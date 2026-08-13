"""Build the global reference dataset from OpenFlights.

Downloads the public OpenFlights dumps and compiles three compact, gzipped
files that ship with the app:

    app/data/generated/airports.json.gz   every airport with a real IATA code
    app/data/generated/airlines.json.gz   every airline with a real IATA code
    app/data/generated/routes.json.gz     the served-route adjacency graph

Two properties the raw data does not contain are derived here, because the
candidate generator depends on them:

**hub_tier** -- from the number of distinct destinations an airport serves.
A route count is a far better hub proxy than any hand-written list.

**demand_index** -- a fare-pressure proxy combining *size* with *carrier
dominance* (a Herfindahl index over each airline's share of departures).
This matters because the two together are what create hidden-city
opportunities: a big airport dominated by one carrier is expensive to fly
*to*, while thin markets behind it stay competitively priced. Dominance alone
would be misleading, since a tiny airport served by two airlines also scores
high on concentration while being cheap.

Usage:
    python scripts/build_reference_data.py [--offline]

Source: https://github.com/jpatokal/openflights (Open Database License).
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data"
SOURCES = {
    "airports": f"{BASE_URL}/airports.dat",
    "airlines": f"{BASE_URL}/airlines.dat",
    "routes": f"{BASE_URL}/routes.dat",
    "countries": f"{BASE_URL}/countries.dat",
}

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "app" / "data" / "generated"
CACHE_DIR = ROOT / ".cache" / "openflights"

NULL_TOKENS = {"", "\\N", "-", "N/A", "null"}

# Airports that serve one city but carry a different city name in the source
# data, so (city, country) grouping alone would miss them.
METRO_OVERRIDES: dict[str, str] = {
    "JFK": "NYC", "LGA": "NYC", "EWR": "NYC", "HPN": "NYC", "SWF": "NYC",
    "IAD": "WAS", "DCA": "WAS", "BWI": "WAS",
    "ORD": "CHI", "MDW": "CHI",
    "SFO": "SFO", "OAK": "SFO", "SJC": "SFO",
    "LAX": "LAX", "BUR": "LAX", "LGB": "LAX", "SNA": "LAX", "ONT": "LAX",
    "HND": "TYO", "NRT": "TYO",
    "ITM": "OSA", "KIX": "OSA", "UKB": "OSA",
    "PEK": "BJS", "PKX": "BJS",
    "PVG": "SHA", "SHA": "SHA",
    "GIG": "RIO", "SDU": "RIO",
    "GRU": "SAO", "CGH": "SAO", "VCP": "SAO",
    "EZE": "BUE", "AEP": "BUE",
    "SVO": "MOW", "DME": "MOW", "VKO": "MOW", "ZIA": "MOW",
    "MXP": "MIL", "LIN": "MIL", "BGY": "MIL",
    "CDG": "PAR", "ORY": "PAR", "BVA": "PAR",
    "LHR": "LON", "LGW": "LON", "STN": "LON", "LTN": "LON", "LCY": "LON", "SEN": "LON",
    "BCN": "BCN", "GRO": "BCN", "REU": "BCN",
    "IST": "IST", "SAW": "IST",
    "DXB": "DXB", "DWC": "DXB",
    "KUL": "KUL", "SZB": "KUL",
    "YYZ": "YTO", "YTZ": "YTO",
    "BER": "BER",
    "STO": "STO", "ARN": "STO", "BMA": "STO", "NYO": "STO",
    "OSL": "OSL", "TRF": "OSL",
    "TLV": "TLV", "SDV": "TLV",
    "DEL": "DEL", "BOM": "BOM",
}


def looks_null(value: str) -> bool:
    return value.strip() in NULL_TOKENS


def valid_iata(value: str) -> bool:
    """Airport IATA codes: exactly three uppercase letters."""
    value = value.strip()
    return len(value) == 3 and value.isalpha() and value.isupper()


def valid_airline_iata(value: str) -> bool:
    """Airline IATA codes are TWO characters and may contain a digit (A3, W6)."""
    value = value.strip()
    return len(value) == 2 and value.isalnum() and value.upper() == value


def fetch(name: str, url: str, *, offline: bool) -> str:
    """Download a source file, caching it so reruns are instant."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{name}.dat"

    if offline and cached.exists():
        print(f"  {name}: using cached copy ({cached.stat().st_size:,} bytes)")
        return cached.read_text(encoding="utf-8")

    if offline:
        raise SystemExit(f"--offline requested but no cached copy of {name} at {cached}")

    print(f"  {name}: downloading...")
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    text = response.text
    cached.write_text(text, encoding="utf-8")
    print(f"  {name}: {len(text):,} bytes")
    return text


def parse_airports(raw: str) -> dict[str, dict[str, Any]]:
    """OpenFlights airports.dat -> {IATA: record} for real, IATA-coded airports."""
    airports: dict[str, dict[str, Any]] = {}
    skipped = 0

    for row in csv.reader(StringIO(raw)):
        if len(row) < 14:
            skipped += 1
            continue
        _, name, city, country, iata, icao, lat, lon, _alt, _tz, _dst, tzname, kind, _src = row[:14]

        if kind.strip() != "airport" or not valid_iata(iata):
            skipped += 1
            continue
        try:
            latitude, longitude = float(lat), float(lon)
        except ValueError:
            skipped += 1
            continue
        # A handful of rows carry placeholder coordinates.
        if latitude == 0.0 and longitude == 0.0:
            skipped += 1
            continue

        airports[iata] = {
            "iata": iata,
            "icao": None if looks_null(icao) else icao.strip(),
            "name": name.strip(),
            "city": city.strip() or name.strip(),
            "country": country.strip(),
            "lat": round(latitude, 5),
            "lon": round(longitude, 5),
            "tz": None if looks_null(tzname) else tzname.strip(),
        }

    print(f"  parsed {len(airports):,} IATA airports ({skipped:,} rows skipped)")
    return airports


def parse_airlines(raw: str) -> dict[str, dict[str, Any]]:
    """OpenFlights airlines.dat -> {IATA: record}.

    IATA codes are reused after an airline folds, so active carriers win any
    collision -- showing a live flight under a defunct airline's name would be
    worse than showing nothing.
    """
    airlines: dict[str, dict[str, Any]] = {}
    for row in csv.reader(StringIO(raw)):
        if len(row) < 8:
            continue
        _, name, alias, iata, icao, callsign, country, active = row[:8]
        if not valid_airline_iata(iata):
            continue
        # The source carries placeholder rows whose "name" is just the code
        # echoed back (IATA 'ZZ' -> name 'Zz'). Showing those as an airline
        # would be worse than showing the raw code.
        name = name.strip()
        if len(name) < 3 or name.casefold() == iata.strip().casefold():
            continue

        record = {
            "iata": iata.strip(),
            "icao": None if looks_null(icao) else icao.strip(),
            "name": name,
            "alias": None if looks_null(alias) else alias.strip(),
            "callsign": None if looks_null(callsign) else callsign.strip(),
            "country": country.strip(),
            "active": active.strip().upper() == "Y",
        }

        existing = airlines.get(record["iata"])
        if existing is None or (record["active"] and not existing["active"]):
            airlines[record["iata"]] = record

    active_count = sum(1 for a in airlines.values() if a["active"])
    print(f"  parsed {len(airlines):,} IATA airlines ({active_count:,} active)")
    return airlines


def parse_countries(raw: str) -> dict[str, str]:
    """OpenFlights countries.dat -> {country name: ISO 3166-1 alpha-2}."""
    codes: dict[str, str] = {}
    for row in csv.reader(StringIO(raw)):
        if len(row) < 2:
            continue
        name, iso = row[0].strip(), row[1].strip()
        if name and len(iso) == 2 and iso.isalpha():
            codes[name.casefold()] = iso.upper()
    print(f"  parsed {len(codes):,} countries with ISO codes")
    return codes


def region_from_timezone(tz: str | None) -> str:
    """Olson timezone -> broad region, e.g. 'Europe/Istanbul' -> 'Europe'.

    A pragmatic stand-in for a continent field the source data lacks; the API
    only uses it for grouping and filtering.
    """
    if not tz or "/" not in tz:
        return "Other"
    area = tz.split("/", 1)[0]
    return {
        "America": "Americas",
        "Atlantic": "Atlantic",
        "Indian": "Indian Ocean",
        "Australia": "Oceania",
        "Pacific": "Oceania",
        "Antarctica": "Antarctica",
    }.get(area, area)


def parse_routes(
    raw: str,
    airports: dict[str, dict[str, Any]],
    known_airlines: set[str],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, Counter[str]]]:
    """OpenFlights routes.dat -> route graph with operators, plus carrier mix.

    Carriers are recorded per *route*, not just per airport, so anything naming
    an operator can name one that actually flies that leg. Codes absent from
    the airline table are dropped -- an unresolvable code is worse than none.
    """
    graph: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    carriers: dict[str, Counter[str]] = defaultdict(Counter)
    kept = 0

    for row in csv.reader(StringIO(raw)):
        if len(row) < 9:
            continue
        airline, _airline_id, source, _src_id, destination, _dst_id = row[:6]
        source, destination, airline = source.strip(), destination.strip(), airline.strip()

        if source not in airports or destination not in airports or source == destination:
            continue

        operator = airline if valid_airline_iata(airline) and airline in known_airlines else None
        graph[source][destination]
        if operator:
            graph[source][destination].add(operator)
            carriers[source][operator] += 1
        kept += 1

    resolved = {
        origin: {dest: sorted(ops) for dest, ops in dests.items()}
        for origin, dests in graph.items()
    }
    print(f"  parsed {kept:,} routes over {len(resolved):,} origin airports")
    return resolved, carriers


def herfindahl(counts: Counter[str]) -> float:
    """Carrier concentration at an airport, 0 (fragmented) to 1 (monopoly)."""
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return sum((count / total) ** 2 for count in counts.values())


def hub_tier(destination_count: int) -> int:
    if destination_count >= 150:
        return 3
    if destination_count >= 60:
        return 2
    if destination_count >= 12:
        return 1
    return 0


def demand_index(destination_count: int, concentration: float) -> float:
    """Relative fare pressure for flying *to* this airport.

    Size dominates, carrier dominance amplifies. A fortress hub lands near 1.30
    (IST), a mid-size capital near 0.95 (OTP), a thin regional market near 0.45.
    See the module docstring for why both terms are needed.

    The spread matters as much as the ordering: it is the gap between a hub and
    the markets behind it that a hidden-city fare exploits, so a compressed
    scale would hide real opportunities.
    """
    if destination_count <= 0:
        return 0.45
    # log-scaled so the top of the range is not owned by a handful of megahubs.
    size = min(1.0, math.log(destination_count + 1) / math.log(260))
    return round(0.45 + 0.75 * (size**1.8) + 0.35 * concentration * size, 3)


def assign_metros(airports: dict[str, dict[str, Any]]) -> None:
    """Group airports serving one city, so 'IST' can reject a landing at SAW."""
    by_city: dict[tuple[str, str], list[str]] = defaultdict(list)
    for code, airport in airports.items():
        by_city[(airport["city"].casefold(), airport["country"].casefold())].append(code)

    for codes in by_city.values():
        if len(codes) < 2:
            continue
        # Name the group after its largest member for a stable, readable key.
        anchor = max(codes, key=lambda code: airports[code]["destination_count"])
        for code in codes:
            airports[code]["metro"] = anchor

    for code, metro in METRO_OVERRIDES.items():
        if code in airports:
            airports[code]["metro"] = metro


def write_gzip_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as handle:
        json.dump(payload, handle, separators=(",", ":"), ensure_ascii=False)
    print(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size:,} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="use cached downloads instead of the network"
    )
    args = parser.parse_args()

    print("Fetching OpenFlights sources")
    raw = {name: fetch(name, url, offline=args.offline) for name, url in SOURCES.items()}

    print("\nParsing")
    airports = parse_airports(raw["airports"])
    airlines = parse_airlines(raw["airlines"])
    iso_codes = parse_countries(raw["countries"])
    # Only carriers still operating should be attached to a route; a defunct
    # airline named on a live-looking itinerary reads as a bug.
    active_airlines = {code for code, row in airlines.items() if row["active"]}
    adjacency, carriers = parse_routes(raw["routes"], airports, active_airlines)

    print("\nDeriving hub tiers, demand indices and regions")
    for code, airport in airports.items():
        destinations = adjacency.get(code, {})
        airport_carriers = carriers.get(code, Counter())
        concentration = herfindahl(airport_carriers)
        airport["destination_count"] = len(destinations)
        airport["carrier_count"] = len(airport_carriers)
        airport["concentration"] = round(concentration, 3)
        # Who actually flies here, busiest first. Lets the app name a plausible
        # operating carrier for any hub instead of guessing.
        airport["top_carriers"] = [code for code, _ in airport_carriers.most_common(6)]
        airport["hub_tier"] = hub_tier(len(destinations))
        airport["demand_index"] = demand_index(len(destinations), concentration)
        airport["country_code"] = iso_codes.get(airport["country"].casefold())
        airport["region"] = region_from_timezone(airport["tz"])
        airport["metro"] = None

    assign_metros(airports)

    tiers = Counter(airport["hub_tier"] for airport in airports.values())
    print("  hub tiers: " + ", ".join(f"tier {t}={tiers[t]:,}" for t in sorted(tiers, reverse=True)))

    # Only countries that actually have an airport are worth exposing.
    country_rows: dict[str, dict[str, Any]] = {}
    for airport in airports.values():
        name = airport["country"]
        row = country_rows.setdefault(
            name,
            {
                "name": name,
                "code": airport["country_code"],
                "region": airport["region"],
                "airport_count": 0,
            },
        )
        row["airport_count"] += 1
    countries = sorted(country_rows.values(), key=lambda row: row["name"])
    missing_iso = sum(1 for row in countries if not row["code"])
    print(f"  {len(countries):,} countries with airports ({missing_iso} without an ISO code)")

    print("\nWriting")
    write_gzip_json(OUTPUT_DIR / "airports.json.gz", list(airports.values()))
    write_gzip_json(OUTPUT_DIR / "airlines.json.gz", list(airlines.values()))
    write_gzip_json(OUTPUT_DIR / "routes.json.gz", adjacency)
    write_gzip_json(OUTPUT_DIR / "countries.json.gz", countries)

    print(
        f"\nDone. {len(airports):,} airports, {len(airlines):,} airlines, "
        f"{len(countries):,} countries, "
        f"{sum(len(dests) for dests in adjacency.values()):,} directed routes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
