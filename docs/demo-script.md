# Damocles — Pitch Demo Script
### EYP National Security Innovation Challenge 2026 · June pitch

**Format.** 5 minutes spoken + 5 minutes Q&A. One operator at the keyboard,
one speaker on the floor. **Demo runs from the pinned `damocles.duckdb.demo`
snapshot with the cron disabled** (see [`DEMO_RESTORE.md`](DEMO_RESTORE.md)).

**Target AoI.** `aoi-17854afce5` — **North Heraklion Zone / Βόρεια Ζώνη Ηρακλείου**.
6 RED total, 5 in reserve. Why this one:

- The brief tells a full operational arc: ambiguous BLUF → sharp
  Devil's Advocate → **PRIORITY recommendation** (request HCG radar logs).
- 12 SAR-detected vessels in Cretan waters + 6 news events including a
  hot-Goldstein single-source claim of an Israeli naval intervention.
- Geographically Greek (Crete coast) — no awkward "polygon over Turkey"
  question.
- The Devil's voice contradicts the source in three sentences — the
  rarest, most demonstrative output the multi-agent system produces.
- Brief is pre-cached → renders in ~5 ms on click. Zero LLM call on
  the critical path.

---

## The narrative arc (memorise this, not the script)

The pitch is **one sentence**, repeated through six demonstrations:

> *"Damocles doesn't tell the analyst the answer. It tells her what to ASK NEXT.
> And it shows her how it asked the same question of itself first."*

Everything that follows exists to land that.

---

## Spoken timing (5 minutes hard cap)

```
T+00:00  Greek opening monologue (60s, see W2-T5)
T+01:00  Cold-open: the morning view
T+01:30  Click RED polygon → brief renders
T+02:00  Citation chain demonstration (clicks 3-5)
T+03:00  Devil's Advocate moment        (click 6)
T+03:45  Audit chain + Verify           (click 8, W3-T1 build)
T+04:15  Local-LLM swap demo            (W3-T2 build)
T+04:45  Production-story slide         (W3-T5 build)
T+05:00  Stop. Q&A.
```

---

## Click-by-click choreography — the 90-second core

The Greek opening sets the stage. Then the speaker says one English line:
*"Now I'll show you what she sees when she sits down."* The operator
already has the app open at `http://127.0.0.1:5173/`.

### Click 1 — T+01:00 — Open AoI from the triage list

```
ACTION    The triage list is already visible (cold-open default).
          Operator clicks the row "Βόρεια Ζώνη Ηρακλείου" / "North Heraklion Zone".
EXPECTED  Map flies to (35.36°N, 25.10°E) — north Crete coastline visible.
          BriefPanel opens to the Brief tab (auto-fire) and loads in <500ms
          (canonical cache hit).
SPEAKER   "Damocles ran this brief at 6 AM, before anyone was awake. RED.
          North Heraklion. Let me read the headline."
TIMING    2s
```

### Click 2 — T+01:30 — BLUF appears, speaker reads aloud

```
ACTION    Speaker reads the BLUF section header aloud.
EXPECTED  Visible text:
          "A single-source report of a violent Israeli naval intervention
           against a Gaza-bound flotilla in the Βόρεια Ζώνη Ηρακλείου
           carries a high risk of being a localized information operation
           or a geocoding error due to a total lack of corroborating
           maritime or local signals."
SPEAKER   Reads BLUF verbatim, then pauses two seconds before:
          "Every word of this is hash-chained to a source. Watch."
TIMING    20s
```

### Click 3 — T+01:50 — Click the BLUF's first citation chip (aoi://)

```
ACTION    Click the first citation chip in BLUF (the aoi-... pill,
          amber-bordered — visually distinct from other citations).
EXPECTED  Map highlight: polygon outline pulses brighter.
          GraphPanel: AoI node activates, member edges light up.
SPEAKER   "Click. This claim is grounded in the AoI itself — the polygon
          on the map. Every brief Damocles writes is anchored to a region
          it can defend on a map."
TIMING    15s
```

### Click 4 — T+02:05 — Click a "Vessel" citation

```
ACTION    Click any of the source-event citation chips on a KEY_JUDGMENT
          section that points at a SAR vessel detection.
EXPECTED  Map flies closer; Evidence modal opens showing SAR detection
          metadata: tile ID, length, AIS status ("dark"), timestamp.
SPEAKER   "Click. The satellite saw a 30-metre vessel here, with no AIS
          broadcast. SAR confirms it exists. AIS says it doesn't want to
          be seen. Damocles calls that 'dark'."
TIMING    25s
```

### Click 5 — T+02:30 — Click a NewsEvent citation

```
ACTION    Click one of the news citation chips (preferably the
          ideologically-coded one with Goldstein -7).
EXPECTED  Evidence modal opens with article preview (og:image + headline +
          source name). Goldstein scale visible.
SPEAKER   "Click. The information signal. Single source. Goldstein
          minus 7 — strongly negative coding. That's the data point that
          escalated this to RED."
TIMING    20s
```

### Click 6 — T+02:50 — The Devil's Advocate moment

```
ACTION    Scroll down (or click the DEVILS_ADVOCATE section header).
EXPECTED  Rose-bordered section visible, devil-confidence chip showing 0.85.
SPEAKER   Reads aloud:
          "The primary assessment relies exclusively on a single,
           ideologically driven news report; the total absence of
           Greek-language signals or official alerts regarding a
           'brutalization' in Greek waters strongly suggests the event
           did not occur as described."
          Then pauses two seconds:
          "Damocles flagged this as RED. It then argued against itself.
          The institution doesn't have to ask 'did we double-check?' —
          the system already did, and showed its work."
TIMING    35s
```

### Click 7 — T+03:25 — The Recommendation

```
ACTION    Scroll to RECOMMENDATION section (emerald-bordered).
EXPECTED  Visible: "PRIORITY" urgency chip + recommendation text:
          "Request immediate Hellenic Coast Guard (HCG) radar logs for
           the North Heraklion Zone to confirm or deny the presence of
           unidentified surface contacts at the reported time."
SPEAKER   "And here's the difference between Damocles and a noise-maker.
          The Devil's Advocate didn't say 'ignore.' It said 'go ask the
          Coast Guard right now.' PRIORITY. The brief tells the analyst
          what to ASK NEXT — never claims to know the answer."
TIMING    20s
```

---

## The framing line (closes the 90-second core)

After Click 7, speaker pauses, makes eye contact with the panel, then:

> *"Every other intelligence platform tells the analyst what to think.
> Damocles tells her what to look at, what to doubt, and what to ask next.
> That is the difference. The architecture institutionalizes the
> second thought. Watch how."*

Transition to the audit-chain demo (Click 8+) — storyboarded as part of W3.

---

## State the demo machine must be in

Before stepping on stage:

1. ✅ Backend running on `127.0.0.1:8001`, healthy.
2. ✅ Vite dev server on `127.0.0.1:5173`.
3. ✅ DuckDB pinned to `damocles.duckdb.demo` (run [`DEMO_RESTORE.md`](DEMO_RESTORE.md) if not).
4. ✅ Six RED AoIs visible in the triage list, **North Heraklion Zone**
   sorted to the top (it has the highest event count among REDs).
5. ✅ Canonical brief cache verified: `GET /api/aoi/canonical/_list` returns
   ≥6 items. Cached calls return in <50 ms.
6. ✅ MapLayerPanel closed by default (so map is the first impression).
7. ✅ Language toggle visible in topbar — set to **EL** for the opening
   monologue, switch to EN before Click 4.
8. ✅ Audit chip showing green; verify will be demonstrated in W3.

## Failure-mode rehearsals (W5-T3 ahead of time)

What happens if:

- **Wifi dies mid-demo.** All canonical briefs are served from local
  DuckDB. AoI labels render from `frontend/public/maplibre-glyphs/`
  (W3-T3, vendored) so no CDN call is needed for text. The satellite
  raster is the only outbound dependency — toggle MapLayerPanel off it
  and dark-matter loads from CARTO (vector tiles still external, but
  the demo's primary basemap is satellite).
- **LLM service is down.** Cached briefs don't call the LLM. The "swap
  to Ollama" demo at T+04:15 (W3-T2) flips the SystemPill's model
  segment to `llama3.1:8b` — clicking the segment fires
  `POST /api/system/llm/switch`, no restart required.
- **Audit chain demo.** T+03:45 — operator clicks "Tamper byte" in the
  AuditLog header (W3-T1). The verdict flips red ("TAMPER detected at
  index N"). Speaker pauses, then operator clicks "Restore" → "Verify
  chain" → green. The whole sequence is <5 seconds.
- **Speaker forgets a line.** The brief is on screen — read it aloud
  directly. The platform's voice can carry the demo if the human stumbles.
- **A click misses.** Esc returns to the triage list (W1 EscToDeselect
  handler). Recover in two clicks max.

---

## Acceptance criteria (matches GOLD_MEDAL_PLAN W2 checkpoint)

This script passes the W2 bar when:

- Median time across 5 full runs is <90 s for the click-by-click core.
- External readers (3 of them) understand each click without asking
  "what just happened?"
- At least one reader says "wait, you can click that?" — surprise = win.
- The Devil's voice is the moment that lands hardest. If the readers
  remember only one thing, it should be that.

If those four are true after a Friday checkpoint, we're on the gold
medal track for W2.

---

*Last revised: 2026-05-13. Authority: `GOLD_MEDAL_PLAN.md` W2.*
*Companion docs: [`DEMO_RESTORE.md`](DEMO_RESTORE.md) (machine state),
[`AOI_QUALITY_REPORT.md`](AOI_QUALITY_REPORT.md) (data provenance).*
