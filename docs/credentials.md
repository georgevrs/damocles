# Credentials & API keys — how to obtain everything Damocles needs

This is the single source of truth for every external account, API key, and credential the Damocles stack consumes. Each section includes: **what it powers**, **whether it's required for the demo**, **signup URL**, **step-by-step instructions**, **where the key appears in the dashboard**, **free-tier limits**, **gotchas**, and **the exact `.env` line(s) to fill**.

Validate everything in one shot after editing `.env`:

```powershell
uv run python scripts/verify_sources.py
```

A target of **7/7 sources reachable** means you're fully provisioned.

---

## Priority cheat-sheet

| # | Service | Purpose | Required for | Cost | Time |
|---|---------|---------|--------------|------|------|
| 1 | **Google Gemini** | LLM during dev | All agent work | Free | 2 min |
| 2 | **Neo4j** (local Docker) | Knowledge graph | All graph work | Free | 0 — Docker only |
| 3 | **Copernicus / Sentinel Hub** | SAR satellite tiles | Geospatial sensor (Week 1) | Free | 10 min |
| 4 | **AISStream.io** | Live AIS vessel positions | Dark-vessel detection (Week 1) | Free | 5 min |
| 5 | **Telegram (MTProto)** | OSINT social signals | Telegram sensor (Week 1) | Free | 10 min + SMS |
| 6 | **OpenSky Network** | ADS-B flight tracks | Historical airspace queries (Week 1) | Free | 5 min — optional |
| 7 | **GDELT** | World news events | OSINT sensor (Week 1) | Free | 0 — no key |
| 8 | **Ollama** (local install) | LLM for demo / production | Final demo only | Free | 30 min download |

You can build through Week 1 with just **#1, #2, #3, #4, #5**. **#6 is optional** (state-vector endpoint works anonymously). **#7 needs no setup**. **#8 only matters for the final demo or GCP deploy** — develop on Gemini.

---

## 1 — Google Gemini API key

**What it powers**
Every agent call during development. The plan's LLM provider abstraction means you swap to Ollama for the demo by changing one env var — but for the entire build you should use Gemini because it's faster and avoids a 9 GB model download.

**Required for**: everything from Day 1 onward.

**Signup URL**: https://aistudio.google.com

### Step-by-step

1. Go to **https://aistudio.google.com** and sign in with any Google account.
2. Accept the AI Studio terms.
3. In the left sidebar click **"Get API key"** (key icon).
4. Click **"Create API key"** → choose **"Create API key in new project"** (or pick an existing GCP project if you already have one).
5. Copy the key — it looks like `AIzaSy...` (39 chars).

### `.env` lines

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.0-flash
```

### Free-tier limits (gemini-2.0-flash, the default)

- **15 requests per minute (RPM)**
- **1 million tokens per day**
- **1,500 requests per day**

This is genuinely sufficient for the entire 3-week build. If you hit a `429 PerDayPerProjectPerModel-FreeTier` error, change `GEMINI_MODEL` in `.env` to a model with a fresh quota — no code change needed:

| Model | Free-tier daily reqs | Notes |
| --- | --- | --- |
| `gemini-2.0-flash` | 1,500 | Default. Fastest with structured JSON. |
| `gemini-2.0-flash-lite` | 3,000 | Same family, smaller. Same daily counter as `2.0-flash` in some accounts. |
| `gemini-2.5-flash-lite` | varies | Reliable fallback when the 2.0 family is exhausted. Verified working in early 2026. |

The model is plumbed through `Settings.GEMINI_MODEL` → `factory.get_provider()` → `GeminiProvider(model=...)`. Restart the backend after changing it.

### Gotchas

- The free key has **no billing tied to it**, but Google may eventually require billing for the 2.5+ models. `gemini-2.0-flash` stays free.
- **Don't commit `.env`** — it's `.gitignore`d already, but double-check before pushing.
- Keys are tied to a project. If you later create a GCP project for production, you'll get a new key there.

### Verify

```powershell
uv run python -c "
import asyncio
from backend.llm.factory import get_provider
print(asyncio.run(get_provider().health_check()))
"
```

Should print `True`.

---

## 2 — Neo4j (local Docker, no external account)

**What it powers**
The knowledge graph. Every node (Vessel, NewsEvent, SocialSignal, CompositeEvent, BriefSection, AuditEntry) and every CITES / COMPOSED_OF / CORROBORATES edge.

**Required for**: everything that ingests, queries, or cites graph data — i.e. all of Week 1 onward.

### Setup

No account needed. Damocles runs Neo4j 5.24 Community edition via Docker Compose locally. Just install **Docker Desktop**: https://www.docker.com/products/docker-desktop/

The container is started automatically by `start.ps1` / `start.sh`, but you can also run it directly:

```powershell
docker compose -f docker/neo4j/docker-compose.yml up -d
```

### `.env` lines (defaults work as-is)

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME_neo4j_password
```

### Browser UI

After the container is up: **http://localhost:7474** — login with `neo4j` / `CHANGE_ME_neo4j_password`. Use this to inspect the graph during development and to run ad-hoc Cypher.

### Production note

For GCP deployment the plan recommends running Neo4j as a systemd service rather than Docker for tighter integration. The schema and queries are identical.

---

## 3 — Copernicus / Sentinel Hub (Sentinel-1 SAR)

**What it powers**
Sentinel-1 SAR backscatter tiles — the raw satellite data the Geospatial sensor downloads, runs CFAR vessel detection on, and ingests as `Vessel` nodes.

**Required for**: geospatial sensor (Week 1, Days 3-4). Without this, no SAR-based vessel detections.

**Signup URL**: https://dataspace.copernicus.eu

### Step-by-step

1. Go to **https://dataspace.copernicus.eu** → click **"Register"** (top-right).
2. Fill the form (any working email, any country). EU-resident is not required.
3. Confirm via the email Copernicus sends.
4. Sign in. Top-right user menu → **"Sentinel Hub"** (this opens https://shapps.dataspace.copernicus.eu/dashboard/).
5. In the dashboard, left sidebar → **"User settings"** → **"OAuth clients"** tab.
6. Click **"Create OAuth client"** → name it `damocles-dev` → click **"Create"**.
7. Two values appear:
   - `Client ID` (a UUID-style string)
   - `Client secret` (shown ONCE — copy it now or you'll have to recreate)

### `.env` lines

```
SENTINELHUB_CLIENT_ID=...
SENTINELHUB_CLIENT_SECRET=...
```

### Free-tier limits (Copernicus Data Space, free trial / Personal account)

- **30,000 processing units (PU) / month** for the Sentinel Hub Process API
- For the demo scenario (March 2024 Aegean, 7 days, 10 m resolution) you'll consume **~100-200 PU total** — well inside free tier
- Full Sentinel-1 archive access (we use the IW VV+VH GRD product)

### Gotchas

- The OAuth secret is shown **once**. If you lose it, delete and recreate the client.
- Don't confuse the older **scihub.copernicus.eu** with the new **dataspace.copernicus.eu** — the legacy SciHub was decommissioned. Damocles uses the new Data Space (the `sentinelhub-py` package targets both, but our token URL in `verify_sources.py` is the new one).
- If you see HTTP 401 from the token endpoint, your secret is wrong (most likely got truncated or whitespace-pasted).

### Verify

```powershell
uv run python -c "
import asyncio, httpx
from backend.config import settings
async def t():
    async with httpx.AsyncClient() as c:
        r = await c.post(
            'https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token',
            data={'grant_type':'client_credentials',
                  'client_id': settings.SENTINELHUB_CLIENT_ID,
                  'client_secret': settings.SENTINELHUB_CLIENT_SECRET})
        print(r.status_code, 'access_token' in r.json())
asyncio.run(t())
"
```

Expect `200 True`.

---

## 4 — AISStream.io (live AIS vessel positions)

**What it powers**
Real-time AIS broadcasts from ships. Used to **cross-reference SAR detections**: a vessel visible on SAR but absent from AIS within ±30 min and 2 km is flagged as `AIS_DARK` (the headline alert in the demo).

**Required for**: dark vessel detection (Week 1, Day 5). Without this, every SAR detection looks identical and the AMBER threat-grade logic can't fire.

**Signup URL**: https://aisstream.io

### Step-by-step

1. Go to **https://aisstream.io** → top-right **"Sign up"**.
2. Email + password (free tier, no card).
3. Verify your email.
4. Log in → top-right user menu → **"API Keys"**.
5. Click **"Create API key"** → name it `damocles-dev` → copy the generated key.

### `.env` line

```
AISSTREAM_API_KEY=...
```

### Free-tier limits

- **1 concurrent WebSocket connection**
- **~1,000 messages / minute** (more than the entire Aegean produces during normal operations)
- **All vessel types**, **global coverage**, **real-time** — no historical replay
- WebSocket only — no REST/historical endpoint

### Gotchas

- **No historical AIS in the free tier.** This is the critical reason the plan recommends running the demo against **pre-seeded data** (March 2024 scenario) rather than live AIS. During development, the seed script captures live AIS for a few hours and replays it — see `scripts/seed_neo4j.py` (Week 1).
- For genuine historical AIS during the seed step you can:
  - Cache live AIS during development (the recommended route)
  - Use **MarineTraffic free tier** (sparse, 1 day lookback)
  - Pay for the AISStream historical add-on (~€20/mo, optional)
- The WebSocket URL is `wss://stream.aisstream.io/v0/stream` and the bbox subscription protocol is documented at https://aisstream.io/documentation.

---

## 5 — Telegram MTProto (OSINT social signals)

**What it powers**
Reading **public** Telegram channels (`@aegeanwatch`, `@greekmilitary`, etc.) for social-signal events. These become `SocialSignal` nodes in the graph and feed the Linguist agent's Greek NER.

**Required for**: Telegram sensor (Week 1, Day 6). Without this, no Telegram signals — the OSINT agent loses one of three corroboration sources but still works (GDELT + OpenSky cover most of the demo).

**Signup URL**: https://my.telegram.org

### Step-by-step

1. You need a working **phone number** (any country, must receive SMS or in-app code from Telegram).
2. Go to **https://my.telegram.org** → enter your phone in international format (e.g. `+306900000000`).
3. Telegram sends a login code via the Telegram app (or SMS if you don't have the app installed). Enter it.
4. After login, click **"API development tools"**.
5. Fill the form:
   - **App title**: `Damocles`
   - **Short name**: `damocles`
   - **Platform**: Desktop
   - **URL** / **Description**: leave blank or write `Internal research tool`
6. Submit. Two values appear on the next page:
   - `api_id` (numeric, e.g. `1234567`)
   - `api_hash` (32-char hex)

### `.env` lines

```
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=abcdef0123456789abcdef0123456789
TELEGRAM_PHONE=+306900000000
```

### First-run interactive auth (one-time)

The first time the Telegram sensor runs, Telethon will:
1. Print a code Telegram has sent to your registered devices
2. Prompt you to enter that code in the terminal
3. Persist a session file at `.telethon/damocles.session` so future runs don't need re-auth

This means **the first sensor run requires interactive terminal access** — plan for it during Week 1 Day 6, not during the demo.

### Limits & gotchas

- Telegram has **strict anti-abuse rate limits** — the sensor must pace itself with `await asyncio.sleep(0.1)` between channel fetches. Telethon enforces this automatically.
- **Public channels only.** Reading a private/restricted channel without being a member requires being a member, which is out of scope.
- Don't share `api_hash` — it's tied to your phone number. Treat it like a password.
- If you ever revoke the app on `my.telegram.org`, all session files become invalid and you'll need to re-auth.
- The plan curates a starter list of channels in `backend/sensors/osint.py` (`MONITORED_CHANNELS`). You'll add to it during Week 1 based on what's actively posting about the Aegean.

---

## 6 — OpenSky Network (ADS-B flight tracks) — optional account

**What it powers**
Aircraft state vectors (position, altitude, callsign) for the airspace sensor. Powers the "Unusual flights over Thrace" demo path.

**Required for**: airspace sensor (Week 1, Day 6). The **anonymous endpoint already works** for current state vectors — `verify_sources.py` already returns 148 live aircraft over the Aegean without any credentials. You only need an account for **historical replay** (querying flights from a past time window, which the seed script needs).

**Signup URL**: https://opensky-network.org

### Step-by-step (optional)

1. Go to **https://opensky-network.org** → **"Login / Register"** (top-right).
2. Click **"Sign up"** → fill the form → confirm via email.
3. Log in. Top-right user menu → **"My OpenSky"**.
4. Note your **username** and **password** — these are the credentials the API uses (HTTP basic auth, not a token).

### `.env` lines

```
# Optional — only needed for historical state-vector queries used by the seed script.
# (No keys are required for live state-vectors used during normal sensor operation.)
OPENSKY_USERNAME=
OPENSKY_PASSWORD=
```

> **Note:** these aren't in the current `.env.example` because the airspace sensor isn't built yet. Add them to `.env.example` and `backend/config.py` when you wire up the historical replay path in Week 1 Day 6.

### Limits

- **Anonymous**: 100 API calls / day, current state only, 10 s update cadence
- **Registered**: 4,000 API calls / day, +`/flights/all` historical endpoint, 5 s cadence
- Historical data is held for ~30 days

### Gotchas

- Historical queries can be **slow (5-30 seconds)** because OpenSky stitches them from the long-term archive. Cache aggressively in `data/cache/`.
- The endpoint is HTTPS but uses HTTP basic auth — make sure not to log the auth header.

---

## 7 — GDELT (world news events) — no signup

**What it powers**
Geocoded world news events keyed by CAMEO action codes (military cooperation, mass violence, etc.). Feeds the OSINT agent's news-corroboration step.

**Required for**: OSINT sensor (Week 1, Day 6).

### Setup

**None.** GDELT is fully public. The plan fetches the rolling 15-minute master file index directly:

```
http://data.gdeltproject.org/gdeltv2/masterfilelist.txt
```

`verify_sources.py` already pings this — green out of the box.

### Reference

- Master file index (15-min cadence): http://data.gdeltproject.org/gdeltv2/masterfilelist.txt
- Per-15-min event CSVs: linked from the index, schema documented at http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf
- CAMEO codebook (event codes): http://data.gdeltproject.org/documentation/CAMEO.Manual.1.1b3.pdf
- Optional alternative: BigQuery has the full GDELT 2.0 dataset at `gdelt-bq.gdeltv2.events`. **Free 1 TB/month query budget** is more than enough — but requires a GCP project, so the plan defaults to direct CSV fetches.

### Gotchas

- The 15-minute drop is tab-separated, **no header**. Schema is positional — see the codebook PDF.
- `actor1_countrycode` / `actor2_countrycode` use **FIPS 10-4** (Greece = `GR`, Turkey = `TU`), not ISO 3166. Easy to miss.
- "Geocoded events" are coarse: a Reuters article about "the Aegean" might be tagged at Athens, not the actual incident location. Use a 50 km spatial tolerance in fusion (already set in [`backend/sensors/fusion.py`](../backend/sensors/fusion.py)).

---

## 8 — Ollama (local LLM for demo / production) — install only

**What it powers**
The **same** agent layer as Gemini, but running entirely on local hardware. This is what makes the EYP sovereignty argument true: at demo time no data leaves the machine.

**Required for**: final demo and GCP deployment. **Not needed during development.** Develop on Gemini and switch the env var when prepping the demo.

**Install URL**: https://ollama.com/download

### Step-by-step (Windows)

1. Download the Windows installer from https://ollama.com/download/windows
2. Run the installer. Ollama installs as a system service and starts automatically (listens on `http://localhost:11434`).
3. Open PowerShell and pull the models the plan calls for (`scripts/download_models.ps1` does this for you):

```powershell
ollama pull llama3.1:8b      # primary reasoning, ~4.7 GB
ollama pull qwen2.5:7b       # devil's advocate, ~4.4 GB
ollama pull llama3.2:3b      # fast watch query parser, ~2.0 GB
```

Total: **~11 GB on disk**, ~10-30 min download depending on connection.

### `.env` switch

When ready to demo (or deploy):

```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_DEVIL_MODEL=qwen2.5:7b
```

Restart the backend. **Zero code changes required** — the plan's [`LLMProvider`](../backend/llm/base.py) abstraction routes everything through one interface.

### Hardware requirements (for smooth demo)

- **GPU**: 8 GB VRAM minimum — RTX 3070, M2 Pro, or A10G on GCP. Will run on CPU but inference latency goes from ~3 s to ~30 s per agent call.
- **RAM**: 16 GB minimum (the 8B model needs ~6 GB resident).
- **Disk**: 12 GB free for model files.

### Gotchas

- On Windows, Ollama runs as a service — `ollama serve` is **not** needed (and will fail with "address in use" if you try). Just check the tray icon.
- First call to a freshly-pulled model takes ~5 s longer (model load into VRAM). Subsequent calls are fast.
- If `ollama list` shows no models, `pull` didn't finish — re-run.
- For GCP: instance type `e2-standard-4` from the plan has **no GPU**. For the demo you'll either need to upgrade to `n1-standard-4` + T4 GPU (~€200/mo) or accept ~30 s/agent latency on CPU. The plan's demo-day budget is 60 s per Watch — feasible on CPU but tight.

---

## Production deployment — GCP Secret Manager

For GCP deployment, the plan calls for **GCP Secret Manager** instead of `.env` files. Map each `.env` line to a secret:

```bash
# example
gcloud secrets create damocles-gemini-key --data-file=- <<< "$GEMINI_API_KEY"
gcloud secrets create damocles-sentinelhub-id --data-file=- <<< "$SENTINELHUB_CLIENT_ID"
# ...etc
```

Then mount them as env vars in the runtime (Cloud Run / GCE startup script). [`backend/config.py`](../backend/config.py) reads from the environment regardless of source — no code changes needed.

The mapping isn't documented yet because Week 3 of the build hasn't reached the deploy phase. Add a `docs/deployment.md` when you do.

---

## Quick `.env` template — fill these in order

```bash
# ─── 1. Gemini (REQUIRED — Week 1 Day 1) ─────────────────────────────────────
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIzaSy...

# ─── 2. Neo4j (defaults work — just start Docker Desktop) ────────────────────
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME_neo4j_password

# ─── 3. Copernicus / Sentinel Hub (Week 1 Day 3) ─────────────────────────────
SENTINELHUB_CLIENT_ID=
SENTINELHUB_CLIENT_SECRET=

# ─── 4. AISStream (Week 1 Day 5) ─────────────────────────────────────────────
AISSTREAM_API_KEY=

# ─── 5. Telegram MTProto (Week 1 Day 6) ──────────────────────────────────────
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

# ─── 8. Ollama (FINAL DEMO ONLY — leave Gemini for development) ──────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_DEVIL_MODEL=qwen2.5:7b

# ─── App ─────────────────────────────────────────────────────────────────────
DAMOCLES_ENV=development
LOG_LEVEL=INFO
DEMO_MODE=true
GCP_PROJECT_ID=
```

---

## Confirming everything works

```powershell
uv run python scripts/verify_sources.py
```

Expected output **once all credentials are filled and Docker Desktop is running**:

```
+--------------+--------+----------------------------------------+
| Source       | Status | Detail                                 |
+--------------+--------+----------------------------------------+
| LLM provider | OK     | GeminiProvider model=gemini-2.0-flash  |
| Neo4j        | OK     | connected: bolt://localhost:7687       |
| Sentinel Hub | OK     | OAuth token acquired                   |
| GDELT        | OK     | HTTP 200, 123 MB                       |
| OpenSky      | OK     | 148 state vectors over Aegean          |
| AISStream    | OK     | key present                            |
| Telegram     | OK     | credentials well-formed                |
+--------------+--------+----------------------------------------+

7/7 sources reachable
```

That's the green light to start Week 1 sensors.
