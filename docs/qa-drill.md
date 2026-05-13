# Q&A Drill — five questions, ≤60 seconds each
### W4-T1 · feeds the Q&A panel at T+05:00

The pitch is five minutes. The Q&A is up to five more. Five minutes of
question-time decides whether the panel awards on the spirit of what
they just saw or on the gaps they can poke open. This document is the
defence — five answers, memorised, delivered without filler.

**Drill protocol.** For each question:
1. Read the answer aloud once, slowly, with a stopwatch.
2. Re-read without the page, target ≤60 seconds.
3. Record. Play back. Mark filler words ("kind of", "basically", "so")
   and any sentence longer than 20 words. Re-deliver.
4. Pass when three consecutive recordings each clock <60s AND have
   zero filler AND no sentence >20 words.

**Forbidden words across all five answers.** *"AI"*, *"machine learning"*,
*"automation"*, *"intelligent system"*. Each one downgrades the platform
to a category EYP has already decided it doesn't want to buy from.
Use *"Damocles"*, *"the platform"*, *"the agents"*, *"the chain"*.

---

## Q1 — *"What if the LLM hallucinates a citation that doesn't exist?"*

**Speaker eye contact:** technical panellist. **Beat 1 of the answer is a
demonstration, not a sentence** — operator clicks any citation chip,
modal opens with the source node, then speaker speaks.

> *"This is the second-most-important question you can ask, so let me
> show you the answer before I say it. [operator clicks chip] Every
> citation chip resolves to a source node that exists in the local
> store — vessel, news event, AoI polygon, composite. The supervisor
> agent validates every citation against the AoI's evidence set
> server-side before the brief is published. A citation pointing at a
> node ID that isn't in the evidence set causes the brief to be
> rejected and re-generated once. If the second pass also fails, the
> AoI gets no brief — Damocles refuses to publish an unsupported
> claim. That rejection is itself an audit-chain entry, so you can
> count how often it fires."*

**Length target:** 55–60 seconds.
**Landing word:** *"…count how often it fires."*
**Trap:** don't say *"we prevent hallucinations"*. Nobody believes that.
Say *"we make them detectable and refuse to publish them"*. Different claim.

---

## Q2 — *"How is this different from Palantir Gotham?"*

**Eye contact:** panel chair (this is the political question).

> *"Three structural differences. One — Palantir AoIs are configuration.
> An analyst tells Palantir what to watch and Palantir watches it.
> Damocles AoIs are inference. The standing scan tells the analyst what
> appeared overnight that wasn't there yesterday. The analyst doesn't
> need to know what to look for. Two — every brief here is hash-chained.
> Any tampering between when the brief was written and when an inspector
> reads it is detectable byte-by-byte. [pause two seconds] We'll
> demonstrate that in a moment if you'd like. Three — sovereignty. There
> is no Damocles cloud. The platform runs on one Greek server with one
> environment variable that swaps the brain to a fully local model. No
> license, no per-seat cost, no recurring egress. EYP owns the keys."*

**Length target:** 55 seconds.
**Landing word:** *"EYP owns the keys."*
**Trap:** don't volunteer Palantir's downsides ("they're a US contractor",
"their UI is dated"). Stay structural. The audience can fill in tone.

---

## Q3 — *"What does this cost EYP to run?"*

**Eye contact:** the procurement-shaped panellist (the one who hasn't
spoken yet — they're calculating).

> *"Hardware cost only. One server inside your existing infrastructure.
> Zero per-seat licensing. Zero recurring API spend in the local-brain
> configuration we'll be in by week one. The third-party APIs we use in
> development — Gemini, Sentinel Hub, AISStream — are either already
> covered by EYP's existing licenses or replaceable with self-hosted
> equivalents. The DuckDB store is roughly seven megabytes per day at
> Greek-national coverage. Operationally we estimate one trained
> analyst per week onboarded from the existing documentation. The full
> source code is delivered. There is no ongoing payment to us after
> day 180."*

**Length target:** 45–50 seconds.
**Landing word:** *"…no ongoing payment to us after day 180."*
**Trap:** don't quote a specific server price. Different panellists have
different mental anchors and being wrong about €5k vs €15k hardware is
a memorable own goal. *"Hardware cost only"* is enough.

---

## Q4 — *"Who owns the data, and where does it live?"*

**Eye contact:** panel chair (this is the legal question).

> *"The DuckDB fact store is a single file on local disk in the
> platform's data directory. Greek soil. The Merkle audit log is local
> JSONL plus mirrored Neo4j edges, both in the same data directory.
> In the local-brain configuration there is no outbound transmission
> at all — every brief is generated, every citation chain is
> resolved, every audit entry is written without any external network
> call. EYP holds the only copy. The platform is delivered as source
> code and operational scripts; there is no Damocles-side telemetry,
> no phone-home, no licensing daemon. If you disconnect the demo
> machine from the network right now, the next four minutes of the
> demo would still work identically."*

**Length target:** 50–55 seconds.
**Landing word:** *"…would still work identically."*
**Trap:** don't claim *"we don't store any data"*. You do — that's the
point. Claim *"we never transmit it"*. The distinction is the win.

---

## Q5 — *"What stops a hostile actor from poisoning your Telegram input?"*

**Eye contact:** technical panellist (this is the adversarial question).

> *"Three layers, and an honest limit. Layer one — the linguist agent
> normalises signal by source reputation. Channels carry a reliability
> tier the analyst can adjust, and a coordinated low-reputation surge
> doesn't promote to RED on its own. Layer two — the Devil's Advocate
> runs against the brief output, not the inputs. So a poisoned input
> that survived layer one still has to survive a counter-narrative
> pass written by a different model with a different prompt. Layer
> three — the audit chain. Every entry is timestamped and hash-chained,
> so an after-the-fact analysis can identify the contaminating row to
> the second and trace its downstream impact. The honest limit — we
> can't prevent prompt injection in absolute terms. Nobody can. But
> we can make it discoverable. That's the difference."*

**Length target:** 55–60 seconds.
**Landing word:** *"…we can make it discoverable. That's the difference."*
**Trap:** don't say *"we use a classifier to filter bad content"*. That's
a feature claim nobody believes. Say *"we make the contamination
detectable after the fact"* — that's a verifiable architectural claim.

---

## The honest answers (what to say when you don't know)

Three fallback patterns. None of them include the word "actually".

1. **"I don't have that number with me, but I can have it to you tomorrow."**
   Use for: specific benchmarks, latency claims at scale, cost
   projections beyond the W3-T5 slide.

2. **"That's outside what we've validated for this pitch — let me tell
   you what we have validated."** Then pivot to one of the five canned
   answers above. Use for: questions about features we haven't shipped.

3. **"That's a fair concern. The architecture lets us address it, but
   I haven't built the specific control. Here's how it would slot in."**
   Use for: legitimate gaps. EYP respects this answer more than
   improvised confidence.

**Forbidden fallbacks.** *"Great question"* (filler). *"I'm glad you
asked"* (cringe). *"That's a really interesting point"* (deflection).

---

## Drill calendar (W4 cadence)

- **Mon Jun 3.** Cold read each answer once, recorded. Mark fillers.
- **Tue Jun 4.** Re-deliver Q1, Q2 three times each. Stopwatch.
- **Wed Jun 5.** Re-deliver Q3, Q4 three times each. Plus full Q1+Q2 from memory.
- **Thu Jun 6.** Q5 three times. Plus a random-order panel of all five.
- **Fri Jun 7.** Hostile-panel dry run — three readers pick one question
  each, deliver cold. Acceptance: ≤60s, zero filler, no <5s stumble.

If Friday fails on any single answer, that answer gets rewritten over
the weekend before W5 begins.

---

*Last revised: 2026-05-13. Authority: `GOLD_MEDAL_PLAN.md` W4-T1.
Companion: [`demo-script.md`](demo-script.md), [`monologue.md`](monologue.md).*
