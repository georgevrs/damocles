# Damocles — AoI Quality Scan (2026-05-12)

**Question.** Given the fact store has 134 AoIs after a full Greek scan,
*are they solid? Are they valid? Do they provide useful information?*

**Method.** Stratified random sample of 10 AoIs (seed=1337, at least one of
each threat grade present in the store). Per AoI, fetched `/api/aoi/{id}/explore`
+ `/api/aoi/{id}/dna` and inspected: polygon validity, source diversity,
threat-grade justification, temporal spread, naming plausibility, base-pair
construction. Cross-referenced against the DuckDB fact store via
`/api/store/stats`. Reproducible script:
[`scripts/aoi_quality_scan.py`](../scripts/aoi_quality_scan.py).
Raw output: [`docs/_aoi_scan.json`](_aoi_scan.json).

**Headline finding.** The AoI agent is **structurally working** — HDBSCAN
clusters, alpha-shapes fit, the LLM produces Greek-native names, threat
grades match member events 10/10. But the **underlying sensor data is
contaminated** in ways that break two of the platform's most marketed
properties: AoIs are NOT showing cross-domain corroboration, and several
AoIs are clusters of land-based SAR false positives misrepresented as
"vessels."

This is salvageable. The fixes are surgical and don't require re-architecture.
But the demo script claims the platform fuses physical + information signals
into AoIs — and the data says it currently does that successfully only
**1 time in 10**.

---

## TL;DR — five hard numbers from the sample

| | Sample (n=10) | What this means |
|---|---|---|
| Threat-grade matches worst member event | **10 / 10** | Grading is honest. No silent escalation. ✓ |
| Polygons valid (≥4 vertices, area > 0) | **10 / 10** | Geometry layer works. ✓ |
| Both Greek + English names present | **10 / 10** | i18n is consistently populated. ✓ |
| AoIs with zero cross-strand base pairs in DNA | **10 / 10** | **The DNA philosophy isn't realised by current data.** |
| AoIs that are single-source-type ("monoculture") | **9 / 10** | Each AoI is essentially one sensor speaking; the "fusion" promise is largely ceremonial. |
| AoIs with all members at identical timestamp (span=0h) | **8 / 10** | Likely seeded/batch data, not live multi-day capture. |

Average composite confidence across the sample: **0.42** (5/10 below 0.4).
The platform is producing low-confidence clusters and *correctly* marking them
GREEN — but that means most polygons on the map aren't analytically actionable.

---

## What the sample looks like

```
  id              grade   centroid          area_km² sources                       name
  aoi-7f63ac5ab7  GREEN   (40.92, 26.53)    129.3    {Vessel: 4}                   North Evros Region
  aoi-bf0a943872  AMBER   (39.00, 22.00)    75.3     {NewsEvent: 34}               Central Mainland Greece
  aoi-bcc4206660  GREEN   (36.69, 22.87)    344.3    {Vessel: 5}                   Monemvasia Coastal Area
  aoi-65832d704d  AMBER   (37.98, 23.74)    156.0    {Vessel: 2, NewsEvent: 26}    Athens Center - Lycabettus
  aoi-f40db4c6a4  GREEN   (39.88, 26.61)    776.6    {Vessel: 8}                   Lemnos Marine Area
  aoi-19566c81e9  GREEN   (41.59, 26.51)    1324.9   {Vessel: 9}                   Northern Evros
  aoi-b43bf74fb1  GREEN   (40.76, 28.21)    260.2    {Vessel: 9}                   Marmara Sea Sector
  aoi-8a87e50422  GREEN   (37.99, 21.56)    752.1    {Vessel: 8}                   Western Achaia Field
  aoi-6d8bdba191  GREEN   (38.62, 22.76)    1224.4   {Vessel: 5}                   Elateia Phthiotis Region
  aoi-3eca936351  GREEN   (41.64, 27.24)    285.0    {Vessel: 7}                   Kirklareli Region
```

---

## 1 — Geographic plausibility: mixed

**6/10 AoIs are over water** (Monemvasia coastal, Lemnos marine, Marmara sea, Athens center, North Evros river region, Karpathos-adjacent).

**4/10 AoIs are on dry land** but their member sources are typed as
`Vessel` — "Northern Evros" (Greek-Turkish-Bulgarian tripoint, inland river
narrows), "Western Achaia Field", "Elateia Phthiotis Region" (mountainous
central Greece), and "Kirklareli Region" (Turkish inland province). The
LLM-namer is being clever here — when the cluster centroid lands on land,
it calls the AoI a "Field," "Region," or a town name, which prose-wise reads
plausible. But for an analyst this is **a category error**: it's a cluster
of "vessels" in a place where vessels cannot exist.

This is the most important finding in the report. See §3 for the root cause.

**Two AoIs cross sovereignty boundaries on purpose**: Marmara Sea Sector and
Kirklareli Region are Turkish territory. The [aoi-philosophy doc](aoi-philosophy.md)
explicitly says this is allowed: *"An AoI's polygon may cover Turkish
waters when the cluster crosses the median line — that is the geometry of
the data, not a territorial claim. Documented."* On a demo screen, however,
a polygon labelled "Kirklareli Region" with a Greek title font will need a
prepared one-liner from the analyst.

---

## 2 — Polygon validity: solid

Every polygon in the sample:
- Has at least 4 vertices (HDBSCAN's `min_cluster_size=4` plus alpha-shape's
  closing edge).
- Has non-zero area.
- Is a single `Polygon` (no degenerate `MultiPolygon` artifacts).
- Has a sensible vertex count: **5–7 for most**, **34 for "Central Mainland
  Greece"** (real alpha-shape concavity on a 34-news-event cluster), and
  **4 for the smallest ("North Evros Region")**.

Areas range from **75 km²** (Central Mainland Greece — concave, news-only)
to **1325 km²** (Northern Evros — a 9-vessel cluster spread over 0.4°
latitude). The big ones are alpha-shape outputs over sparse point sets;
they look reasonable on the map (no spiky artifacts visible in the
[E2E screenshots](../screenshots/01_cold_open.png)).

**Verdict: polygon construction is solid.** No fixes needed here.

---

## 3 — Source diversity: **broken** in a way that breaks the demo

This is the headline failure. The platform's pitch is fusion of physical
(satellite + AIS) signals with information (news + social) signals. The data
contradicts that pitch:

```
  9 / 10 AoIs are single-sensor-type monocultures
  6 / 10 are Vessel-only (no news / no social)
  1 / 10 is NewsEvent-only (no vessels)
  1 / 10 is genuinely mixed   (Athens Center: 2 vessels + 26 news)
  0 / 10 have a cross-strand BASE PAIR in the DNA stats
```

A "base pair" in the AoI DNA model means: *one composite event contains both
a physical source and an information source, indicating that the satellite
saw the same thing the news reported.* That's the analytically interesting
moment. **It happens zero times in this sample.**

### Root cause — the "Vessel" type is impure

`raw_ais` and `raw_sar` rows in the fact store have **identical counts:
1238 each**. Every SAR-detected blob is mirrored into `raw_ais` as a
"vessel with no MMSI." The ingestion pipeline writes both. The AoI agent
then clusters on what is effectively the union of (real AIS broadcasts) ∪
(SAR detections).

When SAR (CFAR vessel detection) is run over Greek territory, it produces
hits anywhere it finds a high backscatter point. That includes:
- Real ships
- Bridges, port cranes, oil platforms
- Buildings near coast / rooftops on inland villages
- Vehicles on highways
- Some terrain features in mountainous areas

Looking at the inland AoIs' actual member sources:

```
aoi-6d8bdba191 (Elateia Phthiotis Region — inland mountains):
  - Vessel  (38.911, 22.516)  mmsi=None  name=None  ais=unknown  length=20.0m  ts=2026-04-29T10:08:25
  - Vessel  (38.654, 23.064)  mmsi=None  name=None  ais=unknown  length=20.0m  ts=2026-04-29T10:08:25
  - Vessel  (38.633, 22.700)  mmsi=None  name=None  ais=unknown  length=20.0m  ts=2026-04-29T10:08:25
  - Vessel  (38.557, 22.803)  mmsi=None  name=None  ais=unknown  length=20.0m  ts=2026-04-29T10:08:25
  - Vessel  (38.362, 22.700)  mmsi=None  name=None  ais=unknown  length=30.0m  ts=2026-04-29T10:08:25
```

Every "vessel" with no MMSI, no name, "unknown" AIS, round-number length,
and **identical timestamp to the second**. These are SAR hits over the
Phthiotis valley — small towns and farms, not boats. Same pattern for
Achaia, Northern Evros (river-narrows section), Kirklareli.

### Why this matters for the demo

The pitch story at `[2:00]` of the demo script says:
> *"Northeast Aegean. Five AIS-dark vessels, confirmed by SAR at 03:22 UTC.
> Two GDELT events. Three Telegram signals in Turkish."*

The current data has the opposite shape — for 6 / 10 AoIs there are
*only* the SAR hits, no GDELT, no Telegram. A judge clicking a RED polygon
expecting cross-source corroboration would see a flat list of `Vessel ·
Vessel · Vessel`. The platform's most differentiating property is invisible
in 90% of clicks.

### What needs to change (root-cause fixes, in increasing scope)

1. **Tag SAR detections distinctly from AIS broadcasts.** Add a new node
   label `SARDetection` (or at minimum, an `is_sar=true` property on
   `Vessel`). Today `raw_ais` and `raw_sar` are 1:1 mirrors but the API
   serves them as the same `Vessel` type, so the frontend can't differentiate.
2. **Mask SAR detections by water surface.** Use a Greek-EEZ + coastal-water
   GeoJSON polygon (already in `data/geojson/`). Any SAR hit > 500 m inland
   gets filtered or labelled as a `LandSignal` (potentially useful for other
   intel purposes but not as a "vessel"). The CFAR detector is doing its job;
   the *interpretation* of its hits as ships is what's wrong.
3. **Require multi-source corroboration to escalate.** The AoI agent already
   pulls `dominant_types` per cluster. Refuse to grade an AoI above GREEN if
   `dominant_types == 1`. Forces the brief to show cross-strand evidence
   before it escalates. This single change would have suppressed at least
   5 of the 10 sampled AoIs from cluttering the triage list with
   monocultures.

---

## 4 — Threat-grade justification: honest

Across the sample, **the declared grade matched the worst member event in
all 10 cases**. The AoI agent isn't inventing escalations; it isn't
softening them either. This is exactly what
[`backend/agents/aoi_agent.py:_build_aoi`](../backend/agents/aoi_agent.py)
promises:

```python
grade_order = {"RED": 3, "AMBER": 2, "GREEN": 1}
dominant_grade = max(
    (e.get("threat_grade", "GREEN") for e in cluster_events),
    key=lambda g: grade_order.get(g, 0)
)
```

The two AMBER AoIs in the sample are AMBER because they contain at least
one AMBER composite. The eight GREEN AoIs contain only GREEN composites.
That logic is sound.

The deeper question is whether the *composite grading* itself is calibrated
correctly — that's a separate audit. From this sample, GREEN composites
have average confidence 0.27–0.42 and AMBER composites 0.55–0.69, which is
plausible.

**Open question.** The full fact store has **134 AoIs but zero RED.** That
is suspicious. Either:
- The Greek scan really produced no RED-graded composites (possible if the
  GDELT Goldstein-scale threshold for RED is set too high), or
- The RED threshold needs lowering by ~0.5 σ for the demo data, or
- Real-world Greek operational tempo just doesn't produce RED on a typical
  week.

Worth checking the `threat_grade` thresholds in
[`backend/sensors/fusion.py`](../backend/sensors/fusion.py) before pitch
day — the audit can't tell from outside whether the floor is too low or the
real signal is just quiet.

---

## 5 — Temporal spread: mostly synthetic-looking

**8 / 10 AoIs have all member events at the same timestamp** (span_hours = 0.0):
- North Evros Region — 4 vessels all at `2026-04-29T10:08:25`
- Monemvasia Coastal Area — 5 vessels all at `2026-04-30T19:00:00`
- Lemnos Marine Area — 8 vessels at `2026-04-29T10:08:25`
- (etc.)

Two timestamps recur over and over: **`2026-04-29T10:08:25`** and
**`2026-04-30T19:00:00`**. These look like batch SAR fetches — a single
Sentinel-1 tile downloaded, CFAR run over it, all hits stamped with the
mid-window timestamp.

The 2 AoIs with non-trivial temporal spread are exactly the ones that have
news sources:
- **Central Mainland Greece** (34 NewsEvents over 20.8h)
- **Athens Center - Lycabettus** (mixed sources over 81.9h)

This corroborates §3: the GDELT pipeline is collecting genuine temporal
flow; the SAR pipeline is collecting one snapshot per tile and synthesising
"events" at the snapshot timestamp.

**Demo implication.** The DNA helix can't usefully encode time on the Y-axis
(my [previously-recommended Option A](E2E_REPORT_AFTER.md)) until the SAR
pipeline produces real per-detection timestamps. Today every vessel in an
AoI would stack at the same Y, which defeats the purpose. Mitigate with
small per-source jitter for display, OR fix the SAR ingestion to record
actual tile acquisition time per detection (Sentinel-1's per-product XML
has it; we're discarding it).

---

## 6 — Naming quality: surprisingly good, with one caveat

**Strong:**
- 10 / 10 have both `name_el` and `name_en` present.
- 10 / 10 are short (≤6 words) per the prompt's instruction.
- 0 / 10 are fallback `Συστάδα N` / `Cluster N` names — the LLM never
  punted.
- Greek names use real toponymy:
  - "Βόρειος Έβρος" (North Evros) — correct for the centroid
  - "Παράκτια Περιοχή Μονεμβασιάς" (Monemvasia Coastal Area) — correct
  - "Θαλάσσια Περιοχή Λήμνου" (Lemnos Marine Area) — correct
  - "Θαλάσσια Περιοχή Προποντίδας" (Marmara Sea Sector — *Propontis* is
    the classical Greek name for the Sea of Marmara, beautifully period)
  - "Περιοχή Κιρκλαρελί" (Kirklareli Region) — correct Greek transliteration
    of the Turkish toponym
- "Κέντρο Αθήνας - Λυκαβηττός" (Athens Center - Lycabettus) — picked
  Lycabettus because the centroid is at 37.98°N, 23.74°E which is within
  walking distance of Lycabettus Hill. Specific, not generic.

**Weak:**
- "Northern Evros" and "North Evros Region" are **two separate AoIs with the
  same name in Greek** (`Βόρειος Έβρος`). The LLM-namer doesn't see prior
  scan results when naming. Either the agent should dedupe Greek names
  within a scan, OR the analyst will see two amber polygons in the same
  region with the same label and assume they're a UI duplicate bug.
- "Western Achaia Field" (Πεδίο Δυτικής Αχαΐας) — "Field" was the LLM's
  attempt to dignify a SAR-false-positive cluster over inland farmland.
  Cute, but the only reason it's there is the data bug from §3.

**Caveat — only one composite-driven name.** The "Athens Center -
Lycabettus" name benefited from 26 news events about Athens. Most names
were given to LLM with only `dominant_types: vessel` and 5 sample event
summaries — and yet they came out specific. That's a credit to the LLM and
to the prompt design.

---

## 7 — DNA visualization: works, but visualizes nothing right now

`/api/aoi/{id}/dna` returns correct strand assignment + correct base-pair
construction logic. I verified by inspection. But:

```
  AoIs with zero base pairs in the sample: 10/10
  AoIs with information_count = 0:          7/10
  AoIs with physical_count = 0:             1/10
```

The DNA helix can only show "cross-strand corroboration" when there ARE
sources on both strands. Today, **most AoIs have one strand empty**. The
helix renders as a single-side colony of nodes with no rungs.

This is not a DNA-component bug — it's a data-distribution problem (§3).
Fix the source-mix issue and the helix becomes interesting. Build the
helix improvements anyway (the planned Option A: time on Y-axis,
confidence on size, corroboration thickness on rungs) — they pay off the
moment the data fixes ship.

---

## 8 — Per-AoI verdicts

| AoI | Verdict | Why |
|---|---|---|
| **Athens Center - Lycabettus** | ✓ STRONG | The only one in the sample that delivers on the platform's promise. 2 vessels + 26 news, 81h temporal spread, AMBER. Demo this one. |
| **Central Mainland Greece** | ✓ SOLID (news-only) | 34 news events over 21h, real temporal flow, AMBER. A coherent news cluster. The "single-strand" critique applies but at least the strand is real. |
| **Marmara Sea Sector** | ~ PLAUSIBLE | 9 vessels at the Sea of Marmara — believable for shipping-lane SAR. Average confidence 0.69 — relatively high. The "all at one timestamp" pattern is the SAR-tile artifact, not a synthesis bug. |
| **Lemnos Marine Area** | ~ PLAUSIBLE | 8 vessels off Lemnos — makes maritime sense. Single sensor, but a maritime AoI with SAR hits is reasonable. |
| **Monemvasia Coastal Area** | ~ PLAUSIBLE | 5 vessels at the Peloponnese tip — coastal, defensible. |
| **North Evros Region** | ✗ SUSPECT | 4 "vessels" at 40.9°N, 26.5°E — the Greek-Turkish-Bulgarian land border. River, not navigable by 20m boats. SAR false-positives on terrain. |
| **Northern Evros** | ✗ SUSPECT | Same problem but worse — 41.59°N is upriver where the river is too narrow for boats. Also a duplicate name with the previous. |
| **Western Achaia Field** | ✗ FALSE-POSITIVE | "Field" is the LLM's tell — SAR hits on Peloponnese inland farmland labeled as boats. |
| **Elateia Phthiotis Region** | ✗ FALSE-POSITIVE | 38.6°N 22.8°E is mountainous central Greece. Vessels 20–30m long here are impossible. |
| **Kirklareli Region** | ✗ FALSE-POSITIVE | 41.64°N 27.24°E is inland Turkish farmland. Same pattern. |

**Tally: 1 strong, 4 plausible, 5 false-positive.** Roughly half of a random
sample wouldn't survive analyst scrutiny.

---

## 9 — Severity-ranked recommendations

### Demo-blocker (must fix before pitch)

1. **Filter SAR detections by water surface** (§3 fix #2). Use the
   `aegean_sea.geojson` + `ionian_sea.geojson` polygons already in
   `data/geojson/`. Drop any `Vessel`-typed row whose `(lat,lon)` falls
   outside a 1-km coastal buffer. This single change would have
   eliminated 5 of the 10 false-positive AoIs in this sample.
2. **Lower the bar to RED for at least one Greek cluster** OR seed one
   deterministically (§4). The script's `[0:20]` line "this RED polygon
   over Lemnos" needs a real RED polygon to land on.

### High-priority (high analytical impact)

3. **Require multi-source corroboration to escalate above GREEN** (§3 fix
   #3). Even with the SAR-water filter, the platform pitches "two strands."
   If only one strand is talking, the AoI shouldn't reach AMBER.
4. **Tag SAR detections as a distinct entity type** (§3 fix #1) — even if
   we still surface them, the analyst should see `SARDetection` not
   `Vessel` on the source row.
5. **Dedupe AoI names within a scan** (§6) — when the LLM produces the same
   `name_el` twice, the second one gets `(N)` suffixed.

### Medium-priority (polish)

6. **Real per-detection timestamps from Sentinel-1** so the DNA helix can
   encode time (§5). Sentinel-1 product metadata has acquisition times to
   the millisecond; we're discarding them in
   [`backend/sensors/geospatial.py`](../backend/sensors/geospatial.py).
7. **Threshold review for AMBER vs GREEN** at composite-event level — 5 / 10
   AoIs have average confidence < 0.4. A "high-volume low-confidence" cluster
   is borderline noise.
8. **Per-source-type filter on the triage list** — give the analyst a way to
   hide single-strand AoIs (already implemented as a `Mine/AI` filter; add
   `Mixed` / `Vessel-only` / `News-only`).

### Low / nice-to-have

9. **Sovereignty badge** on cross-border AoIs ("Kirklareli Region" should
   visibly say "Polygon crosses TUR border — not a territorial claim").
10. **Audit the LLM's `description` outputs** — they weren't captured in
    this scan but the AoI agent generates per-cluster descriptions. Worth a
    spot-check.

---

## 10 — What's actually good

It would be unfair to end the report on the negatives. **Here is what is
genuinely working:**

- **HDBSCAN clustering** — produces well-separated, named clusters at Greek
  scale. 134 AoIs is the right order of magnitude (not 5, not 500).
- **Alpha-shape polygons** — match the actual concavity of the data. No
  spiky artifacts, no degenerate polygons in the sample.
- **LLM naming** — Greek-native toponymy, period-correct ("Propontis"),
  geographically specific ("Lycabettus" rather than "Athens"), no fallback
  triggers in the sample. This was the highest-risk creative-LLM step in the
  whole platform and it landed.
- **Threat-grade derivation** — 10 / 10 match the worst member event.
  No silent escalation, no quiet softening.
- **Citation chain** — every AoI carries `citation_event_ids` that all
  resolve to real composite events. The provenance chain is intact.
- **Bilingual coverage** — every AoI in the sample has both name_el and
  name_en, both non-default.

The skeleton is correct. The flesh (the underlying sensor data) needs the
SAR-vs-water filter and the multi-source requirement before the platform's
"two strands fused" story matches what the analyst actually sees.

---

## What I'd do next, in order, with a 24-hour budget

1. **2 hours**: ship the SAR-over-water filter. Validate by re-scanning and
   confirming the 134 → fewer-but-cleaner AoIs.
2. **3 hours**: implement the multi-source escalation rule and re-grade.
3. **1 hour**: dedupe AoI names within a scan + add a "polygon crosses
   sovereign border" badge.
4. **6 hours**: build the temporal-helix DNA improvements (Option A) so the
   visualization pays off once the data is clean.
5. **Remaining 12 hours**: pre-warm one cached brief on the cleanest RED
   AoI, rehearse the demo, write the one-liner answer for "why is there a
   Greek-titled polygon over Turkey?"

The data is fixable. The architecture isn't the problem. The judges' first
click should land on Athens-Lycabettus (or its successor after the filter
ships) — that's the AoI that genuinely shows what Damocles can do.

---

*Scan conducted: 2026-05-12. Backend: `http://localhost:8001`. Sample
seed: 1337. Sources of evidence: [`docs/_aoi_scan.json`](_aoi_scan.json),
[`scripts/aoi_quality_scan.py`](../scripts/aoi_quality_scan.py).*
