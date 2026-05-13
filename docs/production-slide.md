# Production-Story Slide
### W3-T5 · pitch deck T+04:45 · feeds the close

The pitch has five minutes. Four go to the live demo. The fifth is for
**this one slide** — the answer to *"OK, what happens if we say yes."*

This doc is the slide's source-of-truth. The deck designer pulls the
bullet list verbatim onto a single dark slide; the speaker reads from
the script below.

---

## The slide (one frame, no animations)

```
                 DAMOCLES IN PRODUCTION
                 ──────────────────────

  WHERE     Greek soil. EYP perimeter.        No cloud egress.
  BRAIN     Local Ollama on the analyst's    No prompt leaves
            workstation. Audit-built model    the building.
            (Llama 3.1 · Qwen 2.5).

  PROVENANCE  Merkle-chained audit log. Any
              parliamentary committee or
              inspector can verify byte-by-byte.

  DATA      DuckDB on the analyst's machine. ~7 MB / day.
            Append-only. Open file format.   No vendor lock-in.

  SENSORS   AIS · GDELT · OpenSky · Sentinel SAR · Telegram.
            Swap any one, swap any all.       Same brief pipeline.

  TIMELINE  Day  1   Pilot — 1 analyst, 1 region.
            Day 30   Two regions, multi-analyst, audit-mode review.
            Day 90   National coverage. Two daily standing scans.
            Day 180  Hand-off complete. EYP owns the keys.

  COST      €0 marginal per brief at runtime.
            All third-party APIs already covered by EYP licences
            or replaceable with self-hosted equivalents.
```

---

## Speaker script (≤15 seconds)

> *"This isn't a SaaS. There's no Damocles cloud. The platform runs
> entirely on Greek soil, the brain runs locally on the analyst's
> machine, every brief is hash-chained for inspection, and at day 180
> EYP owns the keys. We're not selling subscription access to a black
> box — we're delivering the platform itself."*

Speaker beats:
1. Point at **WHERE** → *"Greek soil. EYP perimeter."*
2. Point at **BRAIN** → *"Llama 3.1 on the analyst's workstation."*
3. Point at **PROVENANCE** → *"Hash-chained. Inspectable."*
4. Point at **TIMELINE** → *"180 days. EYP owns the keys."*
5. Stop. Q&A.

---

## What's already in the platform (verifiable on demand)

If a panellist asks *"is any of this real or is it slideware?"*, the
speaker can show — not tell — each one:

| Claim | Verifiable how |
|---|---|
| Local Ollama brain | Click the model name in the SystemPill. Flip Gemini→Ollama. SystemPill shows `llama3.1` (and a red dot, because Ollama isn't running on the demo box — that's the honest representation). |
| Tamper-evident audit | Click "Tamper byte" → audit goes red. Click "Restore" + Verify → audit goes green. |
| Append-only DuckDB | `data/damocles.duckdb.demo` is a single file. Inspect with any DuckDB CLI. ([DEMO_RESTORE.md](DEMO_RESTORE.md) §"What's in the snapshot".) |
| Offline label rendering | Glyphs vendored under `frontend/public/maplibre-glyphs/`. Air-gap the laptop, AoI labels still render. |
| Live scan replay | Click "Play scan" in the topbar. 80 polygons stream over a local WebSocket, six REDs land last. |
| Sensor swap-ability | `backend/sensors/` — each sensor is one file with a `fetch()` and a `parse()`. The pipeline contract is the union of their outputs; nothing else cares which one produced a row. |

That table is the W3 deliverable manifest — every row is something the
W3 build added to the demo so the speaker has an artefact behind the
slide's bullets.

---

## What's NOT on this slide (deliberately)

Things that would weaken the close, in descending order of damage:

- **Headcount asks.** Don't pitch *"we need 4 engineers."* The slide
  says *"EYP owns the keys at day 180."* Operational handover is the
  story, not staffing.
- **Cloud / SaaS pricing.** There is no Damocles cloud. Saying
  *"we'll host it"* contradicts the WHERE bullet and gives a panellist
  an opening to ask about EU AI Act data-residency.
- **Roadmap features.** No *"next quarter we'll add X."* The slide is
  about what they get on day 1 — the roadmap belongs in a follow-up
  meeting.
- **Competitor comparisons.** Don't name Palantir, Recorded Future,
  Maltego. Naming a competitor names a category, and EYP has already
  decided that category isn't right for them — otherwise they wouldn't
  be running this competition.

---

## Acceptance (matches GOLD_MEDAL_PLAN W3 checkpoint)

This slide passes the W3 bar when:

- The speaker can read the script in ≤15 seconds without rushing.
- A reader who hasn't seen the deck can answer *"where does this run,
  what's the brain, how is it audited, when does EYP own it?"* from
  the slide alone.
- No bullet is contradicted by anything elsewhere in the codebase or
  in [GOLD_MEDAL_PLAN.md](GOLD_MEDAL_PLAN.md) / [demo-script.md](demo-script.md).
- Every row in the *"verifiable on demand"* table can be demonstrated
  live without leaving the demo machine.

---

*Last revised: 2026-05-13. Authority: `GOLD_MEDAL_PLAN.md` W3-T5.
Companion: [`demo-script.md`](demo-script.md), [`monologue.md`](monologue.md).*
