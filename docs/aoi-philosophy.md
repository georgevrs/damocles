# Areas of Interest — Philosophy

> *Why Damocles draws polygons on the map without being asked, and why those polygons are first-class entities of the knowledge graph.*

---

## The problem AoIs solve

An analyst staring at a Greek-territory operational map after a 7-day standing scan sees ~600 vessel detections, ~120 news events, ~750 composite alerts, and a continuous spread of activity from Corfu to Kastellorizo. The traditional response is to define a watch by hand: "Aegean — last 7 days," "Evros border — last 24 hours." That works when the analyst already knows where to look. It fails when the data tells them where to look.

Areas of Interest are Damocles's answer to a single question:

> **Where is the data clustering — and is that cluster something the analyst should care about?**

The clustering is a mathematical question. The "should care about" is an intelligence-tradecraft question. Damocles answers both, automatically, without the analyst issuing a query.

---

## What an AoI is, formally

An AoI is a named, threat-graded polygon, anchored in time, attached to its evidence:

```
AoI {
  id:              aoi-b25d041daf
  source:          "ai" | "user"
  name_el:         "Λεκάνη Λήμνου"
  name_en:         "Lemnos Basin"
  polygon_wkt:     POLYGON((24.5 39.0, 25.8 39.0, 25.8 40.6, 24.5 40.6, 24.5 39.0))
  centroid:        (lon, lat)
  threat_grade:    "GREEN" | "AMBER" | "RED"
  threat_summary:  "17 composite events, peak threat AMBER"
  citation_event_ids: [composite-id-1, composite-id-2, ...]   ← auditable provenance
  scan_id:         scan-0b939cea8a50
  created_at, updated_at
}
```

Every field is load-bearing. The polygon defines geometry. The name is for analysts. The threat grade is for triage. The citation list is the audit chain — every AoI points at the events that *made* it exist. If the analyst doesn't trust the AoI, they can drill down to the constituent composites, then to the constituent vessels / news / Telegram messages, and read the raw evidence with their own eyes.

There is no AoI without provenance. That is the philosophy in one line.

---

## Two kinds of AoI, one schema

```
source = "ai"      ← inferred from clustering composite events
source = "user"    ← drawn by analyst with terra-draw
```

Both flow through the same DuckDB table, same Neo4j node type, same map layer, same brief panel. The only practical difference is colour (amber for AI, cyan for user) and that user-drawn ones are the only deletable ones (`DELETE /api/aoi/{id}` requires `source='user'`).

This symmetry is deliberate. An analyst's hand-drawn region around Imbros and an AI-inferred cluster over the Cyclades are equally first-class objects: both can be filtered against, both can scope a watch, both can be cited from a brief, both appear in the audit log.

The lesson from Palantir-style platforms is that "system-generated" and "user-generated" must not have separate plumbing. Once they do, integration is forever bolted-on.

---

## The inference pipeline

```
                 ┌────────────────────────────────────────────────┐
                 │        composite_events (DuckDB)               │
                 │   { centroid_lat, centroid_lon, threat_grade } │
                 └──────────────────────┬─────────────────────────┘
                                        │
                            HDBSCAN (sklearn-extra-style)
                            min_cluster_size = 4
                            min_samples = 2
                                        │
                              ┌─────────┴─────────┐
                              │                   │
                              ▼                   ▼
                    Cluster 0 (n=17)       Cluster 1 (n=8)        ...
                              │
                          alphashape(α=0.5)
                              │
                ┌─────────────┴─────────────┐
                │      polygon_wkt          │
                │      centroid             │
                │      member event IDs     │
                └─────────────┬─────────────┘
                              │
                       LLM naming pass
              (centroid + dominant sources + threat)
                              │
                              ▼
                     ┌────────────────┐
                     │  AoI persisted │
                     │  to DuckDB +   │
                     │  Neo4j         │
                     └────────────────┘
```

Three steps, each chosen for a specific reason.

### Step 1 — HDBSCAN, not K-means

HDBSCAN doesn't require the analyst to know how many clusters there are. K-means does. The whole point of inference is to discover structure we didn't know about; demanding K up front defeats that.

HDBSCAN also identifies *noise* (`label = -1`) — points that don't belong to any cluster. We drop them. This matters: a single vessel detection in the middle of the Ionian shouldn't summon an AoI by itself. Density-based clustering refuses to invent significance where there is none.

Tunables (`min_cluster_size=4`, `min_samples=2`) are sized for Greek-scale operations: four corroborated composite events in spatial proximity is the smallest interesting unit.

### Step 2 — Alpha-shape, not convex hull

Convex hulls are simple but they lie. The Cyclades cluster into a coastal arc; a convex hull around that arc claims the entire interior of the sea, including water that has *no* events. An alpha-shape (α = 0.5) follows the actual concavity of the data — it produces an archipelago-shaped polygon for an archipelago-shaped cluster.

Alpha-shape collapses to a degenerate line when given fewer than ~4 well-separated points. We catch that and fall back to a buffered convex hull (`buffer(0.05°)`) — the analyst gets a slightly-too-round polygon instead of nothing, which is the right trade-off for tiny clusters.

### Step 3 — LLM naming

This is the only LLM step in AoI inference. The LLM gets a tight prompt: centroid coordinates, dominant sources, dominant threat grade, three sample event summaries. It returns `{name_el, name_en, description}` constrained to ≤4 words for each name.

Why the LLM? Because Greek place names matter. "Λεκάνη Λήμνου" beats "Cluster 7" by an enormous margin in analyst comprehension. It also beats "Lemnos area" in the brief: Greek-native phrasing tells the analyst the system is one of them, not a US product running on Greek data.

Why constrained to short names? Because the name has to fit on a polygon centroid label at zoom 6. Long names get truncated and lose their function.

What happens when the LLM is unavailable or returns garbage? Deterministic fallback: `Συστάδα N` / `Cluster N`. Always works. Documented in the limitations doc.

---

## Why we infer them after every scan, not on a schedule

The standing scan is the heartbeat. Every time the scan finishes, the AoI agent runs over the new composite events. This means:

- **AoIs are always anchored to a specific scan** (`scan_id` field). They are *findings*, not configuration.
- An AoI that existed in yesterday's scan but doesn't appear today simply doesn't get re-emitted. The map's AoI layer reflects today's reality, not yesterday's.
- Re-running the scan is the same as "refresh AoIs." There is no separate "regenerate AoI" button — the standing scan IS the regeneration.

This is different from the Palantir model, where AoIs are configuration objects edited by hand and live until manually deleted. We chose the opposite extreme — AoIs are *cheap, regenerable, opinionated outputs* — because intelligence is about now, not about what someone configured six months ago.

User-drawn AoIs do persist across scans (you'd be furious if your hand-drawn polygon disappeared every dawn). They have `scan_id = NULL` and are never auto-deleted. This is the asymmetry the symmetric schema can carry.

---

## Why AoIs are graph nodes, not just polygons

The naive design would store AoIs as a flat list of polygons in a database. We don't.

Every AoI becomes a `(:AreaOfInterest)` node in Neo4j with `[:CONTAINS]` edges to every member composite event. Because composite events have `[:COMPOSED_OF]` edges to their source vessels/news/social signals, the analyst can write Cypher queries like:

```cypher
MATCH (a:AreaOfInterest {name_el: 'Λεκάνη Λήμνου'})-[:CONTAINS]->(c:CompositeEvent)
      -[:COMPOSED_OF]->(s)
WHERE s:Vessel AND s.ais_status = 'dark'
RETURN s.mmsi, s.timestamp, c.threat_grade
ORDER BY c.threat_grade DESC, s.timestamp DESC
```

That single query — *"every dark vessel inside the Lemnos basin AoI, ordered by threat"* — is the kind of question that justifies the entire knowledge graph. AoIs make spatial questions answerable in graph terms.

Briefs cite AoIs the same way they cite individual events. The supervisor agent's prompt (after Phase 2) accepts `aoi://<id>` as a citable identifier alongside `composite://<id>` and `vessel://<id>`. An assessment that says "activity in the **Λεκάνη Λήμνου** AoI shows a 38% week-over-week increase" carries a clickable amber underline that, on click, highlights the polygon, opens its detail card, lights up its member composites in the graph, and reveals the underlying vessels — the same citation chain choreography that drives every Damocles claim.

---

## What AoIs are *not*

It is worth being explicit about the boundaries.

- **AoIs are not predictions.** They describe where activity *is*, not where it *will be*. The threat grade is the maximum grade among constituent composites, not a forecast.
- **AoIs are not areas of operation.** They are not jurisdictional, not assigned to units, not tied to commanders. They are descriptive geometry over evidence.
- **AoIs are not warnings.** A RED AoI is RED because at least one composite event in it is RED. The escalation logic that decides whether to wake an analyst lives in the supervisor agent and the Devil's Advocate, not in the AoI layer.
- **AoIs do not cross sovereignty.** The HDBSCAN runs over the standing scan's bbox (Greek mainland + EEZ + Aegean + Ionian, extended into western Turkey because vessel and news activity originates there). An AoI's *polygon* may cover Turkish waters when the cluster crosses the median line — that is the geometry of the data, not a territorial claim. Documented.

---

## Trade-offs we accepted

**HDBSCAN runs on lon/lat directly, not on a projected coordinate system.** At Greek latitudes (~38°), one degree of longitude is ~88 km against ~111 km for latitude. Clusters get slightly elongated east-west. We tested with UTM-34N projection and the visual difference at the rendering scale was ≤2px. The simpler code wins.

**Alpha-shape is non-deterministic at the boundary.** A cluster with one borderline point can flicker between "in" and "out" between scans, producing a polygon that grows and shrinks slightly. We accept this. Stability would require either bigger `min_cluster_size` (loses small but real clusters) or a temporal-smoothing layer (complexity for marginal gain on a daily cadence).

**LLM naming has variance.** "Λεκάνη Λήμνου" today, "Νησίδες Λήμνου" tomorrow. We could pin names by reusing prior runs' names when the centroid moves <X km, but that introduces stickiness that the analyst would have to debug ("why does this AoI have an old name?"). Variance is the price of fresh inference.

**71 AoIs after the first Greek-wide scan was more than expected.** Some are over Turkish territory because vessel activity originates there. Some are duplicates around the same Cycladic cluster because HDBSCAN's hierarchy chose two valid splits. We chose not to post-process. The map layer panel lets analysts hide them; the threat grade lets analysts triage. Auto-merging would mean making editorial decisions inside the inference pipeline, which is the kind of decision that would later require an "undo" button.

---

## How this differs from how others do it

**Palantir Foundry / Gotham:** AoIs are configuration. Analyst draws, names, owns, and the platform respects. No automatic AoIs — the system never claims to know what's interesting.

**Esri / ArcGIS Pro:** AoIs are layers in a project, hand-drawn or digitised from another dataset. Threat grading is downstream analyst work, not a property.

**Worldmonitor (the open-source platform we surveyed):** No AoI concept. The closest analog is the "country brief" page — country-level rollups, not free-form polygons.

**Damocles:** AoIs are inferred outputs of the standing scan, named by the LLM, threat-graded by the events that birth them, citable from briefs, drawable by analysts on the same plumbing, all subject to the same audit chain. They are not configuration. They are findings.

---

## The judge's question

When a senior officer at the EYP final pitch asks *"why are there polygons on the map I didn't draw?"*, the answer is:

> *"Because seventeen composite events clustered north of Lemnos in the last seven days. The platform is telling you so before you have to look. Every event in that cluster is one click away. If you disagree with the cluster, redraw the polygon yourself — same colour scheme, same plumbing, your name on it."*

That sentence is the philosophy. The implementation is just plumbing serving it.

---

*See also*
- [`docs/architecture.md`](architecture.md) — where the AoI agent fits in the pipeline
- [`docs/data-model.md`](data-model.md) — DuckDB `aoi` table + Neo4j `(:AreaOfInterest)` node
- [`docs/agents.md`](agents.md) — `AoIAgent` contract and the LLM naming prompt
- [`backend/agents/aoi_agent.py`](../backend/agents/aoi_agent.py) — implementation
- [`docs/limitations.md`](limitations.md) §"Phase 2 — Day 24" — known edge cases
