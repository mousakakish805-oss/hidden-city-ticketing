# Hidden-City Ticketing

Multi-segment flight **price** anomaly detection.

Ordinary flight search asks one question: *what does A → B cost?* This asks a
second one: *what does A → C cost, when the plane stops at B on the way?*
Sometimes the longer trip is cheaper. That gap is a **hidden-city** fare — you
buy the ticket to C and get off at B.

This tool **reports prices only**. It does not book, reserve, or sell anything,
and it does not track baggage allowances. When you find a fare you want, it
links you to the airline's own site and tells you exactly what to search for.

Available in **English and Arabic**, with full right-to-left support.

```
        the fare you are shown              the fare nobody shows you
     ┌──────────────────────────┐      ┌──────────────────────────────────┐
     │  AMM ──────────►  IST    │      │  AMM ─────► IST ┈┈┈┈┈►  SKP      │
     │           $123           │      │        $85        (you skip)     │
     └──────────────────────────┘      └──────────────────────────────────┘
                                          same seat to Istanbul, $38 less
```

---

## 1. How the detection works

| Step | What happens |
|---|---|
| **1. Baseline** | Price the direct market A → B. Everything is measured against the cheapest fare found here. |
| **2. Candidates** | Pick onward cities **C** behind B that are worth pricing (see below). |
| **3. Fan-out** | Query A → C for every candidate, concurrently, under a rate limit and a wall-clock budget. |
| **4. Validate** | Keep only itineraries where B is an **intermediate** arrival — never the last one. Arriving at B at the end is just a normal connecting flight. |
| **5. Compare** | Vectorised in Pandas: `savings = baseline − price`. Must clear both an absolute and a percentage floor to suppress ordinary fare jitter. |
| **6. Score risk** | Rate how safely each option can actually be executed (below). |
| **7. Learn** | Record which B → C edges paid off, so future searches probe those first. |

### Choosing which cities to price

Every probe costs an API call, so ranking is what decides the running cost.
Candidates come from three sources — real nonstop routes out of B, edges that
produced savings before, and pure geometry as a fallback — then are scored on:

**The expected-fare ratio.** Published fares grow *sublinearly* with distance
and scale with how expensive the destination market is:

```
expected_ratio = (distance(A,C)^0.95 × demand(C)) / (distance(A,B)^0.95 × demand(B))
```

Below 1.0 means C should cost less than B **despite being further** — exactly a
hidden-city opportunity. Modelling this directly is what stops the ranker
preferring somewhere like Hannover behind Istanbul: it is a bigger, cheaper
market, but far enough that the extra distance swamps the saving.

**Detour ratio.** `(dist(A,B) + dist(B,C)) / dist(A,C)`. At `1.0`, B is exactly
on the great circle to C. Above ~1.45 it is a backtrack, not a stop on the way.

**Market viability.** A market with almost no service cannot produce a
through-fare no matter how cheap it looks.

### The risk score (0–100)

A cheaper price is only half the answer. The dominant failure mode is **being
rerouted around B**: after a delay the airline rebooks you to C by any path, and
it has no idea you cared about B.

So the score is driven mainly by *where B sits in the itinerary*:

- **B is the first arrival** (`A → B → C`) — safest. No earlier connection exists to be rerouted.
- **A connection happens first** (`A → X → B → C`) — heavy penalty per preceding leg.
- Round-trip offers are rejected outright: skipping a leg cancels every remaining leg.

Small adjustments follow for tight ground time, thin fare buckets, and savings
so marginal that normal fare movement could erase them.

---

## 2. Languages

English and Arabic, switchable at any time. The choice persists, and switching
mid-results re-renders them (cached upstream, so it costs no API calls).

The split matters:

| Text | Translated in | Why |
|---|---|---|
| Buttons, labels, headings | **Frontend** (`src/i18n/strings.ts`) | Pure chrome, no server round-trip needed |
| Disclaimer, risk warnings, booking steps | **Backend** (`app/i18n/`) | Interpolates live values, and the disclaimer is versioned and legally load-bearing — one auditable source, not two |

Scoring and analysis are **language-free**: they emit a message *code* plus
parameters, and rendering happens at the API boundary. So the database stores
codes, and a finding recorded a year ago is still readable in either language.
Prices and confidence scores are byte-identical across languages — there is a
test asserting exactly that.

Two deliberate choices:

- **Airport and airline names stay in Latin script.** IATA codes are universal, the
  source dataset has no Arabic names, and inventing transliterations would be worse
  than leaving them. Routes (`AMM → IST ⇢ ODS`), codes and times are forced LTR even
  in Arabic — a route is read in travel order, and mirroring it reverses the journey.
- **Arabic uses Latin numerals.** Travellers compare these prices against airline
  sites, which show Latin digits.

Adding a third language means adding one catalog on each side; the tests fail if
a key or a placeholder goes missing.

---

## 3. Architecture

```
frontend/                    React 19 + Vite + Tailwind v4 (TypeScript)
   └── talks to /api  ──────────────┐
                                    ▼
backend/app/
   api/routes/       search · airports · reference · trends · health
   services/         orchestration, offer cache, SSE progress bus, disclaimer
   core/             hub_graph · batch_engine · analyzer (Pandas) · scoring · geo
   providers/        FlightProvider protocol → duffel | amadeus | mock
   data/             global airports · airlines · countries · route graph
   db/               SQLAlchemy 2 async models
```

**The provider seam.** Everything upstream of `providers/` is vendor-neutral.
Duffel and Amadeus have very different shapes — a static bearer token and a
two-step search versus an OAuth exchange and a single GET — yet the analyzer,
ranker and UI are identical for both. Adding another source (Kiwi, an internal
GDS feed) means implementing one protocol: `search()` and `aclose()`.

**Concurrency.** The batch engine fans out with a semaphore, a token-bucket rate
limiter, and a deadline. One dead market cannot sink a run. Database work
happens strictly *either side* of the fan-out, because an `AsyncSession` is not
safe to share across concurrent tasks.

---

## 4. The two data layers

This distinction matters, because only one of them needs an API key.

### Reference data — static, ships in the repo, no key

| | |
|---|---|
| Airports | **6,071** with IATA codes, across **235** countries |
| Airlines | **1,104** (982 active) |
| Route graph | **37,041** directed nonstop routes, each with its operating carriers |

Generated from [OpenFlights](https://github.com/jpatokal/openflights) (Open
Database License) into compressed files under `backend/app/data/generated/`.
Regenerate any time:

```bash
python scripts/build_reference_data.py
```

Two fields are *derived*, not copied, because the ranker needs them:

- **`hub_tier`** — from how many distinct destinations an airport serves.
- **`demand_index`** — fare pressure, from **size × carrier dominance**
  (a Herfindahl index over each airline's share of departures). A big airport
  controlled by one carrier is expensive to fly *to*; a thin market behind it is
  not. Dominance alone would mislead — a tiny airport served by two airlines
  also scores high on concentration while being cheap.

> **Snapshot caveat.** The route dump is a published snapshot, not a live
> schedule feed, so it lags reality. This is safe by construction: the graph
> only decides *what to price*, and the provider decides what actually exists.
> A stale market simply returns no offers.

### Price data — live, **requires an API key**

Fares change constantly and cannot be bundled. This is the layer the key is for.

| Provider | Credential | Use |
|---|---|---|
| `mock` | None | Deterministic synthetic fares. Runs offline. **Default.** |
| `rapidapi` | Key + host | Air Scraper (Skyscanner-derived) via the RapidAPI marketplace. |
| `duffel` | One bearer token | Live fares via the Duffel Flights API. |
| `amadeus` | Key + secret (OAuth) | Live fares via the Amadeus Self-Service API. |

### Watch the quota

One search costs **`MAX_CANDIDATE_DESTINATIONS` + 1** upstream calls — 13 at
the default. That is fine on a paid plan and ruinous on a small free tier,
where it can spend a month's allowance in a couple of dozen searches.

On a free tier, start here:

```bash
MAX_CANDIDATE_DESTINATIONS=4      # 5 calls per search instead of 13
OFFER_CACHE_TTL_SECONDS=21600     # 6h: repeated searches cost nothing
```

Fewer candidates means fewer opportunities found, not worse ones — the ranker
probes in best-first order, so the first few are the most promising. Raise it
once you know the plan can carry it.

Set them up interactively — the secret is never echoed or stored in shell
history, only written to the git-ignored `.env`:

```bash
python scripts/setup_provider.py duffel
```

It writes the credentials and then runs a real search, so a bad token fails
there rather than silently in the UI.

> **Sandbox tokens.** A `duffel_test_*` token returns Duffel's own synthetic
> airline, and Amadeus's test environment serves limited cached inventory.
> Both authenticate fine but neither reflects real fares — and sandbox data is
> often nonstop-only, which means **no hidden cities to find**. Use
> `duffel_live_*` or Amadeus production for real results. The app logs a
> warning at startup when it detects a sandbox token.

The mock is not filler. It uses the **real** route graph and **real** operating
carriers, so every synthesised leg is a city pair that is actually flown by an
airline that actually flies it — and it reproduces the market structure that
creates hidden-city fares in the first place.

---

## 5. Why there is a database

Five jobs, all of which need state that outlives a single request:

| Table | Why it exists |
|---|---|
| `offer_cache` | **Cost control.** One search = ~13 upstream calls. Without a cache, a free API tier is gone in a few hundred searches. With it, the second person searching the same route today costs nothing. This is what makes fan-out affordable. |
| `price_observations` | **Trends.** One API call tells you today's price. It cannot tell you whether $120 is *good*. Only accumulated history can — and every fetch writes one row, so ordinary use builds it for free. |
| `route_candidates` | **Learning.** Records which B → C probes actually produced savings, so they get priced first next time. The system gets cheaper and better-targeted the more it is used. |
| `search_queries` | **Async job state.** Searches run in the background and stream progress; the client must be able to reconnect and fetch the finished result. |
| `disclaimer_acknowledgements` | **Audit trail** that the versioned warning was shown and accepted. |

PostgreSQL in production; **SQLite is the zero-install default** so the app runs
end-to-end with nothing to set up. Set `DATABASE_URL` to switch — the async
driver is selected automatically.

---

## 6. Setup

### Requirements

- **Python 3.11+** (developed on 3.14)
- **Node 18+** — only for the React frontend; the backend ships a zero-build preview UI
- **PostgreSQL** — optional, SQLite is the default

### Backend

```bash
cd backend
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
copy .env.example .env
```

```bash
uvicorn app.main:app --reload --port 8000
```

Then open **http://localhost:8000** — the backend serves a complete preview UI
at `/`, so you can use the whole app without Node. Interactive API docs are at
**http://localhost:8000/docs**.

### Frontend (the primary UI)

```bash
cd frontend
```

```bash
npm install
```

```bash
npm run dev
```

Open **http://localhost:5173**. The dev server proxies `/api` to port 8000, so
the browser stays same-origin — which matters because `EventSource` (used for
live progress) cannot send custom headers.

### Database schema

Development creates tables automatically. Production uses migrations:

```bash
cd backend && alembic upgrade head
```

### Deploying

See **[DEPLOY.md](DEPLOY.md)**. One container serves the API and the compiled
React app together:

```bash
docker compose up --build
```

Set `AUTO_CREATE_SCHEMA=false` in production — `create_all` adds missing tables
but can never alter an existing one, so a column added later would silently not
appear.

### Tests

```bash
cd backend && .venv\Scripts\python.exe -m pytest
```

193 tests covering the detector, the ranker, the risk model, all three
providers, localisation, the global dataset, service suspensions, and the HTTP
layer.

---

## 7. Configuration

Full annotated list in `backend/.env.example`. The ones that matter:

| Variable | Default | Notes |
|---|---|---|
| `FLIGHT_PROVIDER` | `mock` | `mock`, `duffel` or `amadeus` |
| `DUFFEL_ACCESS_TOKEN` | — | `duffel_live_*` for real fares, `duffel_test_*` for sandbox |
| `DUFFEL_API_VERSION` | `v2` | Sent as the `Duffel-Version` header |
| `AMADEUS_CLIENT_ID` / `_SECRET` | — | Required for live fares |
| `AMADEUS_BASE_URL` | `https://test.api.amadeus.com` | Production: `https://api.amadeus.com` |
| `REDIS_URL` | — | Required only for more than one API worker |
| `AUTO_CREATE_SCHEMA` | `true` | Set `false` in production; use Alembic |
| `DATABASE_URL` | SQLite file | `postgresql://user:pass@host:5432/db` |
| `MAX_CANDIDATE_DESTINATIONS` | `12` | **The main cost dial** — each candidate is one API call |
| `PROVIDER_CONCURRENCY` | `6` | Simultaneous upstream requests |
| `PROVIDER_REQUESTS_PER_SECOND` | `5` | Client-side rate limit |
| `MIN_SAVINGS_ABSOLUTE` | `15` | Must clear this **and** the percentage floor |
| `MIN_SAVINGS_PERCENT` | `5` | |
| `MAX_DETOUR_RATIO` | `1.45` | Higher = accept less direct routings |
| `OFFER_CACHE_TTL_SECONDS` | `1800` | |
| `DISCLAIMER_VERSION` | `2026.08.1` | Bumping re-prompts every user |

### Getting credentials

**Duffel** — [app.duffel.com](https://app.duffel.com) → Developers → Access
tokens. One token, no OAuth:

```bash
python scripts/setup_provider.py duffel
```

**Amadeus** — [developers.amadeus.com](https://developers.amadeus.com/) →
create a Self-Service app, then `python scripts/setup_provider.py amadeus`.

Already configured and just want to re-test the connection:

```bash
python scripts/setup_provider.py duffel --verify-only
```

---

## 8. API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/search` | Start a search → `search_id`. `?wait=true` runs it synchronously. |
| `GET` | `/api/search/{id}` | Fetch the finished result, or current status |
| `GET` | `/api/search/{id}/events` | **SSE** live progress from the batch engine |
| `GET` | `/api/search/{id}/matrix` | Just the comparative price matrix |
| `POST` | `/api/search/{id}/acknowledge` | Record disclaimer acceptance |
| `GET` | `/api/airports?q=&country=` | Autocomplete over all 6,071 airports |
| `GET` | `/api/airports/{iata}/candidates?origin=` | Preview the ranker — **spends no API calls** |
| `GET` | `/api/airlines?q=` · `/api/countries?q=` · `/api/coverage` | Reference lookups |
| `GET` | `/api/trends?origin=&destination=` | Price history for a market |
| `GET` | `/api/trends/findings` · `/routes` · `/summary` | Recorded anomalies and the learned graph |
| `GET` | `/api/disclaimer?lang=` · `/api/languages` | Versioned warning text; supported languages |
| `GET` | `/api/health` | Provider, database and disclaimer version |

Pass `"lang": "ar"` in the search body (or `?lang=ar` on `/disclaimer`, or an
`Accept-Language` header) to get Arabic disclaimer text, risk warnings and
booking guidance. Prices and scores are identical either way.

Each hidden-city option carries a `booking` block: the airline's official site,
plus the exact search to run there.

Example:

```bash
curl -X POST "http://localhost:8000/api/search?wait=true" -H "Content-Type: application/json" -d "{\"origin\":\"AMM\",\"destination\":\"IST\",\"departure_date\":\"2026-09-25\"}"
```

---

## 9. Safety

Hidden-city results are **hidden behind a mandatory gate**. The three critical
rules must each be ticked individually before any saving is rendered — a single
"I agree" is too easy to click past when getting it wrong voids the ticket.
Acceptance is stored against a **version**, so changing the wording re-prompts
everyone.

The rules, in short:

1. **One-way tickets only.** Miss a leg and every remaining leg on that ticket is cancelled — including your flight home.
2. **Carry-on only.** Checked bags are tagged to the ticketed destination and fly on without you.
3. **This violates most conditions of carriage.** Airlines have invoiced fare differences, closed frequent-flyer accounts, and confiscated miles. Consequences escalate with repeat use.

Plus: leave your loyalty number off the booking, expect that schedule changes
can route you around your stop, and make sure you are actually admissible where
you get off.

This tool reports prices. It does not give advice, and it does not book.

---

## 10. Known limitations

- **Route/airline data is a snapshot** (circa 2014), so a few markets that have since closed — Donetsk, for instance — can still be proposed. Harmless with a live provider, which returns no offers for them, but visible in mock results.
- **Booking links cover ~90 major airlines.** Smaller carriers get an explicit "no site on file" note rather than a guessed URL. Add more in `app/data/airline_sites.py`.
- **Duration labels (`2h 14m`) are English-only.** They come from the backend's formatter and are not yet localised.
- **Airport and city names are not translated** — the source dataset has no Arabic names.
- **Sandbox tokens have no connections.** Duffel test mode and the Amadeus sandbox often return nonstop-only synthetic data, which means nothing for the detector to find. Real credentials are needed to evaluate the feature honestly.
- **Sandbox route coverage is uneven.** Duffel's test inventory connects some markets via FRA/VIE/DOH but not others, so which origin/destination pairs produce results there is somewhat arbitrary.
- **The RapidAPI provider is written against the documented shape, not a live key.** Air Scraper is an unofficial scraper whose payload can change without notice; run `scripts/probe_rapidapi.py` to confirm the shape before trusting it.
- **The mock is illustrative.** Its prices are modelled, not observed. Anomalies it finds are real *given its model*, not real fares.
