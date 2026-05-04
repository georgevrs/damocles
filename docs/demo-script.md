# Demo script — 5 minutes exactly

Practice this until it is muscle memory.

## Setup checklist (T-30 minutes)

```powershell
# 1. Backend, Neo4j, frontend all up
.\start.ps1                                # all three in separate windows
# OR manually:
docker compose -f docker/neo4j/docker-compose.yml up -d
.\start.ps1 -NoFrontend
npm --prefix frontend run dev

# 2. Pre-seed the demo scenario so the brief renders fast on stage
uv run python scripts/seed_neo4j.py

# 3. Run the regression test — must pass 22/22
uv run python scripts/test_e2e.py

# 4. Check audit verdict shows OK
Invoke-RestMethod http://localhost:8000/api/audit/verify

# 5. Open the browser and warm the bundle
Start-Process http://localhost:5173
# Click around: hit Aegean Maritime chip, click Run watch, click a citation,
# open an evidence modal. This warms the LLM, the SAR PNG cache, and the
# MapLibre WebGL context. Then close that watch's brief — leave the page on
# the empty state for the actual demo.
```

If any step fails, **do not start the demo**. The cost of stopping is zero; the cost of stage failure is months.

## The script

### [0:00] Open

> *"Good morning. Intelligence analysts today have a problem. There are 14,000 signals waiting in their queue. They will review 47 by end of shift. Damocles changes that number."*

Stand at the laptop, browser already open at http://localhost:5173. The three-panel UI is visible — empty brief, empty graph, dark Aegean map.

### [0:30] Tour the chrome

> *"The analyst sees three panels — map on the left, intelligence brief in the centre, knowledge graph on the right. Bottom strip: live pipeline progress, audit log."*

Point at the top bar:

> *"And these badges — the LLM is reachable, the audit chain is healthy. Forty-one entries verified. We'll come back to that."*

[Hover the audit badge so the verdict tooltip shows: *"OK — every chain link rehashes correctly"*]

> *"The analyst can launch a preset Watch — maritime, border, airspace, information — or type any free-text query. The system isn't locked to presets."*

[Hover each chip briefly so the cursor shows it's clickable]

### [0:45] Run the demo watch

Click **Aegean Maritime** chip — input populates with `"Aegean - last 7 days"`.

Click **Run watch**.

> *"During development we use Google's Gemini API — fast, cheap, no GPU required. For the demo and for production, the same code switches to a local model with one environment variable. No data leaves Greek infrastructure."*

The bottom-left progress stream starts firing events: `watch_created`, `sensors started`, `geospatial_sensor complete: 485 events`...

> *"Damocles is fusing four data sources right now: Sentinel-1 satellite radar, AIS vessel positions, GDELT global news events, Telegram social signals. All free, all public."*

The brief panel shows shimmer skeletons. The graph panel populates with composite event diamonds and source-node circles.

### [1:30] The brief lands

After ~50 seconds, the brief replaces the skeleton. Five sections appear: BLUF, Key Judgments (3), Supporting Evidence (3), Devil's Advocate, Recommendation.

> *"Damocles has fused 485 vessel detections, 160 news events, and the social signal layer. The fusion engine has produced multiple composite events, each rated by threat grade — green, amber, red. The supervisor agent has assembled this brief."*

> *"Top alert is AMBER. One sentence at the top — Bottom Line Up Front."*

[Read the BLUF aloud]

### [2:00] The citation click — THE GOLD-MEDAL MOMENT

Click the BLUF sentence text.

> *"Watch what just happened."*

[Pause for a heartbeat — let the eye catch up]

- The map flies to the cited source coordinates over 800 ms
- The graph dims everything to 18% opacity except the cited source nodes
- The cited nodes get an amber border ring; on the active vessel, an outer pulse ring
- A **Citation chain** expansion drops below the BLUF showing two source cards

> *"That click just traversed three independent data sources and a knowledge graph. The map flew to the source location. The graph highlighted the cited nodes. The citation chain expanded inline — every claim, every source, traceable."*

### [2:15] The evidence modal

Click the **Vessel** source card in the citation expansion.

The EvidenceModal opens with the **actual SAR tile PNG** showing the detection bounding box. AIS status, MMSI, length, dark-vessel score visible in the metadata grid.

> *"This is the raw radar pixel the agent reasoned over. AIS-dark — broadcasting nothing, but Sentinel-1 saw it. Eighty meters long. The dark-vessel score is eighty-five percent."*

Close the modal (Escape).

Click another section — say the second Key Judgment.

> *"Same pattern. Click any sentence, trace it to source. Click the source, see the raw evidence."*

Map flies to a new location. Graph updates. New citation expansion.

> *"Not a summary of a summary. A citation chain — the same standard you would expect in a court."*

### [3:00] The Devil's Advocate

Scroll down to the Devil's Advocate section. It has a rose-coloured border and a `devil 75%` chip.

> *"But we don't just tell you what we found. We tell you why we might be wrong."*

[Read the Devil's text aloud — it should be substantive, e.g., *"The maritime escalation narrative is a spurious correlation based on default city-center coordinates..."*]

> *"Damocles institutionalizes skepticism. Every assessment goes through an adversarial review. The devil's confidence — seventy-five percent — is the probability our primary assessment is **wrong**. Not right. Wrong. The analyst sees it as a counter-signal."*

> *"This is what real intelligence tradecraft looks like."*

### [3:30] The audit chain

Scroll to the bottom-right AuditLog panel. Click **Verify chain**.

The verdict banner appears: *"OK — every chain link rehashes correctly"* in emerald green.

> *"Every model call, every analyst action, every citation click — hashed and chained. Merkle structure. Two independent stores."*

> *"Any parliamentary committee can verify this log has not been tampered with. In O(N) time. Right now, in production, every demo I run, every analyst's click — on the chain."*

[Optional, only if you have time: ]

> *"And to prove that's not theatre — the system can detect tampering. The pre-flight test we run before every deployment dry-run does exactly this: populates the chain through the live pipeline, then deliberately corrupts one entry, then verifies. The verifier returns the exact index of the corruption. Tested forty-one entries deep, this morning."*

### [4:00] The graph

Move the cursor to the right panel. Pan the graph slightly.

> *"Forty-seven nodes. Eighty-nine relationships. Built in under sixty seconds from free, public, sovereign data. Zero data left Greek infrastructure. Zero external API calls during the demo."*

> *"The yellow edges are CITES edges — every cited claim in the brief points at a graph node. Click a graph node here..."*

Click a Vessel node in the graph.

> *"...and the brief panel jumps to the section that cites it. Same citation chain, in reverse."*

### [4:15] Second query — proves it isn't scripted

Click the input box. Type:

> `"Turkish research vessel activity last 30 days"`

Hit Enter.

> *"The Watch system accepts any query. The analyst is not limited to presets. Free-text — typed in real time, in front of you."*

The progress stream fires again. The skeleton returns. Don't wait for it to complete — twenty seconds is enough to demonstrate the live nature.

> *"New brief. Same pipeline. Different scope. Comes back in under a minute."*

### [4:45] The close

Step back from the laptop. Look at the audience.

> *"Palantir costs three million euros per deployment. Requires a US cloud. Cannot run in Greek. Damocles costs zero to run, runs on a one-thousand-five-hundred-euro server, runs in Greek, and was built in three weeks by a Greek team."*

> *"The question for EYP is not whether they can afford Damocles."*

[Beat]

> *"The question is whether they can afford not to have it."*

### [5:00] Stop.

Don't say "thank you". Don't say "any questions". Hold the silence for two seconds. Then sit down.

---

## What can fail and what to do

### Pipeline timeout (>90 seconds)
The brief panel still shows skeletons after a minute. **Don't panic.** Continue narrating:

> *"While the pipeline finishes, let me walk through what's happening behind the panels..."*

Use the time to talk about the audit chain or the Devil's Advocate. The brief will land eventually.

If after 2 minutes nothing has appeared, the LLM is rate-limited or stuck. **Switch to the pre-seeded brief** — open a new tab, navigate to a known-good brief URL by clicking the latest watch in the WS log, and continue from `[1:30]`.

### Map doesn't fly to coordinates
Click the same brief sentence again. The `flyTo` is idempotent. If still nothing, the source has no `lat/lon` (rare; happens when only a Composite source has coords). Pick a different sentence.

### EvidenceModal SAR image is missing
The `sar_tile_id` references a tile not in the cache. The modal degrades gracefully — it still shows MMSI, AIS status, length. Narrate around it:

> *"In the seeded scenario this image was evicted from the cache. In production every detection's tile is retained for retention period — see the audit log."*

### Verify chain fails
**Stop the demo immediately and acknowledge it.** *"That's the system doing what it was built to do — surface a tamper attempt. We'd investigate this before allowing any analyst to act on the brief."* Then pivot to the next section. **Do not pretend it didn't happen.** Honesty is the whole point of the audit chain.

### Browser crashes / network drops
Pull up the **pre-recorded video** of a known-good run. Show it inline. Don't try to recover live.

### The audit "verified OK" is suspicious
Hover the badge — the timestamp is right there. Show that the verification ran in the last 15 seconds.

## Calibration notes for the speaker

- **Pace**: 90 words/minute. Under 5 minutes total even with pauses. Don't rush; the visual impact needs the eye to catch up.
- **Pauses**: at `[2:00]` and `[3:00]` and `[4:45]`, deliberately wait 2 seconds. Silent moments are when the audience absorbs.
- **Voice**: lower the third sentence of every section by half a tone. Authority comes from groundedness, not loudness.
- **Eye contact**: on `[0:00]`, `[3:00]`, `[4:45]` — those are the three moments to look at the audience, not the screen.
- **Hands**: flat on the table or pointing at the screen. Don't gesticulate.

## Alternative paths for short demos

### 3-minute version (cuts second query + close)
- [0:00] Open
- [0:30] Tour
- [0:45] Run watch
- [1:30] Brief lands
- [2:00] Citation click + evidence
- [2:30] Devil's Advocate
- [2:45] Audit verify
- [3:00] Stop

### 90-second version (judges with stopwatch)
- [0:00] *"Type a query, get a brief where every sentence cites a source."*
- [0:10] Click Aegean chip → Run watch
- [0:50] Brief lands. *"Click the BLUF."* Click. Map flies, graph highlights, citation expands. *"Three independent data sources, knowledge graph, evidence modal, all in one click."*
- [1:10] Click vessel card → modal opens with SAR PNG. *"Raw radar pixel."*
- [1:25] *"Devil's Advocate institutionalizes skepticism. Audit chain proves nothing's been touched."*
- [1:30] Stop.

## Phrases to avoid

- "AI" without qualification — say "model" or name the specific behaviour
- "Powered by" — implies dependence; sovereignty is the pitch
- "Cutting edge" / "state of the art" / "best in class" — engineering audiences hate marketing words
- "Disrupt" / "revolutionize" / "transform" — same
- Any superlative without a number behind it

## Phrases to lean on

- "**Citation chain**" — the differentiator. Use the words.
- "**Institutionalize skepticism**" — the Devil's Advocate's purpose, in 2 words.
- "**On the chain**" — every analyst action is on the chain. The phrase has cultural weight.
- "**Sovereign**" — used three times exactly. Once for data, once for compute, once for the platform.
- "**Three weeks. Greek team. Free, public data.**" — the closing triple. Memorise the exact wording.

---

**Remember:** the demo is not about the technology. It is about the analyst with 14,000 signals and 47 hours. Everything you show, every word you speak, points back to that person. The judge's question is *"would I trust this in my analyst's hands?"*. The answer the demo proves is *"yes — every claim is cited, every action is logged, every assessment is challenged."*

Don't sell. Demonstrate.
