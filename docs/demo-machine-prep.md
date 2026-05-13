# Demo Machine — Cold-Boot Runbook
### W4-T4 · feeds the pitch box

The demo laptop is the most expensive single thing in the pitch. This
runbook is the procedure for taking a fresh-out-of-the-box Windows 11
machine and getting it to the state where opening one terminal and
running one command produces the demo. **Pin one machine. Do this once
per machine. Re-run [`preflight_demo.py`](../scripts/preflight_demo.py)
within 60 seconds of stepping on stage.**

---

## Hardware target

- 16 GB RAM minimum, 32 GB preferred (Vite + uvicorn + a browser with
  the dev tools open eats 10 GB before the LLM starts).
- 256 GB SSD (the DuckDB snapshot is 7.5 MB; the pain is npm and uv
  caches).
- One USB-C → HDMI dongle in a labelled ziplock taped to the lid.
- Bring **two** laptops to the pitch (primary + backup, both run this
  same procedure). The backup runs at the back of the room with the
  screen folded down — it's the cold-spare if the primary fails.

## Software baseline (one-time install)

```powershell
# From the project root, run:
.\scripts\setup_windows.ps1
```

The script handles:
1. **uv** (Python package manager). Fallback: `pip install uv`.
2. **Node.js 20+** prompt-only — the operator installs from
   nodejs.org if it's missing.
3. **Docker Desktop** prompt-only — required for Neo4j, but the demo
   works without it (DuckDB fallback handles every read path). Skip
   this on the demo machine; we don't want Docker eating background
   CPU during the pitch.
4. **`.env`** copied from `.env.example`. Operator fills in:
   - `GEMINI_API_KEY` (free at aistudio.google.com).
   - `STANDING_SCAN_CRON=` (empty — disables the cron, see below).
5. **Python deps** via `uv sync`.
6. **Greek spaCy model** (`el_core_news_lg`).

After this, the directory has everything except the **snapshot pin**.

## The snapshot pin — DO THIS LAST

The platform's data file is gitignored. Without pinning the W1 demo
snapshot, the analyst sees the *current* DuckDB state — which may be
a fresh empty store, an overnight scan with no RED AoIs, or anything
in between. The snapshot is the demo.

```powershell
# 0. Stop the backend if it's running.
Get-NetTCPConnection -State Listen -LocalPort 8001 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }

# 1. Back up the current DB (so you can roll back later).
Copy-Item "data\damocles.duckdb" "data\damocles.duckdb.bak" -Force -ErrorAction SilentlyContinue

# 2. Restore the demo snapshot.
Copy-Item "data\damocles.duckdb.demo" "data\damocles.duckdb" -Force

# 3. Disable the cron in .env (so the overnight scan can't surprise you).
#    Edit .env: STANDING_SCAN_CRON=     (blank value disables the scheduler)
```

This is the same procedure documented at [DEMO_RESTORE.md](DEMO_RESTORE.md);
that file is authoritative.

---

## The 2-minute cold-boot test

The demo machine passes W4-T4 when **cold boot → first slide → killer
scenario clickable** completes in **under 120 seconds**.

```
T+00:00  Hit the power button.
T+00:30  Windows login.
T+00:35  Open PowerShell at the project root.
T+00:40  Run: .\start.ps1
T+01:10  Backend ready on :8001 (the script tails until /health is green).
T+01:25  Frontend ready on :5173 (Vite hot-reload finished).
T+01:30  Open http://127.0.0.1:5173 in the browser.
T+01:45  Run: uv run python scripts/preflight_demo.py — should say ALL GREEN.
T+02:00  Open slide deck on the second screen.
```

If any beat in that sequence takes longer than the budget, find out
why **before** the pitch. The usual suspects:

- **uvicorn slow to bind.** Old `damocles.duckdb.wal` file hanging
  around. Delete it: `Remove-Item data\damocles.duckdb.wal -ErrorAction SilentlyContinue`.
- **Vite slow to come up.** First `npm run dev` after dep changes
  takes ~30s to pre-bundle. Make sure deps are warm in advance:
  `cd frontend && npm install`.
- **Frontend says "Network Error" in the audit chip.** Backend isn't
  ready yet OR the Vite proxy doesn't see it. Most often: backend
  bound to `::1` only — confirm `start.ps1` passes `--host 127.0.0.1`.

## Pre-flight (60 seconds before the pitch)

```powershell
uv run python scripts/preflight_demo.py
```

Expected: **ALL GREEN**. Nine checks, all bright. If any one fails,
**do not** walk on stage with the laptop — fix it first.

The nine checks (in order):

1. Backend reachable on :8001 (HTTP 200 on /health within 10s).
2. `DEMO_MODE=true` in the running process (so tamper/swap endpoints are live).
3. Frontend reachable on :5173.
4. Canonical brief cache has ≥6 entries (one per RED AoI).
5. The W2-T1 demo target (`aoi-17854afce5` — North Heraklion Zone) has
   a cached brief.
6. ≥6 RED AoIs visible in the live AoI query.
7. Audit chain verifies green.
8. ≥80 AoIs available for the scan-cinema WS replay.
9. `data/damocles.duckdb` present and non-empty (i.e. the snapshot
   was actually pinned, not a fresh empty file).

## Failure modes during pre-flight, with fixes

| Failed check | Most likely cause | Fix |
|---|---|---|
| 1 — backend unreachable | Process died or port grabbed | `.\start.ps1` again; check Get-NetTCPConnection for 8001 squatters |
| 2 — DEMO_MODE off | `.env` was reset | Edit `.env`, set `DEMO_MODE=true`, restart backend |
| 3 — frontend unreachable | Vite crashed on a hot-reload | `cd frontend && npm run dev -- --host 127.0.0.1 --strictPort` |
| 4 — canonical cache empty | Snapshot has briefs but a different DB file is in play | Re-run snapshot pin (above); check `data/damocles.duckdb` mtime |
| 5 — demo target missing | Same as 4, plus pre-cache pass needed | `uv run python scripts/pre_cache_briefs.py` |
| 6 — <6 RED AoIs | Wrong DB file (live state, not snapshot) | Re-pin snapshot |
| 7 — audit chain not green | Someone clicked Tamper byte and didn't restore | `curl -X POST http://127.0.0.1:8001/api/audit/_restore` (works across restarts via on-disk `.demobak`) |
| 8 — <80 AoIs streamable | Wrong DB file | Re-pin snapshot |
| 9 — duckdb missing | Snapshot pin step was skipped | See "The snapshot pin" above |

## What's allowed to be on the demo machine

**Allowed:** the project repo, the snapshot, the slide deck (PDF), an
open browser at `localhost:5173`, an open PowerShell at the project
root, and the speaker's water bottle.

**Not allowed:** Slack, Teams, email, GitHub Desktop, OBS, screen
recorders the operator didn't personally start, browser tabs not
pointing at localhost. Every one of those is a notification that can
land on the projection screen during the pitch.

Quarantine procedure: disable notifications for **every** other app
in Settings → System → Notifications, then close them all. Reboot.
Confirm the only thing in the system tray is what's needed.

## Per-rehearsal reset

After every rehearsal (W4-T2, W5-T1), reset the demo state:

```powershell
# 1. Restore the audit chain in case anyone clicked Tamper byte.
curl -X POST http://127.0.0.1:8001/api/audit/_restore

# 2. Confirm everything is green again.
uv run python scripts/preflight_demo.py
```

If the restore returns *"no tamper backup on record — nothing to
restore"*, the chain is already clean; that's a 400 you can ignore.

If the chain is somehow broken with no `.demobak` available, fall back
to the chain-rebuild one-liner in [audit.md](audit.md) §"Recovery"
(this is a last resort — `audit_log.jsonl` corruption usually means a
deeper bug worth investigating, not papering over).

---

## Acceptance (matches GOLD_MEDAL_PLAN W4 checkpoint)

This runbook passes when:

- Cold-boot test fits in 120s on the actual demo laptop.
- `preflight_demo.py` returns ALL GREEN on the actual demo laptop.
- The snapshot-pin procedure has been executed **after** the most
  recent `git pull` (in case anything in `data/` was rebuilt).
- The backup laptop produces the same ALL GREEN.
- Both laptops are physically present in the pitch room with
  charged batteries and the HDMI dongles taped to their lids.

---

*Last revised: 2026-05-13. Authority: `GOLD_MEDAL_PLAN.md` W4-T4.
Companion: [`DEMO_RESTORE.md`](DEMO_RESTORE.md), [`demo-script.md`](demo-script.md).*
