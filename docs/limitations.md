# Known limitations & engineering debt

This is the candid ledger of everything that is **not done** or **knowingly compromised** in the current codebase. Every item lists a severity, a working description, the rationale (why it exists), and the path forward (if any).

Severity legend
- **BLOCKER** — must be resolved before the June 2026 demo or before GCP deployment.
- **WORKAROUND** — a usable workaround exists; flagged for revisit before the final demo.
- **DEBT** — engineering debt; acceptable for the demo but worth fixing during productionization.
- **BY DESIGN** — explicit scope decision documented here so reviewers don't mistake it for an omission.

This document is meant to be updated as the build progresses. When a limitation is resolved, move the entry to a "Resolved" section at the bottom rather than deleting it — the history is useful for the post-demo write-up.

---

## 1. LLM provider layer

### 1.1 Gemini free-tier daily quota can exhaust mid-day — WORKAROUND

`gemini-2.0-flash` has a 1,500-request/day free-tier limit per project. Heavy testing (especially repeated agent runs in Week 2) can hit `429 PerDayPerProjectPerModel-FreeTier` before midnight Pacific resets. Encountered during foundation verification.

- **Workaround in place:** `GEMINI_MODEL` env var lets you swap to `gemini-2.0-flash-lite` (3,000/day) or `gemini-2.5-flash-lite` (verified working when the 2.0 family is exhausted) without code changes. Documented in [credentials.md §1](credentials.md).
- **Path forward:** add a thin retry-with-fallback wrapper inside [`GeminiProvider`](../backend/llm/gemini.py) that detects the daily-quota error code and automatically tries `OLLAMA_DEVIL_MODEL`-style alternates. Or accept this is a dev-only concern (production runs Ollama).

### 1.2 Ollama on CPU is too slow for the live demo — BLOCKER for demo

The plan budgets ~60 s per Watch end-to-end. Ollama 8B inference on a CPU runs ~30 s per agent call; the supervisor pipeline calls 5+ agents, so a CPU-only run lands at ~150 s.

- **Path forward:** the demo machine needs an 8 GB+ VRAM GPU (RTX 3070 / M2 Pro / A10G on GCP). The plan documents this in `start.ps1` hardware notes; we'll need to verify on the actual demo hardware before April 2026.
- **Mitigation:** keep Gemini as a fallback for the live-typed second query in the demo script — the sovereignty argument is about deployment, not about every keystroke.

### 1.3 No automatic provider failover — DEBT

If Ollama dies mid-pipeline (out-of-memory, model not loaded), the agent layer raises and the Watch errors out. There's no fallback to Gemini even when one is reachable.

- **Path forward:** add a `FailoverProvider` that wraps two providers and auto-degrades. Probably out of scope for the PoC.

---

## 2. Python toolchain & dependencies

### 2.1 `requires-python` locked to `>=3.11,<3.13` — BY DESIGN

Sentinel-1 SDK (`sentinelhub`) didn't have Python 3.13 wheels for our pinned version on win32/linux when we resolved. Some downstream geospatial deps (`rasterio`, `pyproj`) are similarly behind on 3.13.

- **Path forward:** widen to `<3.14` once `sentinelhub>=3.12` and `rasterio>=1.4` ship win/linux 3.13 wheels. Re-check during Week 3.

### 2.2 `gdelt` PyPI package excluded due to malformed metadata — BY DESIGN

`gdelt==0.1.10` ships a `pyproject.toml` with `geopandas (>-1.7)` (typo for `>=1.7`); uv refuses to resolve it. The plan itself recommends fetching the GDELT master file CSV directly via `httpx`, which is what we'll do in the OSINT sensor (Day 6).

- **Status:** not a real limitation — it's a saved dependency.

### 2.3 uv resolution restricted to `win32` + `linux` — BY DESIGN

`tool.uv.environments` excludes `darwin`. macOS isn't a deployment target (dev is Windows, prod is GCP Linux), so resolving a darwin lockfile would create wheel-availability headaches we don't need.

- **If macOS dev becomes needed:** add `"sys_platform == 'darwin'"` and accept that some pinned versions may need bumping.

---

## 3. Geospatial sensor (Sentinel-1 + CFAR)

### 3.1 Tile timestamp = window midpoint, not actual acquisition time — DEBT

`GeospatialSensor.fetch()` uses `(time_from + time_to) / 2` as the timestamp on every emitted `Vessel`. The Sentinel Hub Process API path doesn't return per-tile acquisition metadata.

- **Operational impact:** the AIS cross-reference uses ±30 min tolerance, but the SAR detection is timestamped at window midpoint (e.g. 3.5 days into the past for a 7-day window). Live cross-reference against AIS therefore mostly fails — which is one reason the demo runs against pre-seeded data.
- **Confirmed in Day 7 integration:** with a 7-day window, 485 SAR vessels (all timestamped at midpoint) + 405 GDELT events (spread across the week) yielded **0 cross-sensor fusion edges** — only ~4% of GDELT events fall in the ±12 h band around the vessel midpoint, and that intersection rarely also satisfies the 50 km spatial tolerance. The fusion engine is correct (proven by 14 unit tests on aligned synthetic data); the real-world data simply doesn't align under midpoint timestamps.
- **Path forward:** in `scripts/seed_neo4j.py`, switch to the **Sentinel Hub Catalog API** to enumerate scenes first, then fetch each individually with its true acquisition time. Each Sentinel-1 pass over the Aegean (every ~6 days) becomes a separate `Vessel` cohort with a real timestamp, and the GDELT events of that day fuse properly. The fix lives in the seed pipeline, not the live sensor.

### 3.2 No land mask — DEBT

The 286-detection real-tile run includes coastal rocks, breakwaters, jetties, and possibly oil platforms in addition to actual vessels. CFAR has no idea what land is.

- **Path forward, in priority order:**
  1. **Cheapest:** add a Natural Earth coastline polygon and reject detections within 200 m of the coast. ~50 lines using shapely. Catches breakwaters and rocks.
  2. **Better:** add a known-platform exclusion list for the Aegean (oil rigs, fish farms with fixed AIS-AtoN beacons). These show up as bright stationary returns every pass.
  3. **Best:** the AIS cross-reference (Day 5) does most of the disambiguation: a bright return that AIS-matches at AtoN MID code (99...) is a navigation buoy, not a dark vessel.
- **Demo impact:** moderate. The demo brief shows specific vessels with raw evidence — non-vessel artifacts won't be cited. But the on-screen detection count is inflated.

### 3.3 No fetched-tile cache — DEBT

Each `scripts/test_geospatial.py` run re-fetches the same SAR tile and re-spends Sentinel Hub processing units. Free tier (30,000 PU/month) is generous so this isn't urgent, but during Week 2 agent iteration we'll want to disk-cache fetched tiles.

- **Path forward:** persist the raw float32 array as a GeoTIFF in `data/cache/sar/<bbox_hash>_<time_hash>.tif` and skip the network call when present. ~30 lines in `geospatial.py`.

### 3.4 CFAR uses Gaussian threshold approximation — DEBT (acceptable)

The threshold formula `mean + alpha * std` assumes Gaussian-distributed clutter. Real SAR sea clutter follows a K-distribution, with heavier tails. Practical effect: at the configured `alpha=4.0` (Gaussian Pfa ≈ 3e-5) the actual false-alarm rate is closer to 1e-3 over rough seas.

- **Mitigation:** `min_size_pixels=3` filters most single-pixel speckle hits, which removes the dominant K-tail false alarms.
- **Path forward:** swap to a true K-distribution threshold (closed-form via two-parameter Gamma). Adds ~40 lines, eliminates the bulk of remaining false alarms. Worthwhile if Day 7 fusion shows too many noise events. Otherwise leave as is.

### 3.5 Vessel length estimate is `max(bbox_side) × 10 m/px` — DEBT

Lengths come out within roughly ±50% of true vessel length. A vessel oriented diagonally to the SAR look direction has its bounding box stretched by √2; a parallel-to-coast vessel may have multiple azimuth ambiguity ghosts that inflate the bbox.

- **Path forward:** fit an oriented bounding box via `cv2.minAreaRect` instead of the axis-aligned rectangle from `ndimage.find_objects`. Five lines. Matters because the dark-vessel score boost relies on `length_m > 100` — a wrong length flips a borderline vessel from AMBER to RED. **Worth fixing before Day 7.**

### 3.6 Process API capped at 2,500×2,500 px — BY DESIGN

We clamp `bbox_to_dimensions()` output to 2,500×2,500. Above this, the Process API returns 400.

- **Operational impact:** at 10 m/px, this caps a single fetch to ~625 km². The full Aegean (22-28°E, 35-42°N ≈ 600×800 km) needs ~10 tiles. The demo seed will tile the bbox.
- **Mitigation:** the seed script will iterate over a tile grid; `WatchExecutor` will accept multi-tile results.

---

## 4. AIS cross-reference / dark vessel detection

### 4.1 AISStream free tier has no historical replay — BLOCKER for live demo

The free tier streams real-time AIS only. Yesterday's data is unreachable.

- **Why this matters:** Sentinel-1's 6-day revisit means a fresh SAR tile may be 5 days stale. Cross-referencing a 5-day-old SAR detection against today's live AIS is meaningless.
- **Resolution strategy:** the demo runs against **pre-seeded data**. The seed pipeline (Day 7) will run AISStream capture for ~24-48 h during the seed window and pickle every record alongside the SAR tiles. This is a real engineering pattern, not a corner cut.
- **For production deployment:** either pay for AISStream historical (~€20/mo) or contract the equivalent feed from MarineTraffic or Spire. Document this as a recurring cost in the EYP brief.

### 4.2 Type-5 static-data messages not parsed yet — DEBT

[`AISStreamClient`](../backend/sensors/ais.py) only handles `PositionReport`. Static data messages (type 5) carry the full ship name, callsign, IMO number, and vessel dimensions.

- **Operational impact:** vessel name comes from `MetaData.ShipName` in PositionReport (often present but sometimes empty), and **flag is always None** without static data.
- **Path forward:** add `"ShipStaticData"` to `message_types`, write a `_parse_static_data` function, and merge static records into the matched-AIS results. ~30 lines. Do this when Day 6 OSINT lands so the agent layer has flag data to reason over.

### 4.3 Flag derivation from MMSI MID code not implemented — DEBT

The first 3 digits of an MMSI map to an ITU country code (e.g. 240/241 = Greece, 271 = Turkey). Even without static data we could derive flag for every position report.

- **Path forward:** ship a tiny lookup table (200 entries) in `backend/sensors/_mid_codes.py` and call it during `cross_reference()`. ~50 lines including the table. Half a day's work; the impact on the agent layer is significant (flag is a primary reasoning signal).

---

## 4b. OSINT — GDELT

### 4b.1 GDELT geo filter must be applied loosely — BY DESIGN

GDELT geocodes events to **where the action happened**, not where the actors are based. A Greek-Turkish dispute discussed at the UN geocodes to Geneva; an EU summit decision geocodes to Brussels. A strict Aegean bbox would drop most diplomatic and military-communication events involving GR/TU actors.

- **Operational pattern:** the seed pipeline runs GDELT in two passes — a **strict** Aegean bbox for vessel-incident-class events (CAMEO roots 18-20) and a **global** bbox for contextual events (CAMEO 11-17). The fusion engine merges both result sets.
- **Status:** documented; the smoke test currently uses the global bbox.

### 4b.2 GDELT 2.0 dual country-code scheme is a footgun — RESOLVED but worth flagging

`Actor1/2CountryCode` (fields 7, 17) use **CAMEO codes** which are *mostly* ISO 3166-1 alpha-3 (`GRC`, `TUR`, `CYP`). `ActionGeo_CountryCode` (field 53) uses **FIPS 10-4** (`GR`, `TU`, `CY`). They are **not interchangeable**.

- **Resolution:** [`DEFAULT_ACTOR_COUNTRIES`](../backend/sensors/gdelt.py) holds both representations and matches against any of fields 7/17/53.
- **Trap for future contributors:** if you add a new country to the watchlist, add **both** code variants.

### 4b.3 GDELT 2.0 events table has 61 fields, not 58 — RESOLVED

GDELT v2.0 added `Actor1/2/Action_Geo_ADM2Code` fields. ActionGeo_Lat is at field **56**, not 55; Long at 57, not 56; SOURCEURL at 60, not 59. Easy to miss if you're reading v1-era docs.

- **Resolution:** offsets corrected, unit tests pinned to the v2 schema, sensor docstring documents the trap.

---

## 4c. OSINT — Telegram

### 4c.1 First-run interactive auth is a CLI script, not a UI flow — DEBT (with Week 3 plan)

`scripts/setup_telegram.py` requires the operator to paste a Telegram-issued login code at a terminal prompt. This is fine for the dev machine but wrong for any analyst-facing deployment.

- **Week 3 design intent:** wrap this in a guided UI flow:
  1. Settings panel → "Connect Telegram OSINT" button
  2. Modal: phone number field (pre-filled from settings), "Send code" button
  3. Backend triggers `client.send_code_request(phone)`, returns `phone_code_hash`
  4. Modal switches to: code input + 2FA password input (optional)
  5. On submit, backend calls `client.sign_in(...)` with the hash from step 3
  6. Status spinner → success → session pickled, sensor enabled
- **Implementation note:** Telethon supports this flow via `send_code_request` + `sign_in` as discrete async calls. The CLI's `client.start(phone=...)` is a convenience wrapper; we'll bypass it for the UI version.
- **Until then:** dev runs `setup_telegram.py` once. The session pickles to `data/cache/telegram/damocles.session` and survives across runs until Telegram revokes it.

### 4c.2 `DEFAULT_CHANNELS` is a placeholder list — DEBT

The four channels seeded in [`telegram_sensor.py`](../backend/sensors/telegram_sensor.py) (`@aegeanwatch`, `@greekmilitary`, `@turkishnavy_news`, `@southeasteurope`) come from the plan; I haven't verified they all exist. The sensor logs and silently skips channels it can't resolve.

- **Path forward:** during Day 6 final pass, the operator should:
  1. Open Telegram and search for active Aegean/Greek-Turkish OSINT channels
  2. Subscribe to each (Telethon needs the user's account to be a member to read)
  3. Replace `DEFAULT_CHANNELS` with the verified list
- **Demo impact:** if the curated list is empty or all skipped, the OSINT-from-Telegram corroboration leg of the brief stays empty. Not fatal — GDELT carries the OSINT load.

### 4c.3 Telegram messages have no native geocoding — BY DESIGN

Telegram doesn't attach geo metadata to channel posts. Position information has to come from NER on the message text (e.g., "Greek frigate spotted near Lesvos" → 39.18°N, 26.20°E).

- **Resolution timing:** Day 9, when the **Linguist agent** runs Greek+English+Turkish NER (spaCy `el_core_news_lg` is already installed; English/Turkish models added during agent setup) and writes lat/lon back onto the `SocialSignal` node.
- **Fusion engine impact:** until the Linguist agent runs, Telegram signals correlate by time only, not space. The plan accommodates this by giving Telegram a **100 km spatial tolerance** (the loosest of any sensor) — a single Telegram post about "the Aegean" can corroborate a SAR detection anywhere in the Aegean within ±24 h.

### 4c.4 Greek tonos / Turkish dotted-I matching — RESOLVED

In monotonic Greek, capital letters drop the tonos (acute accent), so `ΑΙΓΑΙΟ` (uppercase, no accent) does NOT substring-match `Αιγαίο` (lowercase, with accent on the iota) under plain `str.casefold()`. Same class of issue exists for Turkish `İ`/`I`/`ı`/`i`.

- **Resolution:** [`_normalize`](../backend/sensors/telegram_sensor.py) NFD-normalizes both haystack and needle, strips combining marks, then casefolds. Unit-test pinned to the exact phrase that broke during the smoke test.

### 4.4 Contested zone is a coarse bbox — WORKAROUND

`DEFAULT_CONTESTED_ZONES` is a single rectangle covering the eastern Aegean (26-28°E, 35.5-40.5°N). The actual disputed maritime areas have a complex shape that follows the median line between Greek and Turkish claims and excludes territorial waters around Greek islands.

- **Operational impact:** the +0.1 dark-vessel score boost for "in contested area" is correct in spirit but loose on edges. A vessel parked 1 km east of Lesvos gets the boost; a vessel 2 km east of a Turkish coastal island doesn't.
- **Path forward:** find an authoritative polygon (likely from Greek MoD academic publications or HALC maritime archives) and load it via shapely. A `shapely.contains(point)` check replaces the bbox lookup. ~20 lines.

### 4.5 GeospatialSensor doesn't auto-run cross-reference — BY DESIGN (for now)

The sensor returns SAR-only `Vessel` objects with `ais_status=UNKNOWN`. Cross-reference happens in a separate call. The pipeline orchestration (Geo → AIS → cross-ref → graph ingest) belongs in `WatchExecutor`, which is currently a placeholder.

- **Resolution timing:** Day 7 (fusion engine) is when we wire the full pipeline.

---

## 5. Pipeline / orchestration

### 5.1 Every solo sensor event becomes a single-member CompositeEvent — DEBT

The fusion engine emits one composite per connected component, including singletons. End-of-week-1 seed run produced 645 composites for 645 sensor events because cross-sensor edges were 0 (see §3.1) — every event was its own component. Most are GREEN passthrough composites that don't need analyst attention.

- **Operational impact:** the frontend's BriefPanel (Week 3) must filter to AMBER/RED composites by default and lazy-load GREEN on scroll. If we render 645 cards we crash the browser.
- **Demo impact:** the demo seed scenario will have far fewer composites because: (a) the March 2024 window has fewer SAR passes; (b) Catalog-API timestamps will produce real cross-sensor fusion, collapsing many singletons into multi-source composites.
- **Path forward:** add a configurable `min_composite_size: int = 1` knob to `FusionConfig`. Solo events below the threshold become standalone graph nodes (still ingested) but don't get a composite wrapper. Reduces graph noise.

### 5.2 WatchExecutor has no transient-failure retry — DEBT

If Sentinel Hub returns 502 once, the geospatial sensor branch is dead for that run. Same for AISStream WebSocket disconnects mid-capture and GDELT slot 504s. Currently the pipeline catches the exception, marks that branch failed, and continues with the survivors.

- **Operational impact:** sometimes a brief is degraded for no good reason — a retry would have produced a richer one.
- **Path forward:** wrap each `_run_*` method with a small `tenacity` retry decorator (`retry=retry_if_exception_type(httpx.HTTPError)`, `stop=stop_after_attempt(3)`, exponential backoff). `tenacity` is already a transitive dep via langchain.

### 5.3 GDELT bbox expansion margin is hardcoded — DEBT

`WatchExecutor._run_gdelt` adds a hardcoded ±2° to the watch bbox before passing it to GDELT. This is a guess — sometimes too tight (events one country away get dropped), sometimes too loose (Brussels EU summit slips through for an Evros-border watch).

- **Path forward:** make it configurable via `WatchSpec` — analysts who care about diplomatic context set `gdelt_expansion_deg = 5`, analysts focused on incidents set `gdelt_expansion_deg = 0`. Default 2 stays.

### 5.4 No fetched-tile cache for SAR — DEBT

(Already in §3.3 — same root cause; mentioning here because Day 7 made it more painful: each `seed_neo4j.py` run re-spends 10+ Sentinel Hub PUs even when re-running on the same window.)

### 5.5 No agent layer yet — BY DESIGN

The plan's Week 2 (Days 8-11). The five agents (Geospatial, OSINT, Linguist, Devil's Advocate, Supervisor) and their prompts. Day 8 starts now.

### 5.6 No Merkle-chain audit logger yet — BY DESIGN

The plan's Day 13. The `AuditEntry` model and `CYPHER_APPEND_AUDIT` query exist; no logger writes to them yet. Sensor fetches and graph mutations during the Day 7 seed run were NOT audited — that's a gap to close before any production deployment.

- **Demo impact:** the audit-log panel in the UI will be empty until Day 13.

---

## 5b. Agent layer (Week 2)

### 5b.1 Agents use pre-fetched context, not LLM tool calling — BY DESIGN

[`BaseAgent`](../backend/agents/base.py) does targeted Cypher queries upfront, formats results compactly, and sends ONE LLM call. Tool calling (Gemini function-calling, Ollama tools) was rejected.

- **Why:** tool calling adds two failure modes — hallucinated tool names and malformed arguments — for no practical benefit on a focused 5-agent pipeline. Pre-fetched context is deterministic.
- **Trade-off:** if an agent needs information we didn't anticipate, it can't go fetch it. If this becomes painful, we layer tool calling on top without changing the contract.

### 5b.2 Agents currently process ONE composite per call — DEBT

`scripts/test_agent.py` picks the highest-confidence composite and runs the agent on it. In production, the supervisor needs assessments for the **top-N** composites per watch (probably 5-10 by threat-grade × confidence) so the brief has multiple cited findings to weave together.

- **Path forward (Week 2 Day 11):** the Supervisor pipeline iterates the top-N AMBER/RED composites, runs Geospatial + OSINT + Linguist + Devil's Advocate concurrently per composite, then assembles the brief.
- **Cost forecast:** at top-10 composites × 4 agents × 1 LLM call each = 40 calls per watch. Gemini free tier (1500/day on flash, 3000/day on flash-lite) handles ~75 watches/day in dev, comfortable. Ollama on local hardware: ~3-5 minutes per watch on a GPU, prohibitive on CPU.

### 5b.3 The Day 8 smoke test fell back to a GREEN composite — DEBT (data shape, not bug)

Day 7 seeding produced AMBER composites only from solo NewsEvents (high goldstein), and the smoke test's preferred picker `AMBER + has-Vessel` returned nothing. The fallback path (any composite, highest confidence) picked a GREEN single-source NewsEvent, so the Day 8 demo shows the agent working on a thin context.

- **Resolution:** when limitation §3.1 is fixed (per-tile SAR timestamps from Catalog API), cross-sensor fusion produces multi-source AMBER composites and the agent will have richer context to reason over. The agent code is correct; the data shape is the blocker.

### 5b.4 No retry budget enforcement — DEBT

`BaseAgent.run()` retries exactly once on validation failure. If the second attempt also fails, it raises. There is no per-watch retry budget — a watch with 10 composites and a flaky LLM could chain 20 retry calls.

- **Path forward:** add a `RetryBudget` shared across all agent runs in a single watch. Once exhausted, agents return a "validation failed, see logs" stub composite instead of raising. The Supervisor agent then notes the degradation in its brief metadata.

### 5b.5 Devil's Advocate cannot mechanically detect manufactured challenges — DEBT

The system prompt contains the rule "*do NOT manufacture false challenges; manufactured challenges destroy trust faster than missed challenges*". The model usually obeys, but a sufficiently sycophantic or hallucinating model could produce a challenge that *looks* legitimate (cites real nodes, uses domain language) but rests on a fabricated premise. We have no automatic way to detect this — it requires human review or ground-truth comparison.

- **Operational mitigation:** the analyst reads the devil's challenges and decides whether they hold water. The system surfaces `devil_confidence` as an analyst-readable counter-signal; it is NOT a hard override.
- **Path forward (post-demo):** track devil's calibration over many runs — for each devil_confidence ≥ 0.7 verdict, did the analyst agree the primary was wrong? Build a calibration curve. If devils consistently false-positive, lower the temperature back from 0.3 toward 0.1.

### 5b.6 Devil's Advocate uses the same model as primary agents on Gemini — BY DESIGN (today)

`get_devil_provider()` routes to `qwen2.5:7b` only when `LLM_PROVIDER=ollama`. Under Gemini in development the devil and primary agents share the same model chain. The plan calls for a slightly more creative model for the devil — the temperature bump (0.1 → 0.3) achieves most of the desired creativity gap regardless.

- **For the demo:** when running on Ollama for sovereignty, the model split kicks in automatically and the qualitative difference is visible.

### 5b.7 BaseAgent._parse changed from staticmethod to instance method — RESOLVED 2026-05-02 (migration note)

To support per-agent output schemas via the new `output_model` class attribute (Devil's Advocate uses `DevilsAdvocateOutput`, the Supervisor will use a richer Brief schema), `_parse` had to become an instance method so it can read `self.output_model`. No external callers depend on the static signature, but flagging it here for any future contributor reading old commits.

### 5b.8 Supervisor reasons over ONE composite at a time — DEBT

`SupervisorAgent.fetch_context()` pulls a single CompositeEvent and its sources. A real watch produces dozens of composites, so the demo brief should aggregate findings across the top-N (probably 3-5 by threat-grade × confidence). The current pipeline produces *one Brief per composite* — i.e., if you ran it across all 645 composites in a seeded watch, you'd get 645 Briefs.

- **Operational impact:** for the demo, we run the agent layer on the **top-1 most-AMBER composite** and ship ONE brief per watch. Thin contexts produce thin briefs (which is what we saw on Day 11 — a 3-judgment brief on a single-source composite).
- **Path forward:** introduce a "watch-level Supervisor" pass that takes the top-N per-composite supervisor outputs and weaves them into a single multi-composite brief. The per-composite Briefs become the supporting tier; the watch-level Brief is what the analyst sees first.
- **Rough cost forecast:** top-3 composites × 4 agents = 12 LLM calls. Plus the watch-level supervisor = 13. With Gemini 3-flash-preview at ~3-5 s per call, that's ~60s — at the edge of the demo's 60s budget but feasible.

### 5b.9 Brief metadata is an unstructured dict — DEBT

`Brief.metadata: dict[str, Any]` carries `agents_consulted`, `processing_duration_seconds`, `sources_count`, `supervisor_metadata`. There's no Pydantic schema for it, so a typo in the assembly code would silently produce a malformed brief.

- **Path forward:** define `BriefMetadata` Pydantic. Five extra lines, catches typos at construction time.

### 5b.10 Primary agents run sequentially in `scripts/test_brief_assembly.py` — DEBT

Geospatial → OSINT → Devil's Advocate runs in series even though Geospatial and OSINT are independent. With Gemini 3-flash at ~5s/call, parallelizing the two primaries shaves ~5s off the demo's wall-clock.

- **Path forward:** `asyncio.gather()` the two primary calls. The devil still has to wait for both to feed their outputs in. ~10 lines.

### 5b.11 SupervisorAgent overrides `run()` instead of using the BaseAgent retry path — DEBT (acceptable)

Supervisor has nested-per-section citation validation that doesn't fit the flat-list contract `validate_agent_output()` enforces, so it has its own `run()` with a duplicated retry loop. If we add a third agent with nested validation, this gets extracted into `BaseAgent.run()` with a `validate_output(out, valid_ids)` hook the subclass can override. For now (one such agent), the duplication is fine.

---

## 5c. API layer (Week 2 Day 12)

### 5c.1 In-memory event broker is single-process only — DEBT (production blocker)

`backend/api/_broker.py` keeps per-watch event buffers and subscriber sets in process memory. Run uvicorn with `--workers 4` and only one worker sees each event; the other three serve stale or empty WebSockets.

- **Path forward (production):** swap the in-memory backend for **Redis pub/sub** or **NATS**. The `WatchEventBroker` interface (`publish`, `subscribe`, `is_done`, `gc`) is small enough that the swap is contained to `_broker.py`. ~80 lines of redis-py.
- **Demo impact:** zero. The demo runs on a single uvicorn worker; multi-worker concerns kick in only on the GCP deployment.

### 5c.2 `POST /api/watches` returns synchronously while the pipeline runs detached — DEBT

The endpoint creates the Watch, kicks off `asyncio.create_task(_run_pipeline(...))`, and returns immediately. If uvicorn crashes mid-pipeline the Watch sits in `status="processing"` forever — there's no resumption path or "stuck-watch sweeper".

- **Operational mitigation today:** the WS shows `pipeline / failed` if the executor itself raises, but a hard process crash leaves no trace.
- **Path forward:** persist a heartbeat into Neo4j every N seconds during pipeline execution; a startup sweeper marks any Watch whose heartbeat is older than 2 × stage-budget as `error`. ~30 lines.

### 5c.3 No POST → WS → brief integration smoke — DEBT

`scripts/test_api.py` exercises only the read-only endpoints against an already-seeded brief. The full button-press → WebSocket-progress → brief-rendered round-trip belongs in the frontend smoke test (Week 3) — until then, individual pieces are tested separately (`test_brief_assembly.py` for the pipeline, `test_broker.py` for the broker, `test_api.py` for the read endpoints).

### 5c.4 Graph endpoint returns full property dicts uncompressed — DEBT

`GET /api/graph/{watch_id}` includes every property of every Node. A 645-composite watch returns ~250 KB JSON. Fine for the demo at LAN speeds, but a real analyst on a slow VPN would feel it.

- **Path forward:** trim properties to a display-only subset before serializing (drop tile_ids, full text bodies, etc.). The frontend Cytoscape panel needs only id, type, label, lat/lon, and a small `display_props` blob.

### 5c.5 `neo4j.time.DateTime` Pydantic serialization — RESOLVED 2026-05-02

Endpoints returning Neo4j Nodes 500'd with `PydanticSerializationError: Unable to serialize unknown type: neo4j.time.DateTime`. Fixed via [`backend/api/_serialize.py`](../backend/api/_serialize.py) with a `jsonable()` walker applied at every endpoint that touches the graph. Coerces neo4j temporal types to ISO strings.

### 5c.6 Broker subscribe race lost events during buffer replay — RESOLVED 2026-05-02

The original implementation registered the live queue *after* replaying the buffer. Events published during replay landed only in the buffer (subscriber set was empty); when the loop transitioned to queue-drain, those events were missed entirely. Fixed by registering the queue first then snapshotting the buffer (single-threaded asyncio makes those two lines atomic). Test pinned to the exact race.

---

## 5d. Audit logger (Week 2 Day 13)

### 5d.1 The `actor` field is unauthenticated — DEBT (production blocker)

`MerkleAuditLogger.log(action_type, actor, payload)` accepts ``actor`` as a free-form string. Today the executor sets it to the agent name (`"geospatial_agent"`, `"devils_advocate"`, etc.) and the citation-chain endpoint sets it to the literal `"analyst"`. Real deployment needs:

- Real auth at the API edge (mTLS / OIDC / SAML — depends on EYP infra).
- The verified principal flowing into every audit call as the actor.
- Per-actor signing of the entry (so even an operator with full DB access can't forge another actor's row).

For the June demo this is acceptable as is — there's no analyst persona to spoof — but it's the first thing that needs hardening before a production deployment.

### 5d.2 Two-store drift can occur if Neo4j append fails after JSONL succeeds — DEBT

The append order is: JSONL first, then Neo4j. If Neo4j fails the JSONL still has the entry, but the chains diverge — JSONL has more entries than Neo4j. ``read_chain`` prefers Neo4j when present, so the verify endpoint would silently use the shorter chain.

- **Mitigations in place:** the JSONL append failure logs `MerkleAuditLogger: Neo4j append failed — entry persisted to JSONL only`. Bootstrap on next startup will pick up from JSONL's later hash.
- **Path forward:** add a `reconcile` CLI that diffs the two stores and replays missing entries into the lagging one. ~50 lines.

### 5d.3 No external anchor for the chain root — DEBT

The chain is internally consistent and tamper-evident *given access to both stores*. An operator with root on the host could rewrite both atomically and the verifier would still pass. Standard Merkle-tree systems anchor by publishing the daily root hash to a public timestamp authority (OpenTimestamps + Bitcoin, or a national PKI).

- **Demo claim:** *"Any parliamentary committee can verify this log has not been tampered with"* — this holds against any party WITHOUT root on the host. Worth being precise in the live demo.
- **Path forward:** pre-demo polish is to publish a daily SHA256 of the latest chain_hash to a public bulletin (could be as simple as a tweet or a git commit to a public mirror repo).

### 5d.4 Audit log grows unboundedly — DEBT

No retention/archival policy. A 7-day window with one watch/day produces ~50-100 entries; a long-running deployment with many analysts would accumulate millions over a year.

- **Path forward:** epoch the chain quarterly. Each epoch's first entry has `previous_hash = chain_hash_of_last_entry_in_previous_epoch`, and the closed epoch is moved to cold storage with the closing chain_hash anchored externally. The "live" chain stays small and fast to verify.

### 5d.5 verify_chain checks chain structure, not payload integrity — BY DESIGN

The chain stores `payload_hash`, not the payload. `verify_chain` proves the chain is internally consistent — that nobody truncated, reordered, or rewrote `chain_hash` linkages. Payload tampering (rewriting both the payload AND its `payload_hash` AND every downstream `chain_hash`) would re-link successfully, but would diverge between the JSONL and Neo4j stores, which is detectable separately.

- **Why this is correct:** mirrors the standard Merkle-tree pattern. Storing payloads in the chain itself bloats it ~100×; the cross-store check catches the same attack class with ~1× storage.

### 5d.6 Bootstrap + read_chain now prefer the longer of the two stores — RESOLVED 2026-05-02

The Day 14 e2e test failed at the audit-verify step because:
1. Day 13 smoke ran with JSONL-only (Neo4j param was None).
2. Day 14 e2e ran the full pipeline through the API → both stores got new entries.
3. Bootstrap picked the older Neo4j-empty path → JSONL had more entries than Neo4j.
4. ``read_chain()`` preferred Neo4j (which only had Day-14 entries whose ``previous_hash`` pointed back to Day-13 hashes only present in JSONL).
5. ``verify_chain`` walked Neo4j alone and failed at index 0 because the first Neo4j entry's ``previous_hash`` was not GENESIS.

Fixed by making both `bootstrap()` and `read_chain()` pick the store with **more entries** (JSONL wins ties — append-only file is harder to silently truncate). Eliminates divergence-driven verify failures.

---

## 5e. Week 2 close-out (Day 14)

### 5e.1 End-of-Week-2 integration test passes 22/22 assertions

[`scripts/test_e2e.py`](../scripts/test_e2e.py) is the regression test that runs before every demo dry-run. It exercises the **full public-API path** (POST → WS → brief → citation chain → audit verify) and asserts every demo-critical invariant from the plan:

- POST /api/watches accepts the query and returns a Watch
- WebSocket streams pipeline events to completion (16 events, 63.4 s)
- Brief appears with the right structure (BLUF + ≥1 KJ + Devil + Recommendation + Supporting)
- Every text-bearing section has at least one citation
- Every citation_node_id resolves to a real source via the gold-medal endpoint
- Every source carries node_id + node_type + raw_evidence
- Audit chain of all 41 entries verifies clean

The test ran in 65 s wall-clock, ~10 Sentinel Hub PUs, ~5 Gemini calls — well inside the demo's 60-90 s budget per watch.

### 5e.2 Demo "press the button" works on live data

The headline result from the e2e run:

> *"A single 80-meter vessel is operating with a disabled AIS transponder in a sensitive Dodecanese transit corridor, though the lack of corroborating signals suggests this may be a technical failure rather than a high-value illicit operation."*

confidence 0.65 — appropriately calibrated for a single-source signal. The Devil's Advocate fired with a substantive counter; the Recommendation tagged ROUTINE (not PRIORITY); the audit chain captured every step of the analysis.

### 5e.3 Reproducible regression bar for the demo dry-runs

`test_e2e.py` is what we run before every dry-run. If any assertion fails, the dry-run is blocked until it's diagnosed. The 22 assertions cover every invariant a judge could test by clicking a button or running a Cypher query.

---

## 6. Frontend (Week 3)

### 6.1 MapLibre GL chosen over commercial Mapbox — BY DESIGN

[`frontend/src/components/MapPanel.tsx`](../frontend/src/components/MapPanel.tsx) uses MapLibre GL (BSD-3, fork of pre-license-change Mapbox GL). Same WebGL UX, no US-vendor lock-in, no API token. Consistent with the demo's *"nothing left Greek infrastructure"* pitch.

- **Tile source today:** `basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` (free hosted vector style).
- **For full sovereignty:** swap to self-hosted Protomaps (`.pmtiles`) — same MapLibre style format, zero outbound calls. Documented as a Day 21 polish task.
- **CSP impact:** production deployment must include `basemaps.cartocdn.com` in `connect-src` until the swap.

### 6.2 Inline AOI GeoJSON instead of fetching `/data/geojson/aegean_sea.geojson` — DEBT

The Aegean polygon is hardcoded in `MapPanel.tsx`. When per-watch region overlays land (Ionian, Evros, Eastern Med, custom bboxes), we'll need either:
- a Vite static route at `/data/*` mapped to the repo's `data/` directory, OR
- copy the GeoJSON files into `frontend/public/data/`

~5 lines of vite config either way.

### 6.3 No "active watch" zoom-to-region behaviour — DEBT

The map shows the same Aegean AOI regardless of the active Watch. A watch with `region=evros` should re-zoom to the Evros corridor. Wire `MapPanel` to read `activeWatch.spec.region` from the store and switch the GeoJSON source accordingly.

### 6.4 No Vitest tests on the frontend yet — DEBT

Zero frontend unit tests. The `CitableText` click handler is the gold-medal moment — a 3-test Vitest suite (renders, click fires fetchCitationChain, applies confidence color) is the minimum bar before demo dry-runs.

### 6.5 Vite dev server binds to `localhost`, not `127.0.0.1` on Windows — RESOLVED 2026-05-02 (gotcha)

On Windows Vite binds only `::1` (IPv6 loopback) — so `http://127.0.0.1:5173` returns connection-refused. Hit `http://localhost:5173` instead. Documented here so the next contributor doesn't waste 10 minutes on it. (Linux/macOS bind both IPv4 and IPv6.)

### 6.6 No Playwright/Cypress end-to-end test for the citation click — DEBT (Day 21 work)

`scripts/test_e2e.py` covers the API layer but doesn't drive the UI. Pre-demo polish should add a Playwright run that: types a watch, waits for the brief, clicks BLUF, asserts the map flew to the right coords, the graph highlighted the right node, the evidence modal opened.

### 6.7 Citation click is section-level, not sentence-level — BY DESIGN (with caveat)

The plan's spec hinted at sentence-level granularity. The current `CitableText` makes the whole section text clickable because the backend stores citations at the section level (each `BriefSection.citation_node_ids` covers all of `section.text`).

- **Why this is the correct choice today:** matches our data model, no backend changes, and analysts read briefs section-at-a-time anyway.
- **Path forward (post-demo):** if sentence-level becomes worth it, the Supervisor's prompt would need to emit per-sentence citation maps, and `CitableText` would need a sentence-tokenizer pass. Material work — not Week-3 scope.

### 6.8 CitationExpansion has no outside-click dismiss — DEBT

The inline panel can only be dismissed via its X button or by clicking another section. Clicking outside the brief panel doesn't clear it.

- **Path forward:** add a global click-outside listener that calls `clearCitation()` when the target is not within the brief panel. ~10 lines.
- **Demo impact:** none — the demo flow always involves clicking the next sentence, which dismisses the previous expansion.

### 6.9 `recommendation.urgency` lives in untyped `extra` dict — DEBT

`BriefSection.extra.urgency` is read with `as string` in `BriefPanel`. A backend typo would silently render the default-green ROUTINE chip.

- **Path forward:** add `urgency` as a typed Pydantic field on `BriefSection` (or split into a dedicated `RecommendationSection`). Keeps validation server-side.

### 6.10 EvidenceModal lacks a focus trap — DEBT (a11y)

Tab key escapes the modal back into the underlying page. Mouse-driven demo navigation is unaffected, but proper a11y compliance loops tab focus inside the modal until close.

- **Path forward:** wrap the modal contents in a focus-trap primitive (focus-trap-react, ~200 lines + dep) or roll our own with `useEffect`-managed focusable-element queries. ~30 lines either way.

### 6.11 SAR image 404 path silently hides the `<img>` — DEBT

`EvidenceModal`'s `onError` sets `display: "none"` on the image element. If a Vessel has a `sar_tile_id` field but the PNG was evicted from the cache, the modal silently omits the image without an error message. (The "no SAR tile cached" placeholder only fires when the id is missing entirely.)

- **Path forward:** track image-load state in component state instead of mutating the DOM, render a `"SAR tile not in cache (id: {id})"` placeholder on error.

### 6.12 `/static/` mount has no auth — DEBT (production blocker)

`StaticFiles(directory=settings.cache_dir)` serves SAR tiles to anyone who can reach port 8000. The audit logger records evidence access via the citation-chain endpoint, but the `/static/` route bypasses it entirely.

- **Path forward (production):** wrap the static handler in an auth dependency that (a) checks the operator's session, (b) writes a `evidence.served` audit entry, (c) optionally rate-limits per-operator. The `EvidenceModal` would then need to fetch via authenticated `axios` instead of a raw `<img src>`.
- **Demo impact:** zero — single-user dev environment. Flagged for the deployment hardening checklist.

### 6.13 NewsEvent modal doesn't iframe the article — BY DESIGN

Most outlets set `X-Frame-Options: deny`, so iframing the original article would render a blank box. The modal ships a "Open original article" button that opens in a new tab — correct UX but worth noting since the plan implied "raw evidence" rendered inline.

### 6.14 CompositeEvent modal lacks linked-source list — DEBT

`CompositeEvent` evidence today shows only the threat grade + summary + centroid + created_at. The richer view would list each `COMPOSED_OF` source with its own clickable card (which opens that source's evidence in a stack). ~40 lines but adds modal history-stack complexity.

- **Demo impact:** low — clicks usually originate from the BriefPanel (which already shows source cards), so the user rarely opens a composite directly.

### 6.15 MapLibre `filter` doesn't accept `feature-state` expressions — RESOLVED 2026-05-02

The Day-20 vessel-pulse ring layer used `filter: ["boolean", ["feature-state", "active"], false]` to render the ring only on cited vessels. MapLibre validates the `filter` field at style-parse time before any feature has state, so feature-state expressions in filters throw at layer creation.

Fixed by always rendering the layer and driving visibility via a `paint` expression on `circle-stroke-opacity` (paint expressions ARE re-evaluated per frame and DO read feature-state). Same visual outcome, valid style.

- **Lesson:** for any per-feature visibility/styling driven by feature-state in MapLibre, use paint expressions, not layer filters. Filters are a static-time concept; feature-state is runtime.

### 6.16 React Query `data` undefined window during HMR — RESOLVED 2026-05-02

`SystemBadges` initially read `health.llm.ok` after a `health &&` guard, which only proves `health` is truthy. During Vite HMR transitions or a partial backend response, `health` could be `{}` and `health.llm` undefined, crashing the render.

Fixed by deeper optional chaining (`health?.llm?.ok`, `health?.llm?.model`) and gating the badge render on `health?.llm` (not just `health`). Defensive against any future backend that returns a partial shape.

---

## 6. API & frontend

### 6.1 Only `/health` and `/api/watches/templates` are wired — BY DESIGN

`POST /api/watches` exists and parses queries via the LLM, but `GET /briefs/{id}`, `GET /briefs/{id}/citation/{section_id}`, `GET /audit`, `GET /graph`, and the WebSocket progress stream are not yet implemented.

- **Resolution timing:** Day 12.

### 6.2 No frontend code beyond the scaffold — BY DESIGN

Vite+React scaffold exists; no components are written yet.

- **Resolution timing:** Days 15-21.

---

## 7. Demo strategy & data

### 7.1 Demo runs against pre-seeded historical data — BY DESIGN

The demo scenario is **March 14-20, 2024 — Aegean EEZ Activity** (a documented period of Turkish research vessel activity near the Dodecanese). The seed script will pre-process all SAR/AIS/GDELT/Telegram data for that window into Neo4j; the demo queries this pre-loaded data.

- **Why:** Sentinel-1's 6-day revisit + AISStream's no-historical free tier make it impossible to guarantee fresh demo-day data. This is the standard approach for any geospatial intelligence demo — the alternative (live data, fingers crossed) would be unprofessional.
- **What to say to judges:** *"This demo runs on a real historical scenario from March 2024. In production deployment the same pipeline runs on live data with a 15-minute lag from satellite ingestion."*

### 7.2 Demo budget vs. real run-time — WORKAROUND

The demo script targets <60 s per Watch. With pre-seeded data and an 8 GB GPU, this should hold. With live data (or CPU-only Ollama), expect 3-5× longer.

- **Mitigation:** pre-cache the brief outputs for the primary demo Watch (`Aegean — last 7 days`) so the first click is instant. The second live-typed Watch can show actual processing time.

---

## 8. Windows-specific

### 8.1 Default console encoding cp1252 — RESOLVED

PowerShell on Windows defaults to cp1252, which can't render Greek characters or Rich's box-drawing glyphs. Surfaced twice during foundation verification (`→` arrow in test scripts).

- **Resolution:** [`start.ps1`](../start.ps1) now sets `PYTHONUTF8=1` and `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`. If you run scripts directly without going through `start.ps1`, set those manually first.

### 8.2 First Telegram run requires interactive code entry — BY DESIGN

Telethon's first connection to a phone-bound API requires the user to type a Telegram-issued login code into the terminal. After that, the session pickles to `.telethon/damocles.session`.

- **Operational impact:** the seed script's Telegram step (Day 6) cannot run unattended on its first invocation. Every run after the first is fully automatic.

### 8.3 Docker Desktop required for Neo4j on the dev machine — BY DESIGN

GCP deployment uses Neo4j as a systemd service; Windows dev uses Docker Desktop. Documented in [credentials.md §2](credentials.md).

---

## 9. Privacy, scope & legal

### 9.1 Telegram sensor reads PUBLIC channels only — BY DESIGN

[`backend/sensors/osint.py`](../backend/sensors/osint.py) (when written) and the curated `MONITORED_CHANNELS` list will only include public channels. Reading restricted channels would require membership or invite, which is out of scope.

### 9.2 Audit log is locally-rooted — DEBT

The Merkle chain is internally consistent and tamper-evident *given access to the local store*. There is no external anchor: a determined operator with full DB access could replace the entire chain end-to-end and the verifier function would still pass.

- **Path forward:** publish the daily root hash to a public timestamping service (OpenTimestamps + Bitcoin, or a Greek government PKI) so the chain is anchored externally.
- **Demo impact:** none — judges will see the local verify_chain() pass.

### 9.3 Coarse maritime polygons are not legal boundaries — BY DESIGN

`data/geojson/greek_eez.geojson` is a hand-drawn coarse outline. The properties.note explicitly disclaims legal-boundary status. Production should source from MarineRegions Maritime Boundaries v12 or similar.

---

## 10. External-service reliability

These aren't our limitations but they directly affect the demo. Document them so we can monitor.

| Service | Risk | Demo impact | Mitigation |
| --- | --- | --- | --- |
| Sentinel Hub | OAuth token endpoint occasionally times out | Seed step retries; live demo unaffected (uses pre-seeded data) | None needed — hits during seed only |
| AISStream | WebSocket can disconnect under load | Capture script has reconnection logic (TODO Day 6) | Multi-attempt capture window |
| OpenSky | Historical endpoint slow (5-30 s) | Seed only; cached after first run | Aggressive disk caching |
| GDELT | Master file index 99.9% uptime, individual 15-min CSVs occasionally missing | Skip-on-404 in OSINT sensor | Pull from previous 15-min slot if current missing |
| Gemini | Free-tier daily quota | Dev only; production uses Ollama | Documented swap procedure |
| Telegram | Per-app rate limits, occasional `FloodWaitError` | OSINT seed step pauses 30 s on flood | Telethon handles automatically |

---

## Resolved limitations (history)

### gdelt PyPI metadata bug — resolved 2026-05-02

`gdelt==0.1.10` had `geopandas (>-1.7)` typo blocking `uv sync`. Removed from `pyproject.toml`; the plan recommends direct CSV fetches anyway.

### sentinelhub 3.10.4 unresolvable on Python 3.12 darwin — resolved 2026-05-02

Loosened to `sentinelhub>=3.10` (resolved to 3.11.5) and restricted `tool.uv.environments` to win+linux.

### CFAR guard ring too small for real vessel sizes — resolved 2026-05-02

Defaults bumped from `guard=2, training=6` to `guard=4, training=8` after synthetic-target tests showed contamination of training cells by larger targets. 25×25 outer window, still <200 ms per 1024×1024 patch.

### Windows cp1252 console encoding — resolved 2026-05-02

`PYTHONUTF8=1` and `[Console]::OutputEncoding=UTF8` set in `start.ps1`.

### Gemini 2.0-flash daily quota exhaustion — resolved 2026-05-02

`GEMINI_MODEL` env var added. `.env` switched to `gemini-2.5-flash-lite`. `.env.example` documents the swap procedure.

### GDELT 2.0 field offsets off by one — resolved 2026-05-02

ActionGeo_Lat/Long moved from fields 55/56 (v1) to 56/57 (v2 added ADM2Code throughout the geography blocks). Caught when 0 events came back from a slot that the diagnostic showed had passing rows; the smoking gun was `lat=27897` (an ADM2 feature ID, not a latitude). All ActionGeo offsets corrected, unit tests pinned to v2 schema, sensor docstring updated.

### GDELT dual country-code scheme — resolved 2026-05-02

`Actor1/2CountryCode` use CAMEO codes (mostly ISO 3166-1 alpha-3, e.g. `GRC`/`TUR`); `ActionGeo_CountryCode` uses FIPS 10-4 (`GR`/`TU`). The plan's docstring claimed FIPS-only, which dropped most matches against real data. `DEFAULT_ACTOR_COUNTRIES` now contains both representations.

### Greek tonos breaks naive casefold matching — resolved 2026-05-02

Telegram keyword matcher couldn't match `ΑΙΓΑΙΟ` (no tonos, monotonic Greek convention) against `Αιγαίο` (with tonos) under `str.casefold()`. The matcher now NFD-normalizes and strips combining marks before substring matching. Same class of fix incidentally handles Turkish `İ`/`I`/`ı`/`i` and any other diacritic-bearing language. Unit-test pinned to the exact phrase that surfaced the bug.

### GDELT executor used global bbox, fusion never crossed sensors — resolved 2026-05-02

The Day 7 seed produced 0 cross-sensor fusion edges in part because `WatchExecutor._run_gdelt` was passing the global bbox (a habit borrowed from the standalone smoke test). Fusion needs strict bbox filtering to keep events within haversine reach of SAR detections. The executor now uses the watch bbox + 2° expansion margin for fusion-driven runs; the standalone smoke test (`scripts/test_gdelt.py`) keeps the global bbox by design.

### SAR preview NaN-pixel cast warning — resolved 2026-05-02

`np.uint8` cast emitted `RuntimeWarning: invalid value encountered in cast` when a SAR tile contained NaN cells (open ocean far from any backscatter). Now wrapped in `np.nan_to_num(safe, nan=-25.0, posinf=0.0, neginf=-25.0)` before clipping. PNG previews render correctly with no log spam.

### `UnboundLocalError` in BaseAgent retry path — resolved 2026-05-02

`except AgentValidationError as exc:` in `BaseAgent.run()` left `exc` bound only inside the except block (PEP 3134 deletes the variable on exit). Subsequent reference outside the block raised `UnboundLocalError`. Captured the message into `first_error: str | None = None` outside the except block. Two unit tests pin the retry path so this can't regress.

### Greek final sigma + inflection in the geocoder — resolved 2026-05-02

Two Greek-specific gotchas surfaced when geocoding Telegram messages:
- `"Σάμος".casefold()` keeps the final ``ς`` while `"ΣΑΜΟΣ".casefold()` produces a regular ``σ`` — different strings under substring match.
- Greek nouns inflect across cases: `Σάμος` (nominative) becomes `Σάμο` (accusative). The gazetteer only had the nominative form so accusative mentions never matched.

Fixed by unifying both sigma forms in `_normalize` (`s.replace("ς", "σ")`) and by emitting a trailing-sigma-stripped variant alongside the original alias at gazetteer load time. Test pinned to the exact accusative phrase that broke.

### Geocoder ordering: longest-alias-first vs leftmost-in-text — resolved 2026-05-02

The first matcher iterated places by alias-length-desc, so for `"Cesme'den Chios'a ferry hattı"` it returned **Chios** (which appears later in the text but happens earlier in the gazetteer iteration order). Refactored `geocode_text` to compute all alias matches and return the leftmost in-text, with `-alias_length` as tiebreaker so `Ege Denizi` still beats `Ege` at the same offset.

### Gemini 3 thinking tokens consume `max_output_tokens` — resolved 2026-05-02

Gemini 2.5 and 3 models reserve a non-deterministic share of `max_output_tokens` for internal "thinking" tokens before producing visible output. With `max_tokens=1024` and a busy prompt, ~1900 tokens went to thinking and the JSON answer truncated at 71 visible tokens — `json.loads` then raised `Unterminated string starting at: line 2 column 15`.

Two fixes layered:
1. **Migrated from `google-generativeai` 0.8.x to `google-genai` 1.74+.** The old SDK didn't expose `thinking_config` at all; the new one supports `ThinkingConfig(thinking_level="minimal")` which Google documents as "the closest to disabling thinking" for Gemini 3 Flash.
2. **Bumped `BaseAgent.max_tokens` from 1024 to 2048** as a belt-and-suspenders headroom margin.

The migration also let us drop the `asyncio.to_thread` shim — `google-genai` is async-native via `client.aio.models.generate_content()`. Pulled in pydantic 2.13 + httpx 0.28 + ollama 0.6 along the way (the old over-pinned versions were incompatible with the new SDK; loosening to ranges resolved cleanly).

References:
- [Gemini 3 Developer Guide](https://ai.google.dev/gemini-api/docs/gemini-3)
- [GitHub: thinking models truncate output when max_output_tokens set](https://github.com/googleapis/python-genai/issues/782)

---

## Phase 2 — Day 22 — DuckDB persistence layer

### AIS sensor not migrated to write-through cache (deferred to Day 23)

The `AISSensor` is a *streaming* sensor — it opens an AISStream WebSocket, captures vessel positions for `ais_capture_seconds`, and closes. The capture window's identity is `(bbox, capture_duration, wall_clock_at_start)`, not `(bbox, time_from, time_to)`. Caching it under the same key shape as GDELT/Sentinel-1 would either over-cache (returning stale broadcasts as fresh) or under-cache (every fetch is a miss because `now()` differs). The honest approach is to **persist** AIS rows on every capture into `raw_ais` (so the standing scan still benefits) but **not short-circuit** the capture itself. Day 23 wires this when the standing scan lands — the standing scan runs the live capture once daily; user watches with `mode='cached'` then read the union of recent rows from `raw_ais` instead of opening a fresh stream.

### Telegram sensor cache key needs `(channels, keywords)` folded in

`TelegramSensor.fetch()` accepts `channels` and `keywords` kwargs that mutate the result. The cache mixin's `_run_with_cache(... extra={...})` parameter is in place for this; Day 23 wires the kwargs through. Until then, Telegram fetches uncached.

### DuckDB single-writer concurrency

DuckDB allows many readers but serialises writes through a per-database lock. With sensors running in parallel inside the same `WatchExecutor.run()`, write contention is bounded (each sensor finalises its writes once). With *multiple WatchExecutor.run() coroutines* running (e.g. user watch + standing scan overlapping), the writers will queue. Acceptable for the demo; if we ever need multi-watch concurrency we move sensor cache writes into a per-process queue consumed by a single writer thread.

### DuckDB spatial extension may be unavailable offline

`INSTALL spatial; LOAD spatial;` requires either a cached extension or network at first boot. `DuckDBStore.connect()` falls back to schema-without-spatial on `IOException`; nothing in the cache path uses GEOMETRY columns, so the fallback only loses `ST_*` helpers. Spatial queries Day 23+ (e.g. AoI containment) check for the extension and degrade gracefully to bbox-only filters.

### `payload_json` doubles storage for cached rows

We persist both the structured columns *and* the full Pydantic JSON in `payload_json` so re-reads decode to identical objects (round-trip fidelity matters for the citation chain — `Vessel.id` must survive). Costs ~1.2-1.5x disk vs columns-only. Justified for now; if the file grows past a few GB we'll switch reads to column-rebuilds.

---

## Phase 2 — Day 23 — Greece-wide standing scan

### Scheduler runs in-process (single FastAPI worker)

`StandingScanScheduler` is an `AsyncIOScheduler` started in the FastAPI lifespan. With a multi-worker uvicorn config (e.g. `--workers 4`) every worker would try to schedule its own scan. Demo deploy is single-worker; production needs either an `apscheduler.executors.pool.ProcessPoolExecutor`-coordinated lock or a sidecar scheduler (k8s `CronJob`, GCP Cloud Scheduler hitting `POST /api/standing/scan`). Documented for the deploy doc.

### Scheduler scrapes sensor counts from progress events instead of return values

`_run_scan()` parses `"name: N events"` strings from the executor's progress stream to populate `scan_runs.sensor_counts`. A cleaner change is to extend `WatchExecutor.execute()` to yield a structured `final_summary` event at the end. Deferred — current parse handles the existing message shape.

## Phase 2 — Day 24 — AI Areas of Interest

### Alpha-shape collapses on small clusters (n<4)

`alphashape.alphashape(pts, 0.5)` returns a degenerate `LineString` or empty geometry when there are fewer than ~4 well-separated points. We catch the failure and fall back to a buffered convex hull (`buffer(0.05°)`). Trade-off: small clusters get a slightly-too-round polygon instead of a tight hull. Acceptable for the demo's visual narrative; mathematically pickier users can tune `FALLBACK_BUFFER_DEG`.

### LLM naming may produce inconsistent transliteration

The naming agent returns `{name_el, name_en}`; we pass `temperature=0.2` and a tight schema, but the LLM occasionally swaps Greek/Latin scripts or returns inflected vs nominative forms across runs of the same scan. We don't post-process. Two demo runs of the same scenario may show "Λεκάνη Λήμνου" / "Lemnos Basin" once and "Νησίδες Λήμνου" / "Lemnos Islets" the next. Documented as expected variance.

### Clusters over Greek-wide scans use lat/lon Euclidean, not haversine

HDBSCAN runs on `(lon, lat)` directly; at Greek latitudes (~38°) one degree of longitude is ~88km vs 111km for latitude. Clusters are slightly elongated in the lon direction. Negligible at the visualisation level for this geography; for tighter clustering we'd project to UTM 34N before HDBSCAN.

## Phase 2 — Day 25 — User-drawn polygons

### terra-draw mounts lazily; no fallback if its bundle fails

`MapDrawControl` dynamic-imports `terra-draw` and `terra-draw-maplibre-gl-adapter`. If either bundle fails to load (e.g. CSP block in a hardened deploy), the "Draw AoI" button still appears but clicks no-op. We log a `console.warn` and continue. A graceful degradation path (disable the button when `drawRef.current` is null) is a 5-line follow-up.

### Polygon geometry is sent as raw GeoJSON (no winding-order normalisation)

The backend uses `shapely.geometry.shape(geom).wkt` to convert. Shapely accepts both winding orders, so the backend never rejects. If we ever need RFC-7946-strict GeoJSON (right-hand rule for polygons) for export, we'll normalise via `shapely.geometry.polygon.orient(p, sign=1.0)`.

## Phase 2 — Day 26 — Sigma.js graph migration

### ForceAtlas2 runs synchronously on the main thread

Each layout pass iterates 220 times via `forceAtlas2.assign(graph, { iterations: 220 })`. For Greek-wide graphs (5k+ nodes) this can block the main thread for 200-500ms. The graphology team ships `graphology-layout-forceatlas2/worker` which moves it to a Web Worker; switching is a 6-line change deferred to post-demo when we benchmark on the EYP target hardware.

### Citation-pulse halo dropped vs Cytoscape

Cytoscape gave us a free animated outer-ring on the active node (the `node.active` style + `border-width: 3`). Sigma's WebGL programs don't include a halo by default — we'd need a custom fragment shader. We compensate with a 1.8x size bump + cream colour for the active section node. Visual effect is comparable; the *animated* pulse is the loss, and adding it back is a single custom-program file (deferred).

### `graphology` does not auto-deduplicate parallel edges across reloads

The graph payload from `/api/graph/{watch_id}` may contain the same `(source, target, type)` triple twice across a refresh. We construct with `multi: true` so additions don't error, but the visual gets thicker edges. The legacy Cytoscape code synthesised stable IDs (`e${i}-${src}-${tgt}-${type}`) — Sigma picks edge IDs on its own. Acceptable; if it bothers anyone we'll synthesise IDs the same way and switch to `multi: false`.

## Phase 2 — Day 27 — Rich map layers

### Satellite basemap is overlaid above the dark vector style, not swapped

When the analyst toggles "Satellite", we add an EOX `s2cloudless` raster source on top of the dark CARTO style instead of replacing the style. The visible result is identical (raster is fully opaque at zoom 5+) but the dark style still consumes GPU. Cleaner approach: swap the entire `mapStyle` URL on toggle. Deferred because mid-style swaps reset all dynamic sources, requiring a re-add of every Phase 2 layer — one-shot fix possible via an `idle` event listener; not load-bearing for the demo.

### News heatmap H3 polygons cross the antimeridian incorrectly

`h3.cell_to_boundary` returns lat/lng pairs, and our adaptor builds polygon coords without checking for ±180° crossings. Inside Greek territory this never triggers; the moment we widen scope to e.g. Pacific scopes it would draw degenerate world-spanning polygons. Documented as a known scope-restriction; fix is a `splitDateline` helper applied per cell.

### Trajectory rendering doesn't fade by age within a single line

Trajectory polylines have one global `line-opacity`; older points within a single line look the same as newer ones. The plan called for "opacity decay over time" — to do that properly we'd encode age as a per-vertex attribute and use `["interpolate", ["linear"], ["get", "age_normalised"], ...]`, which requires emitting MultiLineString features one-segment-per-step or using a custom shader. Deferred; current rendering is still informative (one trail per vessel, opacity uniform) and matches what other open-source AIS visualisers do.
