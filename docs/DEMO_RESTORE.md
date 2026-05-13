# Demo Snapshot & Restore

The pitch day's worst failure mode: an overnight scan replaces the seeded
RED AoI with a fresh GREEN noise cluster, and the demo opens to nothing
worth clicking. To prevent that, we pin a known-good DuckDB snapshot and
disable the cron during the pitch window.

## What's in the snapshot

`data/damocles.duckdb.demo` is a frozen copy of the fact store taken at
the end of the W1 data-quality pass. State at snapshot time:

| | Count |
|---|---|
| Total AoIs | 80 |
| **RED** | **6** (Athens Syntagma · Istanbul Central · North Heraklion · Northern Evros · Ephesus · Gemlik Bay) |
| AMBER | 0 |
| GREEN | 74 |
| Composites | 1392 |
| `raw_ais` (mostly SAR-mirror) | 1238 (961 water, 277 land — tagged by `is_water`) |
| `raw_sar` | 1238 (same row count, same tagging) |
| `raw_news` | 158 (7 hot, Goldstein ≤ -5) |
| **Pre-cached canonical briefs** | **6 (one per RED)** — serve in <50 ms |

All AoIs in the snapshot are sourced from at least one water-tagged
detection. The multi-source escalation rule was active when these were
generated — every cluster with ≥2 distinct source types AND a dark
vessel AND a hot-news signal got promoted to RED; single-strand clusters
were capped at GREEN. Everything in between got AMBER (currently 0 because
every multi-source cluster in this data had the dark+hot pattern).

Verified: 10/10 random sample AoIs (seed=1337) are over genuine water.
Verified: 6 RED AoIs are geographically + topically defensible — every
one has Vessel + NewsEvent sources, on water or operationally relevant
coast, with Greek-native naming.

## Demo-target candidates

For the killer scenario (W2-T1 in the gold-medal plan), the strongest
candidates ranked by demo strength:

| Rank | AoI | Centroid | Events | Why |
|---|---|---|---|---|
| 1 | **Κέντρο Αθήνας - Σύνταγμα** (Athens Syntagma) | (37.97, 23.74) | 35 | Greek capital, central square, strong cross-source, name reads as operational |
| 2 | **Βόρειος Έβρος** (Northern Evros) | (40.98, 26.46) | 8 | Greek border, terror-relevant, smaller cluster = clearer story |
| 3 | **Βόρεια Ζώνη Ηρακλείου** (North Heraklion) | (35.36, 25.10) | 18 | Crete coastal, real maritime context |
| 4 | Ephesus / Istanbul / Gemlik (Turkish coast) | various | various | Defensible cross-border AoIs but pitch story needs prep ("not a territorial claim") |

## How to restore for demo

```powershell
# 0. Stop the backend
Get-NetTCPConnection -State Listen -LocalPort 8001 |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 1. Snapshot the live DB (in case you want to roll back later)
Copy-Item "data\damocles.duckdb" "data\damocles.duckdb.bak" -Force

# 2. Restore the demo snapshot
Copy-Item "data\damocles.duckdb.demo" "data\damocles.duckdb" -Force

# 3. Disable the cron in .env (write-once toggle for the demo)
#    Edit .env:  STANDING_SCAN_CRON=        (empty = cron disabled)

# 4. Boot backend normally
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

On Linux/bash:

```bash
# 0. Stop backend
lsof -ti:8001 | xargs kill -9 2>/dev/null || true

# 1. Backup current state
cp data/damocles.duckdb data/damocles.duckdb.bak

# 2. Restore demo snapshot
cp data/damocles.duckdb.demo data/damocles.duckdb

# 3. Disable cron
sed -i 's/^STANDING_SCAN_CRON=.*/STANDING_SCAN_CRON=/' .env

# 4. Boot backend
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

## How to refresh the snapshot

After any further data-quality work, regenerate:

```powershell
# 1. Run the data-quality pass
uv run python scripts/w1_data_quality_pass.py

# 2. Stop backend (so the file isn't locked)
Get-NetTCPConnection -State Listen -LocalPort 8001 |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 3. Snapshot
Copy-Item "data\damocles.duckdb" "data\damocles.duckdb.demo" -Force
```

## Why this is in `.gitignore`

`data/*.duckdb*` is gitignored — operational data with vessel positions,
news clippings, AoI inferences. Don't commit the snapshot to the public
repo. Treat it as **the demo's most valuable single file** and keep a
copy on each of the demo + backup laptops in the W4-T4 pitch box.

## Verification after restore

Run the quality scan against the restored DB. The bar from W1 was:

- ≥80 % of a random 10-sample over water → currently **100 %**
- Mixed-source AoIs exist (multi-strand corroboration) → currently **6 AMBER, all mixed**
- AoI count between 30 and 90 → currently **80**

```powershell
uv run python scripts/aoi_quality_scan.py
```

If any of these regress after restore, do NOT proceed to demo without
investigating — the snapshot may have been overwritten.
