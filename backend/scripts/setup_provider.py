"""Interactive credential setup for a live flight provider, plus a real test.

    python scripts/setup_provider.py duffel
    python scripts/setup_provider.py amadeus

Secrets are read with ``getpass``, so they are never echoed to the terminal and
never land in your shell history. They are written only to ``backend/.env``,
which is git-ignored, and only a masked prefix is printed back.

Where to get credentials:
    Duffel   https://app.duffel.com  ->  Developers  ->  Access tokens
    Amadeus  https://developers.amadeus.com  ->  Self-Service  ->  create an app
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"

# Python puts *this file's* directory on sys.path, not the backend root, so
# `import app` would fail. Adding it here means the script runs from anywhere.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def mask(secret: str) -> str:
    """Show just enough to confirm the right value was pasted."""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:6]}{'*' * (len(secret) - 10)}{secret[-4:]}"


def read_env() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def write_env(updates: dict[str, str]) -> None:
    """Merge ``updates`` into .env, preserving comments and unrelated keys."""
    if ENV_PATH.is_file():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    elif EXAMPLE_PATH.is_file():
        print(f"  Creating {ENV_PATH.name} from {EXAMPLE_PATH.name}")
        lines = EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    remaining = dict(updates)
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
        output.append(line)

    if remaining:
        output.append("")
        output.append("# --- added by scripts/setup_provider.py ---")
        output.extend(f"{key}={value}" for key, value in remaining.items())

    ENV_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")
    # Owner-only, best effort: Windows ignores POSIX mode bits.
    with contextlib.suppress(OSError):
        ENV_PATH.chmod(0o600)


# ----------------------------------------------------------------- providers


def collect_rapidapi(existing: dict[str, str]) -> dict[str, str]:
    print("RapidAPI credentials")
    print("  Key:  https://rapidapi.com/developer/dashboard")
    print("  Host: the 'x-rapidapi-host' on the listing's code snippet,")
    print("        e.g. air-scraper.p.rapidapi.com")
    if existing.get("RAPIDAPI_KEY"):
        print(f"  Existing key on file: {mask(existing['RAPIDAPI_KEY'])}")
    print()

    host = input(f"API host [{existing.get('RAPIDAPI_HOST', '')}]: ").strip()
    host = host or existing.get("RAPIDAPI_HOST", "")
    if not host:
        raise SystemExit("A host is required. Nothing was written.")
    # People paste the whole URL; take just the hostname.
    host = host.removeprefix("https://").removeprefix("http://").rstrip("/").split("/")[0]

    key = getpass("API key (hidden as you type): ").strip()
    if not key:
        raise SystemExit("No key entered. Nothing was written.")

    return {"FLIGHT_PROVIDER": "rapidapi", "RAPIDAPI_KEY": key, "RAPIDAPI_HOST": host}


def collect_duffel(existing: dict[str, str]) -> dict[str, str]:
    print("Duffel access token")
    print("  Portal: https://app.duffel.com -> Developers -> Access tokens")
    print("  A duffel_test_* token returns sandbox inventory;")
    print("  duffel_live_* returns real airline fares.")
    if existing.get("DUFFEL_ACCESS_TOKEN"):
        print(f"  Existing token on file: {mask(existing['DUFFEL_ACCESS_TOKEN'])}")
    print()

    token = getpass("Access token (hidden as you type): ").strip()
    if not token:
        raise SystemExit("No token entered. Nothing was written.")
    if not token.startswith("duffel_"):
        print("\n  Warning: Duffel tokens normally start with 'duffel_test_' or")
        print("  'duffel_live_'. Continuing anyway.")

    return {"FLIGHT_PROVIDER": "duffel", "DUFFEL_ACCESS_TOKEN": token}


def collect_amadeus(existing: dict[str, str], production: bool) -> dict[str, str]:
    base_url = "https://api.amadeus.com" if production else "https://test.api.amadeus.com"
    print("Amadeus Self-Service credentials")
    print("  Portal: https://developers.amadeus.com -> My Self-Service Workspace")
    print(f"  Target: {base_url}")
    if existing.get("AMADEUS_CLIENT_ID"):
        print(f"  Existing key on file: {mask(existing['AMADEUS_CLIENT_ID'])}")
    print()

    client_id = input("API Key (Client ID): ").strip()
    client_secret = getpass("API Secret (hidden as you type): ").strip()
    if not client_id or not client_secret:
        raise SystemExit("Both values are required. Nothing was written.")

    return {
        "FLIGHT_PROVIDER": "amadeus",
        "AMADEUS_CLIENT_ID": client_id,
        "AMADEUS_CLIENT_SECRET": client_secret,
        "AMADEUS_BASE_URL": base_url,
    }


async def verify(provider_name: str) -> int:
    """Run one real search so credential problems surface here, not in the UI."""
    from app.providers.base import ProviderError, SearchRequest
    from app.providers.registry import build_provider

    provider = build_provider(provider_name)  # type: ignore[arg-type]
    if provider.name == "mock":
        print("\n  Credentials were not picked up -- the app fell back to mock.")
        print("  Check the values written to .env.")
        return 1

    departure = date.today() + timedelta(days=45)
    request = SearchRequest(origin="AMM", destination="IST", departure_date=departure)
    print(f"\nTesting {request.origin} -> {request.destination} on {departure}...")

    try:
        offers = await provider.search(request)
    except ProviderError as exc:
        print(f"  FAILED: {exc}")
        print("\n  Check the credentials and that the app is enabled in the")
        print("  provider portal. New keys can take a few minutes to activate.")
        return 1
    finally:
        await provider.aclose()

    if not offers:
        print("  Authenticated, but this market returned no offers.")
        print("  Normal on a sandbox/test token, which carries limited inventory.")
        print("  The credentials themselves are working.")
        return 0

    cheapest = offers[0]
    print(f"  OK: {len(offers)} offers, cheapest {cheapest.price_total} {cheapest.currency}")
    print(f"  Routing: {' -> '.join(cheapest.outbound.path)} on {cheapest.primary_carrier_name}")

    connecting = [offer for offer in offers if offer.outbound.stop_count > 0]
    print(f"  {len(connecting)} of {len(offers)} offers have a connection.")
    if not connecting:
        print("  Note: hidden-city detection needs connecting itineraries.")
        print("  A sandbox token often returns nonstop-only synthetic data.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "provider",
        choices=("rapidapi", "duffel", "amadeus"),
        help="Which provider to set up",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Amadeus only: use the production endpoint instead of the sandbox.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Test the credentials already in .env without changing them.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Save the credentials without running a test search. Useful on a "
        "metered plan, where the test itself costs quota.",
    )
    args = parser.parse_args()
    if args.verify_only and args.no_verify:
        raise SystemExit("--verify-only and --no-verify are contradictory.")

    existing = read_env()

    if not args.verify_only:
        collectors = {
            "rapidapi": lambda: collect_rapidapi(existing),
            "duffel": lambda: collect_duffel(existing),
            "amadeus": lambda: collect_amadeus(existing, args.production),
        }
        updates = collectors[args.provider]()
        write_env(updates)
        print(f"\n  Wrote {ENV_PATH} (git-ignored)")
        for key, value in updates.items():
            print(f"  {key} = {mask(value) if key != 'FLIGHT_PROVIDER' else value}")
        # settings are read at import time, so make this process see them.
        os.environ.update(updates)

    if args.no_verify:
        print("\nSaved without testing. Verify later with:")
        print(f"  python scripts/setup_provider.py {args.provider} --verify-only")
        return 0

    code = asyncio.run(verify(args.provider))
    if code == 0:
        print("\nDone. Restart the API to use live fares:")
        print("  uvicorn app.main:app --reload --port 8000")
    return code


if __name__ == "__main__":
    sys.exit(main())
