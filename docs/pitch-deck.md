# Pitch Deck — 6 slides, 5 minutes
### W4-T3 · feeds the pitch at T+00:00

Six slides, no animations except the speaker's voice and the live demo.
Each slide ≤4 bullets, mono-typeface body, no clipart, no stock photos.
The deck exists to anchor the speaker — the **demo** carries the pitch.

**Theme constants** (use across all slides):
- Background `#0b0f17` (panel-bg), text `#e5e7eb` (panel-text)
- Amber accent `#f59e0b` for the Damocles diamond mark; rose `#ef4444`
  only on the RED-AoI demo slide; emerald `#10b981` only on the
  audit-chain slide
- Mono font: any IBM Plex Mono / JetBrains Mono variant
- One slide-number in the bottom-right corner, Greek numerals (`Α Β Γ Δ Ε Ϛ`)
- No company logo other than the diamond mark — EYP doesn't want
  vendor branding splashed across the room

---

## Slide Α (1) — Cover + Greek opening
**Duration:** 60 seconds spoken (the [monologue](monologue.md))
**On the slide:**

```

                ◆  DAMOCLES

                Σοβαρή νοημοσύνη.
                Σε Ελληνικό έδαφος.

                EYP National Security Innovation Challenge · 2026
```

**Speaker notes.** The deck stays on this slide for the entire 60-second
monologue. The operator does NOT advance the slide until the speaker
says *"Ξεκινάμε."* Then transition without animation to slide Β.

**The diamond.** The amber diamond mark is the only visual identity.
It comes from the platform's loading state — analysts watching it spin
during a brief generation. It's the platform's signature.

---

## Slide Β (2) — The killer scenario
**Duration:** 90 seconds spoken (the [click-by-click](demo-script.md#click-by-click-choreography--the-90-second-core))
**On the slide:**

```
   Tuesday, 06:00 EET.                  Six hours ago, while
                                        the analyst was asleep:

      Damocles                          6 RED Areas of Interest
      finished its                      surfaced from 1,238 SAR
      overnight                         detections + 158 news
      scan.                             events across Greek
                                        territory and EEZ.

                                        One of them already has
                                        a brief written.
```

**Speaker notes.** Operator **switches to the app at T+01:00** (slide stays
visible briefly as the app comes up). The speaker says *"Now I'll show
you what she sees when she sits down."* Then clicks the **North
Heraklion Zone** row in the triage list. Slide Β disappears, replaced
by the app itself. **For the next 90 seconds the screen is the
running platform, not slides.**

**Slide Β is never re-shown.** When the speaker finishes click 7 and
delivers the framing line *"…tells her what to look at, what to doubt,
and what to ask next"*, the operator advances to slide Γ.

---

## Slide Γ (3) — Tamper + sovereignty cinema
**Duration:** 60 seconds spoken
**On the slide:**

```
   Provenance is the architecture.            Sovereignty is the deployment.

   • Every brief sentence                     • Greek soil. EYP perimeter.
     hash-chains back to                      • Local Ollama brain on
     its source row.                            the analyst's workstation.
   • Every source row                         • Zero outbound calls in
     hash-chains to the                         local-brain mode.
     scan that fetched it.                    • No vendor cloud.
   • Every scan is an                           No phone-home. No daemon.
     append-only entry                        • EYP owns the keys at
     in the audit log.                          day 180.
```

**Speaker notes.** The speaker speaks across the slide while the operator
does the **live tamper demo** (W3-T1) and the **provider swap** (W3-T2)
on the running app behind the slide — the slide is reference text, not
the focus. **Operator beats:**
1. Click **Tamper byte** → audit verdict flips red.
2. Speaker: *"I just flipped one byte in a chain link. Watch the
   verdict change."*
3. Click **Verify chain** → "TAMPER DETECTED at index N".
4. Click **Restore** → byte replayed.
5. Click **Verify chain** → green.
6. Click the model name in the SystemPill → swaps to `llama3.1:8b`,
   dot goes red because Ollama isn't running on the demo machine.
7. Speaker: *"On the deployment laptop this is green. The pill stays
   green and no prompt leaves the building."*
8. Click model name again → back to Gemini (dot back to green).

---

## Slide Δ (4) — Devil's Advocate + DNA strands
**Duration:** 45 seconds spoken
**On the slide:**

```
   The system argues against itself.

   ┌─────────────────────────────────────────────────────────┐
   │ DEVIL'S ADVOCATE  · confidence 0.85                      │
   │                                                          │
   │ "The primary assessment relies exclusively on a single,  │
   │ ideologically driven news report; the total absence of   │
   │ Greek-language signals or official alerts strongly       │
   │ suggests the event did not occur as described."         │
   │                                                          │
   │           — written by a SEPARATE agent, against the     │
   │             same brief, on the same evidence set         │
   └─────────────────────────────────────────────────────────┘

   The institution doesn't have to ask 'did we double-check?'
   The system already did, and showed its work.
```

**Speaker notes.** Operator **scrolls the brief to the DEVILS_ADVOCATE
section** on the live app (the brief is still open from slide Β's
demo). Slide Δ stays visible as **reference for the quote** — judges
read the slide while the speaker delivers the spoken framing. The
**Information DNA** panel is briefly opened (one click) to show the
strand structure (W2-T2-adjacent).

**Trap.** Don't read the slide aloud word-for-word. Judges read fast;
the speaker's job is the framing sentence underneath, not the quote.

---

## Slide Ε (5) — Production story
**Duration:** 30 seconds spoken (the [W3-T5 script](production-slide.md#speaker-script-15-seconds), expanded slightly)
**On the slide:** verbatim from [production-slide.md §"The slide"](production-slide.md#the-slide-one-frame-no-animations).

**Speaker notes.** Read the slide top-to-bottom but pause for one
beat after each WHERE/BRAIN/PROVENANCE/DATA/SENSORS/TIMELINE/COST
label. The total budget is 30 seconds — that's roughly four seconds
per label. **Do NOT advance to Q&A on this slide; advance to slide Ϛ
first.** Slide Ε is the answer; slide Ϛ is the invitation.

---

## Slide Ϛ (6) — Q&A invitation
**Duration:** 15 seconds spoken
**On the slide:**

```
                ◆  DAMOCLES

                Σας ευχαριστώ.

                Ερωτήσεις.
```

**Speaker notes.** Speaker says *"Σας ευχαριστώ. Είμαι στη διάθεσή σας."*
Eye contact: panel chair. **Do not say** *"happy to take questions"* —
say *"είμαι στη διάθεσή σας"* (I am at your disposal). It's the
register EYP uses internally.

The five anticipated questions are in [`qa-drill.md`](qa-drill.md). The
operator stays at the keyboard during Q&A — any of the five canned
answers can include a live click.

---

## Slide timing budget — verification

| Slide | Spoken | Cumulative | Hard cap |
|---|---|---|---|
| Α    Cover + monologue       | 60s | 1:00 | 1:05 |
| Β    Killer scenario (demo)  | 90s | 2:30 | 2:35 |
| Γ    Tamper + sovereignty    | 60s | 3:30 | 3:40 |
| Δ    Devil's Advocate        | 45s | 4:15 | 4:25 |
| Ε    Production story        | 30s | 4:45 | 4:55 |
| Ϛ    Q&A invitation          | 15s | 5:00 | 5:05 |

The hard caps allow 5 seconds slack each. **If the speaker is 10+
seconds late at slide Γ, the operator skips the model-swap beat
(steps 6–8 above) — the tamper demo alone is enough to make slide Γ's
point.**

---

## Acceptance (matches GOLD_MEDAL_PLAN W4 checkpoint)

This deck passes the W4 bar when:

- Five full deliveries run inside the hard caps in the table above
  with no slide >5s over.
- Three external readers can each answer *"what's on slide Γ?"* from
  memory after watching the pitch once. The provenance + sovereignty
  framing has to land or the close doesn't work.
- No slide is >4 bullets. (Slide Γ has 8 bullets total across two
  columns — that's the cap.)
- No animation. No transition. No clipart. No stock photo.
- The speaker can deliver every slide's spoken script without looking
  at the deck content — the slide is for the audience, not the speaker.

---

*Last revised: 2026-05-13. Authority: `GOLD_MEDAL_PLAN.md` W4-T3.
Companion: [`demo-script.md`](demo-script.md), [`monologue.md`](monologue.md),
[`qa-drill.md`](qa-drill.md), [`production-slide.md`](production-slide.md).*
