# Damocles — Gold Medal Plan
### EYP National Security Innovation Challenge 2026 · June pitch · ~5 weeks left

**The single thing this plan optimises for.** Land three sentences in the judges'
notebooks before they leave the room:

> 1. *"It runs sovereign — one env var flips to local Ollama, no foreign API
>    calls. They demoed the switch live."*
> 2. *"The audit chain isn't a feature, it's a guarantee. They tampered with
>    one byte on stage and the chip flipped red."*
> 3. *"Every claim in every brief clicks through to its raw source. Not a
>    summary of a summary."*

Everything in this plan exists to engineer those three sentences.

---

## Definition of done — what "gold medal" means in code

| Criterion | How we test it |
|---|---|
| Cold-open shows ≥3 well-named RED/AMBER AoIs, all geographically defensible (no inland "vessels"). | Random click-test on 10 polygons from a fresh scan; ≥9 pass a "would I defend this to a judge" sniff test. |
| The killer scenario runs end-to-end in ≤90s with five clicks, no LLM call on the critical path. | Stopwatch a clean dry run. Median over 5 runs <90s. |
| Tamper-and-restore demo works in ≤20s, with the audit chip clearly switching state. | Visible state change captured on slow-mo video. |
| Local-LLM swap is demonstrable in ≤30s without restarting the app. | Live `LLM_PROVIDER` toggle that re-routes the next agent call to Ollama. |
| Five hostile questions have rehearsed paragraph answers, delivered without filler words. | Mock-panel session with three external readers. |
| Zero network calls to foreign services after the local-swap is demoed. | Wireshark capture during the final 3 minutes; no outbound traffic except to localhost. |
| All of the above runs from a pinned DuckDB snapshot and a disabled cron. | `data/damocles.duckdb.demo` exists, cron flag is off in `.env.demo`. |

If we hit all seven, gold is the median outcome.

---

## Risk register — what could lose this for us

| # | Risk | Likelihood | Blast radius | Mitigation |
|---|---|---|---|---|
| R1 | Venue WiFi blocks Gemini or Carto glyphs mid-demo | Medium | Demo dies | Demo from Ollama. Self-host glyphs. |
| R2 | Live cron triggers during pitch, rewrites our seeded RED AoI | Low | Story unravels | Disable cron in `.env.demo`. Pin DuckDB. |
| R3 | "Why is there a vessel inland?" question lands on day 1 | High → Low after data fix | Confidence collapses | Ship SAR/water mask in week 1. |
| R4 | LLM hallucinates a citation that doesn't resolve | Low (validator catches) | One bad brief | Pre-cache all RED briefs; never live-fire on stage. |
| R5 | A judge tries to break the citation chain by clicking weird citations | Medium | One click looks broken | Click-test every chain in every cached brief. |
| R6 | The Devil's Advocate counter sounds either too tame or unhinged | Medium | Pitch deflates | Hand-tune the prompt + cache the brief; do not regenerate live. |
| R7 | Greek opening monologue fumbled by the speaker | Medium | First impression damaged | Memorise it. Backup card. Rehearse 50×. |

Each P0 below maps to one of these risks. Order is non-negotiable.

---

## Phase plan

```
WEEK 1  (May 13–19)   Data quality unblock        — fixes R3, prereq for everything
WEEK 2  (May 20–26)   The killer scenario         — fixes R5, encodes the medal moment
WEEK 3  (May 27–Jun 2) Tamper + sovereignty cinema — fixes R1, R4
WEEK 4  (Jun 3–9)     Pitch deck + Q&A drill      — fixes R6, R7
WEEK 5  (Jun 10–16)   Rehearsal + buffer          — soak time, last polish
PITCH:  Jun 17±
```

We do **not** add new sensors, new map layers, or new viz types after
end-of-week 2. Anything not earning a place in the killer scenario gets
killed. See §"Kill list" below.

---

## WEEK 1 — Data quality unblock (May 13–19)

The whole demo rests on the analyst clicking a polygon and not flinching
when they see what's inside. Today the click 50% of the time lands on a SAR
false-positive over Phthiotis farmland (see [`AOI_QUALITY_REPORT.md`](AOI_QUALITY_REPORT.md)).
Fix this first or nothing else matters.

### W1-T1 · Land/water masking for SAR · 4h

**What.** Wrap `backend/sensors/cfar.py` output with a water-surface filter
using the existing `data/geojson/aegean_sea.geojson`, `ionian_sea.geojson`,
`greek_eez.geojson`. Any detection whose `(lat, lon)` is > 500 m inland of
the unioned water polygon is either dropped or stored with `is_water=false`
in `raw_sar` and excluded from the AoI agent's input.

**Acceptance.**
- After re-scan, `SELECT count(*) FROM raw_sar WHERE is_water=true` is ≥ 60 %
  of pre-mask count (we keep the real water detections).
- A spot-check of 5 random `raw_sar` rows with `is_water=false` confirms each
  is over land in QGIS or Google Maps.
- Re-running [`aoi_quality_scan.py`](../scripts/aoi_quality_scan.py) shows
  fewer than 1 in 10 AoIs landing on dry land.

**Owner.** backend dev. **Risk if skipped.** R3 lands on demo day.

### W1-T2 · Multi-source escalation rule · 2h

**What.** In [`backend/agents/aoi_agent.py:_build_aoi`](../backend/agents/aoi_agent.py),
after threat-grade derivation, downgrade to GREEN if the cluster's
`dominant_types` contains only one entry. Force the platform to require
cross-strand corroboration before it shouts.

**Acceptance.**
- After re-scan, any AoI with `threat_grade in (RED, AMBER)` has
  `len(dominant_types) >= 2` (verified by [`aoi_quality_scan.py`](../scripts/aoi_quality_scan.py)).
- The 1/10 "STRONG" Athens-Lycabettus pattern (vessels + news) survives the
  re-scan as AMBER.

### W1-T3 · Tune for at least 3 RED AoIs · 3h

**What.** After T1 + T2, run the full scan and count REDs. If 0, lower the
`fusion.py` Goldstein-scale / fatalities / corroboration thresholds *only as
much as needed* to get at least 3 REDs from the Greek scan window. Document
each threshold change.

**Acceptance.**
- `SELECT count(*) FROM aoi WHERE threat_grade='RED'` ≥ 3 from a real scan,
  not seeded.
- Each RED is geographically + topically defensible (you can articulate
  *why* it's RED in one sentence).

### W1-T4 · Re-scan + freeze · 1h

**What.** Run one full Greek scan with the new thresholds, snapshot DuckDB
to `data/damocles.duckdb.demo`, document the restore procedure in
[`docs/operations.md`](operations.md).

**Acceptance.**
- Snapshot exists. Restore command works. Cron is OFF for `damocles.duckdb.demo`.

### W1-T5 · DNA polish · 4h

**What.** Now that the data has actual cross-strand pairs, the temporal
helix [I built last week](AOI_QUALITY_REPORT.md#7--dna-visualization-works-but-visualizes-nothing-right-now)
will show non-zero base pairs. Add a "corroboration intensity" badge that
counts the strongest rung's source count ("max 7-source corroboration").
Re-screenshot for the pitch deck.

**Acceptance.** A screenshot of the DNA tab for the cleanest RED AoI shows
≥2 base-pair rungs, with the thickest one visibly heavier than the thinnest.

### W1 checkpoint — Friday May 17

Re-run the audit. The bar:

- 30 ≤ AoI count ≤ 90 (was 134; fewer-but-cleaner is correct).
- ≥3 RED.
- ≥80 % of a random 10 sample pass the "would I defend this" test.
- DNA helix renders non-zero base pairs on the cleanest RED.

If we miss the bar, week 1 extends and week 5 (buffer) compresses. Do not
move to week 2 until W1 passes.

---

## WEEK 2 — The killer scenario (May 20–26)

One AoI. Five clicks. 90 seconds. Choreographed. Rehearsed.

### W2-T1 · Pick the demo AoI · 1h

**What.** From the cleaned fact store, identify the single most demonstrable
RED AoI. Criteria, ranked: (a) physical + information sources both present,
(b) cross-strand base pairs ≥ 2, (c) Greek-named with a recognisable
toponym, (d) topic with operational salience to EYP (border, AIS-dark,
information operations, GPS jamming).

**Acceptance.** Written 200-word "scene description" of the AoI in
[`docs/demo-script.md`](demo-script.md) §"Killer scenario."

### W2-T2 · Pre-cache the canonical brief · 4h

**What.** Run the full 4-agent pipeline for the chosen AoI. Hand-review the
output. If the BLUF or Devil's Advocate phrasing is off, re-run with a
prompt tweak until it's tight. Persist the result with a `is_canonical=true`
flag in DuckDB. The `/api/aoi/{id}/brief` endpoint returns the canonical
version when present, skipping the live pipeline.

**Acceptance.**
- Click → brief renders in <500 ms (verified by browser DevTools network tab).
- BLUF reads tight to a non-technical reader (test with one external person).
- Devil's Advocate phrasing is sharp ("Evidence is consistent with…",
  `devil_confidence ≥ 0.3`).
- 5 click-tests against all citations resolve to evidence panels.

### W2-T3 · Choreography spec · 2h

**What.** Write the exact 5-click sequence in
[`docs/demo-script.md`](demo-script.md), with timing per click and what the
speaker says during each. Example:

```
T+00:00  Click RED polygon "Λεκάνη Λήμνου"
T+00:02  Map flies. Brief tab populated. Speaker: "Damocles ran this brief at
          4 a.m. Read the BLUF."
T+00:14  Click the first BLUF citation chip (aoi://). Polygon highlights
          on map. Speaker: "This claim is grounded in the AoI itself."
T+00:22  Click "vessel://" citation. SAR tile opens in evidence modal.
          Speaker: "Eight minutes earlier the satellite saw this. AIS was
          off."
T+00:38  Click "news://" citation. Greek translation alongside the
          Kathimerini article. Speaker: "Twenty minutes later the press
          knew."
T+00:54  Switch to DNA tab. Speaker: "Physical signal left, information
          right, six base pairs connect them."
T+01:10  Switch to Audit Chain panel. Speaker: "Every step of that is
          hash-linked. Watch." [moves to W3-T1 tamper demo]
```

**Acceptance.** Doc exists. Speaker has rehearsed it 5× and the median time
is 80–90s.

### W2-T4 · Click-test every citation · 3h

**What.** Programmatically click every citation chip in the canonical
brief, capture the resulting evidence modal, verify it renders correctly
(image loads, text non-empty, no React error boundary). Extend
[`scripts/e2e_screenshots.py`](../scripts/e2e_screenshots.py) with a
`scenario_canonical_brief_clicks` function.

**Acceptance.** Script runs, all citations green-light, screenshot per
citation exists in `screenshots/canonical/`.

### W2-T5 · Greek opening monologue · 4h

**What.** Write, translate, and memorise a 60-second cold-open monologue.
Draft:

> "Στις 3 το πρωί της περασμένης Πέμπτης, ένα δεξαμενόπλοιο εισήλθε στην
> ελληνική ΑΟΖ με ανενεργό AIS. Η EYP το έμαθε από δημοσιογραφικά
> πρακτορεία στις 11:14. Το Damocles το είδε στις 3:22, οκτώ λεπτά μετά
> την λήψη του δορυφορικού καρέ. Δεν περιμένει ερώτηση. Δεν στέλνει δεδομένα
> εκτός Ελλάδας. Και κάθε πρόταση κάθε αναφοράς οδηγεί κρυπτογραφικά πίσω
> στην πηγή της. Σήμερα θα σας δείξω πώς."

**Acceptance.** Speaker delivers it in <65 s without filler, three times in
a row, recorded.

### W2-T6 · Kill the "Vessel · Vessel · Vessel" wall · 2h

**What.** The Graph panel still has type-monoculture labels for some AoIs
even after W1 fixes. Verify with the canonical AoI that the node-label
diversifier from the post-fix E2E is working; if not, finish it.

**Acceptance.** Graph panel for the canonical AoI shows ≥3 distinct labels.

### W2 checkpoint — Friday May 24

Run the killer scenario from scratch in front of three external readers.
Bar:

- They understand each click without asking what just happened.
- BLUF reads as "operational language," not "marketing language."
- At least one of them says "wait, you can click that?" — surprise = win.
- Median scenario time across 5 runs <90s.

---

## WEEK 3 — Tamper + sovereignty cinema (May 27–Jun 2)

### W3-T1 · Live tamper demo · 6h

**What.** Add three dev-mode-only endpoints + UI:

1. `POST /api/audit/_tamper` (gated on `settings.DEMO_MODE`) — flips a byte
   in a chosen audit entry's `chain_hash`, persists.
2. `POST /api/audit/_restore` — restores from in-memory backup.
3. Frontend: in DEMO_MODE, expose "Tamper" + "Restore" buttons next to
   "Verify chain" in the AuditLog header. Confirmation modal before action.

**Visual flow.**

```
[Green chip · 92/92 verified] · [Verify] [Tamper] [Restore]
       ↓ click Tamper, confirm
[Green chip · 92/92] · [Tamper changed entry #47] · [Verify] [Tamper] [Restore]
       ↓ click Verify
[RED chip · TAMPER @ #47] · [Verify] [Tamper] [Restore]
       ↓ click Restore
[Green chip · 92/92] · [Restored] · [Verify] [Tamper] [Restore]
       ↓ click Verify
[Green chip · 92/92 verified]
```

**Acceptance.** Sequence completes in <20s with clearly visible state
changes. Captured in slow-mo video for the pitch deck.

### W3-T2 · Live LLM provider swap demo · 4h

**What.** Add a tiny dev-mode-only switcher in the SystemPill: a click on
the LLM dot opens a menu `[Gemini] [Ollama]`. Selecting flips
`app.state.executor.llm` to the other provider for the next call. No
restart. The next brief generation uses the new provider.

**Acceptance.** Demo: trigger a fresh AoI brief on Gemini, see it land.
Click pill, swap to Ollama. Trigger another brief, see it land from local.
The SystemPill shows `● ollama` after the swap. <30s.

This is the sovereignty cinema. *"One env var, one click. Same brief
shape. No external traffic. Watch."*

### W3-T3 · Self-host Carto glyphs · 2h

**What.** Download the dark-matter glyph PBFs once, vendor under
`frontend/public/maplibre-glyphs/`, patch the MapPanel style to point at
`/maplibre-glyphs/{fontstack}/{range}.pbf`. Removes the CORS error and the
foreign dependency.

**Acceptance.** Map text labels render. Console clean. No `cartocdn.com`
requests in the network panel.

### W3-T4 · WebSocket scan cinema · 4h

**What.** When the analyst clicks "Run scan now," polygons should pop in on
the map as the scan progresses, driven by the existing `ProgressStream`
WebSocket events. Add an `aoi_added` event type emitted from the AoI agent
as each AoI is persisted. Frontend listens and re-fetches AoIs (or just
appends the new one) with a brief flash animation.

**Acceptance.** Visible polygon-by-polygon animation during a live scan.
Cinematic mode for stage.

### W3-T5 · Production-story slide · 3h

**What.** One slide. Topology diagram. Bullet points: single server, air-gap
option, 5-analyst-per-week onboarding, schema migration plan, open source.
No demo dependency — this slide lives in the pitch deck, shown for ~30s
near the close.

**Acceptance.** Slide ready, reviewed by one external reader, fits in
1 minute of pitch time.

### W3 checkpoint — Friday May 31

- Tamper + restore choreography works in <20s on a fresh machine boot.
- LLM swap works in <30s, brief renders from Ollama on stage equipment.
- Map renders without internet egress to Carto.
- Pitch deck has 4 slides: cold open, killer scenario, tamper, production.

---

## WEEK 4 — Pitch deck + Q&A drill (Jun 3–9)

Stop building. Start defending.

### W4-T1 · Court-room Q&A drill — five questions · 6h

**What.** For each of these five questions, write a single-paragraph answer
and rehearse delivery without filler words. The questions:

1. **"What if the LLM hallucinates a citation that doesn't exist?"**
   → *Server-side citation validator at
   [`supervisor_agent.py:_validate_supervisor_output`](../backend/agents/supervisor_agent.py)
   rejects any node ID not present in the AoI's evidence set. The AoI-id-first
   BLUF rule is enforced server-side, not prompt-side. If a citation slips
   through, the brief is rejected and re-generated once. If it fails again,
   the AoI gets no brief — the platform refuses to publish an unsupported
   claim.*

2. **"How is this different from Palantir Gotham?"**
   → *Three structural differences. One: Palantir AoIs are configuration —
   analysts tell it what to watch. Damocles AoIs are inference — the system
   tells analysts what changed overnight. Two: every brief here is
   hash-chained; tampering is detectable, and we'll demonstrate that in a
   moment. Three: sovereignty — Palantir requires their cloud and a
   $30 million license. Damocles runs on one Greek server with one env var
   switch to a fully local LLM.*

3. **"What does this cost EYP to run?"**
   → *Hardware cost only. One server in your existing infrastructure.
   Zero per-seat licensing. Greek-hosted models if the policy requires it.
   The full source is open and audit-ready. Operationally we estimate
   five analysts onboarded per week with the existing documentation.*

4. **"Who owns the data, and where does it live?"**
   → *DuckDB file on disk under `data/`. Greek soil. The Merkle audit log
   is local JSONL plus mirrored Neo4j edges, both in the same data
   directory. No external transmission in `LLM_PROVIDER=ollama` mode. The
   only outbound calls in development mode are to Gemini, and we can flip
   that off live.*

5. **"What stops a hostile actor from poisoning your Telegram input?"**
   → *Three layers. The Linguist agent normalises by source reliability
   (channels are scored on a Reputation tier the analyst can adjust).
   The Devil's Advocate runs against the brief output, not just the inputs,
   so a coordinated input attack still has to survive a counter-narrative
   pass. And finally, the audit chain means an after-the-fact analysis
   can identify the contaminating entry to the second and trace its
   downstream brief impact. We can't prevent prompt injection in absolute
   terms — nobody can — but we can make it discoverable.*

**Acceptance.** Each answer delivered in ≤60s without rehearsal cards,
recorded.

### W4-T2 · Full dry run × 5 with hostile panel · 8h

**What.** Recruit three readers (one Greek-speaker, one intelligence/military
background, one technical). Run the full 5-minute pitch + Q&A at least
five times. After each run, write down what felt fragile.

**Acceptance.** By the fifth run, none of the readers can find a question
that stumps the speaker for >5s.

### W4-T3 · Final pitch deck · 4h

**What.** 6 slides, 5 minutes spoken:

1. Cover + Greek opening (the monologue) — 60s
2. The killer scenario — 90s
3. Tamper + sovereignty cinema — 60s
4. Devil's Advocate + DNA strands — 45s
5. Production story (the W3-T5 slide) — 30s
6. Q&A invitation — 15s

**Acceptance.** Deck reviewed by all three readers. Each slide ≤4 bullets.

### W4-T4 · Demo machine prep · 4h

**What.** Dedicate one laptop as the demo machine. Install everything from
scratch using `scripts/setup_windows.ps1`. Pin DuckDB to the W1 snapshot.
Disable cron. Test the full pitch from cold-boot. Bring this laptop to
every rehearsal.

**Acceptance.** Cold-boot → app running → first slide → killer scenario
runnable in <2 minutes.

### W4 checkpoint — Friday Jun 7

- Five Q&A answers recorded.
- Pitch deck final.
- Demo machine works from cold-boot.
- Dry run #5 passes with no readability gaps.

---

## WEEK 5 — Rehearsal + buffer (Jun 10–16)

No new features. No new code unless it's a regression fix.

### W5-T1 · Daily dry-run · 2h × 7 days

**What.** Every day, one full pitch including Q&A, at the same time of day
the actual pitch will happen. Record each run.

**Acceptance.** Day-over-day improvement in cadence; no day worse than the
previous.

### W5-T2 · Regression sweep · 4h

**What.** Re-run [`e2e_screenshots.py`](../scripts/e2e_screenshots.py) and
[`aoi_quality_scan.py`](../scripts/aoi_quality_scan.py). Both must produce
the same OK counts as the last green run. If anything regresses, fix it
that day, don't ship anything else.

**Acceptance.** Both scripts green; results filed under `screenshots/preflight/`.

### W5-T3 · Failure-mode rehearsal · 3h

**What.** Deliberately break things and rehearse the recovery:
- Disconnect WiFi mid-pitch → swap to Ollama, show the swap.
- Pretend the projector dies → show the slide deck on the laptop directly.
- Pretend a citation click breaks → say "I'll show you the raw evidence
  directly" and click into the evidence modal a different way.

**Acceptance.** All three recoveries take <15s and don't break narrative.

### W5-T4 · The pitch box · 2h

**What.** Pack what we bring on stage:
- Demo laptop (W4-T4)
- Backup laptop with same image
- HDMI + USB-C + DisplayPort adapters
- Wired mouse
- Two printed copies of the cold-open monologue (one for speaker, one
  backup)
- Two printed copies of the Q&A answer cards
- Phone hotspot pre-configured as WiFi fallback (only used if local-LLM
  mode somehow fails)

**Acceptance.** Box exists, contents inventoried, both laptops boot to
demo state in <2 min.

---

## Kill list — what we will NOT build

Naming what we won't do is half the plan. Each of these has been considered
and rejected for a reason.

| Idea | Reject because |
|---|---|
| 11 sensors all wired into the killer scenario | The pitch survives on 3-4. Breadth shows in the written submission, depth wins the stage. |
| Real-time Telegram subscription | If it goes down mid-pitch, narrative breaks. Use cached evidence. |
| Polished 3D DNA helix | The 2D version is finally meaningful after W1; 3D is sci-fi vibes without new information. |
| Analyst-drawn AoI flow in the killer scenario | Already supported; rehearsing it adds rehearsal load. Mention in 10 seconds, don't demo. |
| Multi-language support beyond EL/EN | Out of scope for EYP-Greek audience. |
| Mobile/tablet view | Pitch is on a laptop projector. |
| OAuth login | Not a feature judges care about. Defer to deployment. |
| Per-row "mark reviewed" on triage | UX nicety, no medal lift. |
| Keyboard shortcuts beyond Esc | One shortcut beyond Esc is one slide of explanation we don't have time for. |
| New i18n entries beyond fixing the audit chip | Diminishing returns; EL+EN are enough. |
| WebSocket scan cinema if it's not done by end of W3 | Cut it. The standing-scan story is told in the brief, not in animation. |

If a teammate proposes adding one of these between now and pitch day, the
answer is no and this list is the artifact.

---

## Hand-off — what each week ships

| Week | Ships | Owner notes |
|---|---|---|
| W1 | Clean fact store · DNA shows real base pairs · `damocles.duckdb.demo` snapshot | Backend + AoI agent work. |
| W2 | Choreographed killer scenario · Greek monologue · pre-cached canonical brief | Backend (cache) + frontend (script) + speaker prep. |
| W3 | Tamper demo · LLM provider swap · self-hosted glyphs · 4-slide deck | Backend + frontend + slides. |
| W4 | 5-answer Q&A drill · final 6-slide deck · demo machine ready | Speaker prep + ops. |
| W5 | 7 daily dry runs · pitch box packed · regression-clean | Discipline week. |

---

## How I (Claude) propose to help

For each week I can:

- **W1** — Implement the SAR/water mask and the multi-source rule. Re-run
  the scan. Re-run the audit. Produce the W1 checkpoint report.
- **W2** — Build the canonical-brief cache and the click-test extension to
  the E2E script. Help wordsmith the Greek monologue and the BLUF.
- **W3** — Build the tamper endpoint + UI, the LLM swap, the glyph
  self-hosting, the WebSocket cinema.
- **W4** — Write the Q&A answers (we have a draft above), build slide
  outlines, structure the dry-run scoring sheet.
- **W5** — Run the regression sweep, audit the pitch box, provide a
  per-day rehearsal log template.

If you want me to start, the unambiguous first stroke is **W1-T1: ship the
SAR/water mask**. Every other week depends on that landing this week.

---

*Plan version: 1.0. Living document — amend by PR, not by hallway
decision. Source of truth for "are we on track" at every Friday checkpoint.*
