# Deploying

The app ships as **one container** serving both the API and the compiled React
app. That is deliberate: the browser stays same-origin, which matters because
`EventSource` — the live progress stream — cannot send custom headers and is
awkward across origins. It also means there is no CORS configuration to get
wrong in production.

```
┌──────────────────────────────────────────┐
│  hidden-city  (one image)                │
│                                          │
│   /            compiled React app        │
│   /preview     zero-build fallback UI    │
│   /api/*       FastAPI                   │
│   /docs        OpenAPI                   │
└───────────────┬──────────────┬───────────┘
                │              │
          PostgreSQL      Redis (optional)
```

---

## 1. Before you deploy

| | Why |
|---|---|
| **A live provider token** | With `FLIGHT_PROVIDER=mock` your users see invented prices. See below. |
| **PostgreSQL** | SQLite has no place on a host with an ephemeral filesystem — you lose the price history and the learned route graph on every restart. |
| **`AUTO_CREATE_SCHEMA=false`** | Migrations own the schema in production. `create_all` adds missing tables but can never alter one that exists. |
| **`DEBUG=false`** | Otherwise every SQL statement is logged. |

### The provider token

Search-only access is a smaller ask than ticketing. When requesting live
Duffel access, say you need **offer requests and offer search only** — this app
never creates orders, never takes payment, and never issues a ticket.

Once you have it, nothing but the environment changes:

```bash
FLIGHT_PROVIDER=duffel
DUFFEL_ACCESS_TOKEN=duffel_live_...
```

No rebuild, no code change. Restart and it is live.

---

## 2. Run it locally, exactly as production

```bash
docker compose up --build
```

That starts PostgreSQL, Redis and the app, runs migrations, and serves
everything on <http://localhost:8000>. It is the same image you deploy, so if
it works here it works there.

Pass secrets through the environment rather than baking them in:

```bash
FLIGHT_PROVIDER=duffel DUFFEL_ACCESS_TOKEN=duffel_live_xxx docker compose up --build
```

---

## 3. Deploying to a host

Any host that builds a Dockerfile works. The pattern is identical everywhere:

1. Point the host at this repository; it detects the root `Dockerfile`.
2. Attach a PostgreSQL database and let it inject `DATABASE_URL`.
3. Set the environment variables in section 4.
4. Deploy. The container runs `alembic upgrade head` before serving.

**Fly.io**, **Railway** and **Render** all follow exactly these steps and all
offer managed Postgres. The container listens on `$PORT`, which is what these
platforms set, and falls back to 8000.

`postgres://` URLs are converted to the async driver automatically, so whatever
form the host injects will work.

---

## 4. Production environment

```bash
ENVIRONMENT=prod
DEBUG=false
AUTO_CREATE_SCHEMA=false            # Alembic owns the schema

DATABASE_URL=postgresql://user:pass@host:5432/dbname

FLIGHT_PROVIDER=duffel
DUFFEL_ACCESS_TOKEN=duffel_live_... # never commit this

CORS_ORIGINS=                       # empty: same-origin deployment
MAX_CANDIDATE_DESTINATIONS=12       # the main cost dial
```

### Scaling past one worker

The live progress stream is in-process by default. With two workers, a browser
connected to worker B would watch a search running on worker A and see nothing.
Set `REDIS_URL` and the event bus becomes worker-independent:

```bash
REDIS_URL=redis://host:6379/0
WEB_CONCURRENCY=4
```

Do this *before* scaling, not after.

---

## 5. Cost control

This is the number that decides your bill. One search is **1 baseline query +
N candidate probes**, so at the default 12 it is ~13 provider calls.

Three things already reduce that, and one you should set:

- **The offer cache** (30 min default) makes a repeated search free.
- **The learned route graph** stops probing markets that never pay off.
- **Suspended airports** are never probed at all.
- **`MAX_CANDIDATE_DESTINATIONS`** is the dial. Halving it halves your bill and
  finds fewer opportunities.

Watch it with:

```bash
curl https://your-host/api/trends/summary
```

---

## 6. After deploying, check these

```bash
curl https://your-host/api/health
```

Expect `"provider": "duffel"` and `"database": "postgresql"`. If it says
`"provider": "mock"`, the token was not picked up and **your users are seeing
invented prices** — the single most important thing to verify.

Then confirm the schema applied, and that a real search returns something:

```bash
curl -X POST "https://your-host/api/search?wait=true" -H "Content-Type: application/json" -d "{\"origin\":\"AMM\",\"destination\":\"IST\",\"departure_date\":\"2026-09-25\"}"
```

---

## 7. Before you make it public

This tool describes a practice that is legal for travellers but breaks most
airlines' conditions of carriage. Airlines have litigated over it — Lufthansa
sued a passenger, and United and Orbitz sued Skiplagged. Skiplagged still
operates publicly, so this is not forbidden ground, but a public site is a
different proposition from personal use.

The app already does the things that matter: results are gated behind a
disclaimer whose critical rules must be acknowledged individually, that
acknowledgement is recorded server-side with its version, and nothing is ever
booked or sold. Consider also getting terms of service and a privacy notice
reviewed for your jurisdiction, and check your provider's own terms permit the
use you are putting their data to.
