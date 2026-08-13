"""Inspect a RapidAPI flight listing and report whether it can drive this app.

RapidAPI is a marketplace, not an API: one key, hundreds of listings, each with
its own endpoints and response shape. So before a provider can be written, two
questions have to be answered against the real service:

1. Does it authenticate with your key?
2. **Does it name the intermediate airports of a connecting itinerary?**

Question 2 decides everything. Hidden-city detection compares A->B against
A->C-stopping-at-B, so a response that says "1 stop" without saying *where* is
useless here, however good the prices are. Plenty of listings are exactly that.

Usage:
    python scripts/probe_rapidapi.py --host sky-scanner3.p.rapidapi.com \\
        --path /flights/search-one-way \\
        --param fromEntityId=AMM --param toEntityId=IST --param departDate=2026-09-25

    # Or just list what a listing exposes, if you are unsure of the path:
    python scripts/probe_rapidapi.py --host <host> --path / --raw

The key is read from RAPIDAPI_KEY or backend/.env, never from the command line
(arguments show up in shell history and process listings).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from getpass import getpass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Field names that different vendors use for the same concepts. Used to guess
# where the useful data lives, not to parse it.
# Skyscanner-derived listings are published under many names, and each spells
# its endpoints slightly differently. Rather than make the user hunt through
# the dashboard, --discover tries the known combinations and reports which one
# their subscription answers.
#
# Airport-lookup endpoints only: they are the cheapest call each listing has,
# and a wrong host is rejected by the RapidAPI gateway before it ever reaches
# the backing API, so it should not consume quota.
KNOWN_LISTINGS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("sky-scrapper.p.rapidapi.com", "/api/v1/flights/searchAirport", {"query": "IST"}),
    ("air-scrapper.p.rapidapi.com", "/api/v1/flights/searchAirport", {"query": "IST"}),
    ("air-scraper.p.rapidapi.com", "/api/v1/flights/searchAirport", {"query": "IST"}),
    ("flights-sky.p.rapidapi.com", "/flights/auto-complete", {"query": "IST"}),
    ("sky-scanner3.p.rapidapi.com", "/flights/auto-complete", {"query": "IST"}),
    ("skyscanner80.p.rapidapi.com", "/api/v1/flights/searchAirport", {"query": "IST"}),
    ("skyscanner89.p.rapidapi.com", "/flights/auto-complete", {"query": "IST"}),
    ("tripadvisor16.p.rapidapi.com", "/api/v1/flights/searchAirport", {"query": "IST"}),
)

MAX_PROBE_POLLS = 3

SEGMENT_HINTS = ("segment", "leg", "flight", "sector")
AIRPORT_HINTS = ("iata", "airport", "origin", "destination", "departure", "arrival", "from", "to")
PRICE_HINTS = ("price", "amount", "total", "fare", "cost")
MAX_DEPTH = 6


def load_key() -> str:
    """Environment, then .env, then ask.

    Prompting matters: this script exists to check an API *before* committing
    to it, which is exactly when the key has not been saved anywhere yet.
    Reading it from an argument is never an option -- arguments persist in
    shell history and are visible in process listings.
    """
    key = os.environ.get("RAPIDAPI_KEY")
    if key:
        return key

    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, _, value = line.strip().partition("=")
            if name.strip() == "RAPIDAPI_KEY" and value.strip():
                return value.strip()

    print("No RapidAPI key in the environment or backend/.env.")
    print("Paste it here to probe without saving it anywhere.\n")
    key = getpass("RapidAPI key (hidden as you type): ").strip()
    if not key:
        raise SystemExit("No key entered.")
    return key


def describe(value: Any, depth: int = 0, path: str = "") -> list[str]:
    """Render the *shape* of a JSON payload rather than its contents."""
    pad = "  " * depth
    if depth > MAX_DEPTH:
        return [f"{pad}..."]

    if isinstance(value, dict):
        lines = []
        for key, child in list(value.items())[:25]:
            here = f"{path}.{key}" if path else key
            if isinstance(child, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(describe(child, depth + 1, here))
            else:
                sample = repr(child)
                if len(sample) > 60:
                    sample = sample[:57] + "..."
                lines.append(f"{pad}{key} = {sample}")
        if len(value) > 25:
            lines.append(f"{pad}... {len(value) - 25} more keys")
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{pad}[] (empty)"]
        lines = [f"{pad}[{len(value)} items], first:"]
        lines.extend(describe(value[0], depth + 1, f"{path}[]"))
        return lines

    return [f"{pad}{value!r}"]


def walk(value: Any, path: str = "") -> list[tuple[str, Any]]:
    """Flatten to (dotted path, value) so we can search for concepts."""
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}" if path else key
            found.append((here, child))
            found.extend(walk(child, here))
    elif isinstance(value, list) and value:
        here = f"{path}[]"
        found.append((here, value[0]))
        found.extend(walk(value[0], here))
    return found


def looks_like_iata(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 3 and value.isalpha() and value.isupper()


def assess(payload: Any) -> int:
    """Report whether this response can support hidden-city detection."""
    entries = walk(payload)

    segment_paths = sorted(
        {
            path
            for path, _ in entries
            if any(hint in path.lower().split(".")[-1] for hint in SEGMENT_HINTS)
        }
    )
    price_paths = sorted(
        {
            path
            for path, value in entries
            if isinstance(value, (int, float, str))
            and any(hint in path.lower().split(".")[-1] for hint in PRICE_HINTS)
        }
    )
    iata_paths = sorted({path for path, value in entries if looks_like_iata(value)})

    print("\n" + "=" * 70)
    print("CAN THIS API DRIVE HIDDEN-CITY DETECTION?")
    print("=" * 70)

    print(f"\n  Price-like fields ({len(price_paths)}):")
    for path in price_paths[:8]:
        print(f"    {path}")

    print(f"\n  Segment/leg containers ({len(segment_paths)}):")
    for path in segment_paths[:10]:
        print(f"    {path}")

    print(f"\n  Fields holding a 3-letter airport code ({len(iata_paths)}):")
    for path in iata_paths[:12]:
        print(f"    {path}")

    # The decisive test: airport codes appearing *inside* a repeated segment
    # container means intermediate stops are named.
    nested = [p for p in iata_paths if "[]" in p and any(h in p.lower() for h in SEGMENT_HINTS)]

    print("\n" + "-" * 70)
    if nested:
        print("  VERDICT: looks USABLE.")
        print("  Airport codes appear inside repeated segment containers, which")
        print("  means intermediate stops are named. Examples:")
        for path in nested[:6]:
            print(f"    {path}")
        return 0

    if iata_paths and segment_paths:
        print("  VERDICT: UNCERTAIN.")
        print("  Both segments and airport codes exist, but not obviously nested")
        print("  together. Paste the JSON above and it can be judged properly.")
        return 0

    print("  VERDICT: probably NOT USABLE.")
    print("  No airport codes found inside per-segment structures. If this API")
    print("  only reports a stop *count* and not which airports, hidden-city")
    print("  detection is impossible with it -- the whole feature depends on")
    print("  knowing where the plane touches down.")
    return 1


def discover(key: str) -> int:
    """Find which known listing this key is actually subscribed to."""
    print("Trying known Skyscanner-derived listings...\n")
    hits: list[tuple[str, str]] = []

    for host, path, params in KNOWN_LISTINGS:
        try:
            response = httpx.get(
                f"https://{host}{path}",
                params=params,
                headers={"x-rapidapi-key": key, "x-rapidapi-host": host},
                timeout=25.0,
            )
        except httpx.HTTPError as exc:
            print(f"  {host:38s} {path:34s} transport error: {type(exc).__name__}")
            continue

        code = response.status_code
        if code == 200:
            marker = "  <-- SUBSCRIBED"
            hits.append((host, path))
        elif code == 403:
            marker = "  (exists, but not subscribed / quota spent)"
        elif code in (401, 404):
            marker = ""
        else:
            marker = ""
        print(f"  {host:38s} {path:34s} HTTP {code}{marker}")

    print()
    if not hits:
        print("None of the known listings answered.")
        print("Open your subscribed API on rapidapi.com -> Endpoints -> code snippet,")
        print("and read off 'x-rapidapi-host' and the URL path. Then run:")
        print("  python scripts/probe_rapidapi.py --host <host> --path <path> --param query=IST")
        return 1

    host, path = hits[0]
    print(f"Found it: {host}")
    print("\nInspect the flight-search response next:")
    print(f"  python scripts/probe_rapidapi.py --host {host} --path {path} --param query=IST --raw")
    return 0


def search_flow(key: str, host: str, origin: str, destination: str, save: str | None) -> int:
    """Exercise the real two-step flow: resolve airports, then search flights.

    This is the check that matters. It follows exactly the sequence the
    provider uses, so if this returns a usable payload the provider will work,
    and if it does not the dump shows precisely what to fix.

    Costs three API calls.
    """
    from datetime import date, timedelta

    headers = {"x-rapidapi-key": key, "x-rapidapi-host": host}
    places: dict[str, dict[str, str]] = {}

    for code in (origin, destination):
        print(f"Resolving {code}...")
        response = httpx.get(
            f"https://{host}/api/v1/flights/searchAirport",
            params={"query": code, "locale": "en-US"},
            headers=headers,
            timeout=30.0,
        )
        if response.status_code != 200:
            print(f"  HTTP {response.status_code}: {response.text[:200]}")
            return 1

        entries = response.json().get("data") or []
        match = None
        for entry in entries:
            params = (entry.get("navigation") or {}).get("relevantFlightParams") or {}
            sky_id = entry.get("skyId") or params.get("skyId")
            entity_id = entry.get("entityId") or params.get("entityId")
            if sky_id and entity_id and str(sky_id).upper() == code.upper():
                match = {"skyId": str(sky_id), "entityId": str(entity_id)}
                break

        if match is None:
            print(f"  No exact match for {code}. First entry looked like:")
            for line in describe(entries[0] if entries else {})[:20]:
                print(f"    {line}")
            return 1

        print(f"  skyId={match['skyId']} entityId={match['entityId']}")
        places[code] = match

    departure = (date.today() + timedelta(days=45)).isoformat()
    search_params = {
        "originSkyId": places[origin]["skyId"],
        "destinationSkyId": places[destination]["skyId"],
        "originEntityId": places[origin]["entityId"],
        "destinationEntityId": places[destination]["entityId"],
        "date": departure,
        "cabinClass": "economy",
        "adults": 1,
        "sortBy": "best",
        "currency": "USD",
        "market": "en-US",
        "countryCode": "US",
    }
    print(f"\nSearching {origin} -> {destination} on {departure}...")
    response = httpx.get(
        f"https://{host}/api/v1/flights/searchFlights",
        params=search_params,
        headers=headers,
        timeout=60.0,
    )
    print(f"  HTTP {response.status_code} | {len(response.content):,} bytes")
    if response.status_code != 200:
        print(f"  {response.text[:400]}")
        return 1

    payload = response.json()

    # The first call starts the search server-side and returns a fragment.
    # Re-issuing the same request collects the finished result; this listing
    # has no dedicated polling endpoint.
    for attempt in range(MAX_PROBE_POLLS):
        if ((payload.get("data") or {}).get("context") or {}).get("status") != "incomplete":
            break
        if attempt == 0:
            print(f"  status=incomplete -- re-issuing (up to {MAX_PROBE_POLLS} times)")
        wait = 3.0 * (attempt + 1)
        print(f"    waiting {wait:.0f}s for the search to settle...")
        time.sleep(wait)
        retried = httpx.get(
            f"https://{host}/api/v1/flights/searchFlights",
            params=search_params,
            headers=headers,
            timeout=60.0,
        )
        if retried.status_code != 200:
            print(f"    retry {attempt + 1}: HTTP {retried.status_code} {retried.text[:150]}")
            break
        body = retried.json()
        data = body.get("data") or {}
        count = len(data.get("itineraries") or [])
        status = (data.get("context") or {}).get("status")
        print(f"    retry {attempt + 1}: status={status} itineraries={count}")
        if count >= len((payload.get("data") or {}).get("itineraries") or []):
            payload = body

    if save:
        Path(save).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  saved to {save}")

    itineraries = ((payload.get("data") or {}).get("itineraries")) or []
    stop_prices = ((payload.get("data") or {}).get("filterStats") or {}).get("stopPrices") or {}
    if stop_prices:
        direct = (stop_prices.get("direct") or {}).get("isPresent")
        print(f"  direct flights present: {direct}")
    print(f"  itineraries: {len(itineraries)}")
    if not itineraries:
        print("\n  No itineraries. Response shape:")
        for line in describe(payload)[:60]:
            print(line)
        return 1

    connecting = [i for i in itineraries if (i.get("legs") or [{}])[0].get("stopCount")]
    self_transfer = [i for i in itineraries if i.get("isSelfTransfer")]
    print(f"  with a connection: {len(connecting)}   self-transfer: {len(self_transfer)}")

    print("\n  First itinerary, shape:")
    for line in describe(itineraries[0])[:45]:
        print("   " + line)

    return assess(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Try the known Skyscanner-derived listings and report which one "
        "your key is subscribed to.",
    )
    parser.add_argument(
        "--search",
        nargs=2,
        metavar=("ORIGIN", "DESTINATION"),
        help="Run the full two-step flow (resolve airports, then search) and "
        "report whether the payload can drive the detector. Costs 3 calls.",
    )
    parser.add_argument("--host", help="e.g. sky-scrapper.p.rapidapi.com")
    parser.add_argument("--path", default="/", help="Endpoint path to call")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Query parameter; repeat for each one",
    )
    parser.add_argument("--raw", action="store_true", help="Dump the raw JSON too")
    parser.add_argument("--save", metavar="FILE", help="Write the raw response to a file")
    args = parser.parse_args()

    key = load_key()

    if args.discover:
        return discover(key)
    if not args.host:
        raise SystemExit("--host is required (or use --discover to find it).")
    if args.search:
        return search_flow(key, args.host, args.search[0].upper(), args.search[1].upper(), args.save)

    params = dict(pair.split("=", 1) for pair in args.param if "=" in pair)

    url = f"https://{args.host}{args.path}"
    print(f"GET {url}")
    print(f"  params: {params or '(none)'}")
    print(f"  key:    {key[:6]}{'*' * 12}{key[-4:]}")

    try:
        response = httpx.get(
            url,
            params=params,
            headers={"x-rapidapi-key": key, "x-rapidapi-host": args.host},
            timeout=45.0,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        print(f"\n  Transport error: {exc}")
        return 1

    print(f"\n  HTTP {response.status_code} | {len(response.content):,} bytes")
    for header in ("x-ratelimit-requests-limit", "x-ratelimit-requests-remaining"):
        if header in response.headers:
            print(f"  {header}: {response.headers[header]}")

    if response.status_code == 401:
        print("\n  Unauthorised -- the key is wrong, or not subscribed to this listing.")
        return 1
    if response.status_code == 403:
        print("\n  Forbidden -- usually means you are not subscribed to this API,")
        print("  or the free quota for the month is exhausted.")
        return 1
    if response.status_code == 404:
        print(f"\n  Not found. The gateway said: {response.text[:200]}")
        print("  Either the host or the path is wrong. Find the right one with:")
        print("    python scripts/probe_rapidapi.py --discover")
        return 1

    try:
        payload = response.json()
    except ValueError:
        print("\n  Response is not JSON:")
        print(response.text[:500])
        return 1

    if args.save:
        Path(args.save).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"  saved to {args.save}")

    print("\n" + "=" * 70)
    print("RESPONSE SHAPE")
    print("=" * 70)
    for line in describe(payload)[:120]:
        print(line)

    if args.raw:
        print("\n" + "=" * 70)
        print("RAW")
        print("=" * 70)
        print(json.dumps(payload, indent=2)[:6000])

    return assess(payload)


if __name__ == "__main__":
    sys.exit(main())
