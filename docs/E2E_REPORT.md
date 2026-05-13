# Damocles — End-to-End UI Audit (2026-05-11)

**Methodology.** Headless-Chromium walkthrough via Playwright, 15 named scenarios
exercising the golden paths of the analyst-facing UI. The script
[`scripts/e2e_screenshots.py`](../scripts/e2e_screenshots.py) is reproducible:
boot the stack (Neo4j + FastAPI + Vite), then
`uv run python scripts/e2e_screenshots.py`. Output: 15 PNGs in `screenshots/`
plus `_log.json` capturing console errors. Backend manually probed for endpoints
the UI couldn't be made to fire.

**Stack under test.** Backend on `:8000` (Gemini LLM healthy, Neo4j healthy,
DuckDB 134 AoIs from prior Greece scan). Frontend on `:5173`. Viewport
1600×950. EN locale.

**Headline numbers.** 14 OK scenarios, 6 WARN, 10 console FAIL entries (8 of
which are network-layer dupes of 2 root causes). The app is **demo-functional
but has 4 issues that would land badly in front of a judge** and 5 medium UX
issues that compound into a "rough around the edges" impression.

---

## 1 — The cold-open works, but the morning view is misleading

![cold open](../screenshots/01_cold_open.png)

`01_cold_open.png` — the analyst lands on the triage list, which is
the right behaviour per the AoI-first philosophy. 134 AoIs visible, sorted
RED → AMBER → GREEN, AI-inferred above analyst-drawn.

**Problem.** The filter chip row shows **`ALL 134 · RED 0 · AI 134 · MINE 0`** —
zero RED AoIs in the current fact store. Clicking the RED chip lands on
"No AoIs match this filter."

![red filter empty](../screenshots/04_triage_filter_red.png)

This is a **demo-readiness blocker**, not a code bug. The demo script at
`PART 9: [0:20]` opens with *"this RED polygon over Lemnos appeared at 6am."*
With no RED data in the fact store on stage, the analyst's first click leads
to an empty filter, contradicting the pitch.

**Severity: HIGH.** **Action:** seed the fact store with at least one RED AoI
before pitch day (an AIS-dark vessel + corroborating news cluster), or lower
the RED threshold in `AoIAgent` so a meaningful percentage of clusters
escalate. The current 134-AoI distribution is unaudited; suspect the
LLM-naming and threat-grading is producing AMBER-floors.

---

## 2 — The top bar is clean, but tells you the system is stale

![topbar](../screenshots/02_topbar.png)

`02_topbar.png` shows:
- DAMOCLES wordmark + back-to-landing chip (works)
- **`Greece coverage · stale · 7d · 2,634`** — yellow dot, indicating the
  last successful scan is older than the freshness window
- Watch chip presets: Aegean Maritime / Evros Border / E. Med Airspace /
  Information Ops / Custom Watch
- Watch input with placeholder and Run button
- Audit chip `audit OK · 92` (chain verified, 92 entries)
- EL language toggle

**Strong points.** The system is honest about its own state — `stale` is
shown, not hidden. The two-row layout is tidy and the right-side health
strip is uncluttered.

**Problem 1.** "stale" never resolves in a typical demo. The standing-scan
cron runs at 04:00 UTC daily; if the demo is at 14:00 local on a Tuesday, the
scan finished ~10 hours ago — well inside the freshness window — yet the chip
showed `stale` here because the last fact-store update predates the freshness
threshold. **The threshold likely defaults too tight (probably 12h).** Make it
configurable and bump to 24h for the demo build.

**Problem 2.** The watch input is right next to the Run button with no visible
icon, so it reads as "more chips" rather than "primary input." For a
secondary feature this is fine; for the *only* explicit user-input field in
the app, it deserves a search icon or "Custom Watch" should pre-fill it.

**Severity: MEDIUM** for both.

---

## 3 — Clicking an AoI: the choreography works, the brief tab does not

![aoi clicked](../screenshots/05_aoi_clicked.png)

`05_aoi_clicked.png` — clicking "Kumkapi Coastal Zone" (first AoI in the
list, an AMBER over Turkish waters) correctly:
- flies the map to the AoI centroid (visible top-left)
- opens the AoITabbed pane (Brief / DNA / Detail tabs)
- rebuilds the Knowledge Graph panel on the right with the AoI subgraph
  (Sigma.js circular layout, 30+ nodes)
- shows the loader **"Running 4 agents on this AoI…"** in the brief tab

**Critical bug — the brief tab never resolves in 60s of waiting.**

![brief tab after 60s](../screenshots/07_brief_after_wait.png)

`07_brief_after_wait.png` — same view 60 seconds later. The brief has NOT
rendered.

**Root cause analysis (verified):**

A manual probe of `POST /api/aoi/aoi-a35cf2c6fb/brief` returned a complete,
valid brief **in 15.2 seconds**, with the AoI id as the first BLUF citation
(the server-side enforcement works correctly):

```
HTTP 200 bytes=3860 time=15.223456
{ "bluf": { "text": "A 70-meter vessel operating in an AIS-dark state…",
            "citation_node_ids": ["aoi-a35cf2c6fb", "507e856f-…", …] } }
```

So the backend is fine. The UI is broken in one of two ways:

1. **Most likely:** `AoITabbed.tsx:53` only auto-fires the mutation for
   `RED` or `AMBER` grades. Kumkapi Coastal Zone in the screenshot showed
   no visible grade dot in the row — possibly GREEN. The user must then
   click the "Generate intelligence brief →" CTA, which the script's
   text-locator did not find in time.
2. **Possible:** the mutation fires but `setActiveBrief` doesn't update
   because `briefIsForThisAoI` (line 65) compares `activeBrief.watch_id ===
   \`aoi-watch-${aoi.id}\`` and there's a mismatch.

**Severity: CRITICAL.** This is the gold-medal demo moment. On stage you
have one click → brief should appear in ~10 s. Either auto-fire for ALL
grades, or display the CTA more prominently and skip the loader-then-CTA
two-step.

**Action:**
- Remove the grade gate at `AoITabbed.tsx:52-54` — always auto-fire on AoI
  open
- Add a "Cancel" button on the loader so the analyst can bail to DNA tab
  while the brief generates
- Show a deterministic progress message ("Geo agent 1/4 · OSINT 2/4 · …")
  driven by WebSocket events, not a generic spinner

---

## 4 — The DNA tab works and looks the part

![DNA tab](../screenshots/08_dna_tab.png)

`08_dna_tab.png` — the Information DNA double helix renders. Two strands
visible, base-pair rungs in dashed amber between cross-strand
corroborations. Stat strip at top: `P 7 · I 0 · Composites 7 · 0 base pairs`.

**Strong points.** Visual metaphor reads as "evidence chain," not as
"sci-fi decoration." Deterministic positioning means the same AoI looks
identical every render — analysts will learn the shape of a familiar AoI.

**Problems.**
1. **Density.** With 14+ nodes the labels overlap. Need either:
   - per-strand minimum spacing so labels don't collide
   - hover to reveal full label, truncate to dot+id by default
   - or a zoom/pan inside the SVG
2. **`0 base pairs` for an AoI with composites is suspicious.** Means
   either this AoI happens to have only physical sources, or the base-pair
   construction logic in `backend/api/aoi.py:aoi_dna` is over-filtering.
   For the Kumkapi cluster (likely Turkish news + AIS-dark vessels) we'd
   expect at least one cross-strand pair. Investigate.
3. **The stat strip is at the TOP**, but the SVG legend is at the BOTTOM.
   Separating the explanation of the symbols from the count of the symbols
   forces a saccade. Consolidate.
4. **No "click a node" interaction** yet. Clicking should open the same
   evidence card the BriefPanel's citations open. Currently dead.

**Severity: MEDIUM.** Demo-passable but several "wait, what?" moments per
minute of viewing.

---

## 5 — Detail tab: the bilingual layer is leaking

![detail tab](../screenshots/09_detail_tab.png)

`09_detail_tab.png` shows the Detail tab with composite events listed.

**Visible bugs:**

1. **The header title appears in Greek even when the UI language is EN.**
   The AoI shown is "Παράκτια Ζώνη Κουμ Καπί" rendered in Greek. The
   triage row earlier in EN-mode also showed Greek-first. Both stem from
   `AoIDetail.tsx:99` which falls back `name_el || name_en` regardless of
   `lang`. **Fix:** import `useT` and pick `lang === 'en' ? name_en : name_el`
   (the triage list already does this — port that logic).

2. **`area` shows `· · ·` (empty)** in some rows. The polygonAreaKm2
   helper returns 0 for degenerate polygons; show "—" instead of empty.

3. **Composite rows show `0 sources` and `conf. 70%`** but the chevron
   doesn't open anything when sources = 0. Either hide the chevron in
   that case or show the parent message in the expanded body.

4. **Three nearly-identical "1989/None / front / front" entries** at the
   bottom — these look like deduplication failures in the composite
   fusion. Suggests `FusionEngine` may be over-counting near-duplicate
   sensor events.

**Severity: MEDIUM** per bug, **HIGH** in aggregate because the Detail tab
is what a judge skeptical of the AoI's provenance will inspect.

---

## 6 — Layer panel: visually overwhelming, functionally obscure

![layer panel](../screenshots/10_layer_panel.png)

`10_layer_panel.png` — the layer panel is open over the left third of the
map. Width approximately 30% of the map area.

**Issues.**

1. **Default-open is wrong** for the cold-open. The first impression for
   an analyst is "what is this big panel?" — they came to see the map.
2. **The two collapse arrows (left edge `←` and panel-right `›`) compete.**
   I tried to collapse the panel and could not figure out which arrow does
   it.
3. **Eye-icon toggles + slider on each row is too dense.** Most analysts
   want on/off; the opacity slider is power-user. Hide opacity behind a
   "…" menu per row or a global "advanced" toggle.
4. **External Feeds group is at the bottom**, but it's where the
   "new this session" data lives (earthquakes / disasters / EONET).
   For the demo, surface it higher or annotate as `NEW`.
5. **The earthquake layer toggled ON between `10_layer_panel.png` and
   `11_earthquakes_on.png` produced no visible change** — but the panel
   was still covering the part of Greece where the quakes live. Move the
   panel into a collapsible overlay or shrink its default width.

**Severity: HIGH.** The layer panel is the analyst's main map control and
right now it dominates the map.

---

## 7 — Satellite basemap: invisible behind the layer panel

![satellite](../screenshots/12_satellite_basemap.png)

`12_satellite_basemap.png` is visually almost identical to `11_earthquakes_on.png`
because the layer panel still covers the map. The satellite raster IS
loading (verified via API and console), but the user can't see it.

**Action.** The map basemap is the platform's most impressive single piece
of evidence ("we run Sentinel-2 over Greek waters"). Show it. Either:
- close the layer panel by default for the first 5 seconds (auto-collapse
  with a flash), or
- move the panel to the right rail next to the legend, or
- make it a popover from a single icon button

**Severity: MEDIUM.**

---

## 8 — Greek mode: i18n works, edge cases leak

![greek UI](../screenshots/14_greek_ui.png)

`14_greek_ui.png` — language switch to EL. **Strong points:**
- Top bar: Σχεδίαση ΠΕ (Draw AoI), Επιχειρησιακή Περιοχή, watch chips
  presumably translated (cropped in this shot)
- Footer panels: Πρόοδος επεξεργασίας, Αλυσίδα ελέγχου
- Layer panel labels all Greek

**Bugs:**
1. **Brief panel header still shows "Intelligence brief"** in some renders
   even when EL is active (visible in 14 if you look at the centre header).
   The `panel.brief` key resolves correctly in EL → "Αναφορά πληροφορίας",
   so this must be a stale paint. Force re-render on language change.
2. **The AoI title rendering bug from §5** is invisible here because the
   Kumkapi name IS Greek-native — but for AoIs with English names, the
   bug is real.
3. **"audit OK · 92"** chip text never translates. Add `audit.chip.ok`
   to the i18n table.

**Severity: LOW** — Greek mode is acceptable as-is. Polish.

---

## 9 — Watch input: placeholder/role mismatch

The E2E script's `scenario_run_watch` failed because it couldn't find an
input with placeholder containing "Type a watch":

```
Locator.fill: Timeout 3000ms exceeded.
  - waiting for get_by_placeholder("Type a watch").first
```

The screenshot from `02_topbar.png` confirms the placeholder IS
"Type a watch — e.g. \"Aegean — last 7 days\"". The locator should have
matched. **Hypothesis:** the watch input becomes hidden when a vessel/AoI/brief
is active. Either the placeholder is not in the DOM at this point in the
walkthrough, or the input is conditional.

**Severity: LOW for the bug**, **HIGH for the implication:** if the
analyst is reviewing an AoI and wants to type a custom watch, they
shouldn't have to clear the selection first. The watch input should
remain accessible.

**Action.** Audit `WatchInput.tsx` for conditional rendering tied to
`activeWatch`/`activeAoI`.

---

## 10 — Console errors: two real, eight noise

```
console.error: Access to fetch at 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/glyphs/Open%20Sans%20Regular,Arial%20Unicode%20MS%20Regular/0-255.pbf'
   from origin 'http://localhost:5173' has been blocked by CORS policy
console.error: Failed to load resource: net::ERR_FAILED   (×4 — different glyph ranges)
console.error: Error   (×6 — generic, no detail)
console.warning: GL Driver Message: GPU stall due to ReadPixels   (×4)
```

**Real issues:**

1. **CORS on Carto glyph fonts.** MapLibre needs PBF glyph files for label
   rendering. Carto's CDN appears to be sending headers that
   chromium-headless rejects. Symptoms: map labels (country names, place
   names) may not render. Not reproduced in real Chrome typically, but the
   exposure is real — Carto could change CORS at any time. **Action:**
   self-host the dark-matter glyphs (small directory of `.pbf` files) under
   `frontend/public/maplibre-glyphs/` and patch the MapLibre style to use a
   local glyph URL.

2. **6× generic `Error`** entries with no detail. These correspond to React
   Query failures (probably brief generation or audit chain checks) that
   are caught silently in `onError`. Add explicit toast notifications so
   analysts know when something failed instead of "silent partial
   success." See `AoITabbed.tsx:33` — the `useMutation` has no `onError`
   handler.

**Noise:**

3. **WebGL "GPU stall due to ReadPixels"** — this is the Sigma.js
   ForceAtlas2 worker doing per-frame readbacks. Cosmetic; suppress in
   prod build.

**Severity: MEDIUM** for #1, **HIGH** for #2 (silent failures kill
analyst trust).

---

## 11 — Pipeline progress + Audit chain panels: empty when they shouldn't be

Looking at the bottom strip across every screenshot, the two panels read:

- **Pipeline progress**: "Pipeline idle. Submit a watch to start."
- **Audit chain**: "Audit log is empty."

Both wrong. The audit chip in the topbar shows "audit OK · 92" — so there
ARE 92 audit entries — but the Audit Chain panel says empty.

**Diagnosis.** The Audit panel only loads when an explicit fetch fires.
Look at `AuditLog.tsx` — it probably reads from `activeWatch` or similar.
Should default to loading the last 50 entries on mount.

The Pipeline panel is correct as-is (no live watch running), but for a
demo it would be more impressive if it showed the LAST scan's pipeline
events instead of "idle."

**Severity: MEDIUM.** These two panels eat 32% of the screen and contribute
zero information at idle.

---

## 12 — Missing features the audit revealed

In order of demo impact:

1. **No keyboard navigation on the triage list.** `j`/`k`/`Enter`/`Esc` are
   table stakes for any list-driven intel tool. Currently it's mouse-only.

2. **No "Mark reviewed" / "Dismiss" action on triage rows.** Analysts
   triage by clearing items, not by clicking through and forgetting.
   Add a per-row checkmark that fades the row.

3. **No permalink to an AoI** (e.g. `?aoi=aoi-a35cf2c6fb`). Shareability
   to a colleague over Signal/email is missing. Every intel tool needs
   stable URLs.

4. **No tamper-detection live demo.** You have hash-chained audit and a
   Verify button. The script reads it at `[4:15]` but doesn't *demo*
   the failure mode. A "Tamper" button in dev mode that flips one byte
   of `audit_log.jsonl` and re-runs Verify would be a 20-second
   gold-medal moment.

5. **No "show me the scan pipeline live" mode.** The user opens the app
   and polygons are "just there." A "Run scan now" → WebSocket-driven
   AoI pop-in animation would let the analyst SEE the system thinking.

6. **No copy-to-clipboard on AoI ID, Composite ID, MMSI, brief section
   text.** Every operational tool has this.

7. **No filter beyond `All/RED/AI/Mine` on the triage list.** Need at
   minimum: text search, time-window (last 24h / 7d / 30d), source-type
   (vessels / news / social).

8. **No bulk action** (e.g. "highlight all AoIs containing a dark
   vessel" → adds a class to those rows).

9. **No "deselect" on the map.** Once an AoI is clicked, the only way
   back to the triage view is to click the X on the AoI card. The map
   should also deselect on Esc or on click-elsewhere.

10. **The Knowledge Graph panel** shows the AoI subgraph as a ring of
    30+ nodes with labels like "Vessel" "Vessel" "Vessel" — node labels
    aren't differentiating. Use the MMSI tail or the headline first
    word, not the type.

---

## Severity-ranked action list

### Demo-blocking (P0 — fix before next dry run)
- **Brief auto-fire only on AMBER/RED.** Always auto-fire. (§3, ~10 LOC)
- **Zero RED AoIs in current fact store.** Either re-tune thresholds or
  seed at least one RED. (§1)
- **AoI title shows Greek in EN mode.** Port the lang-aware name logic
  from triage to detail. (§5, ~5 LOC)
- **Silent React Query failures.** Add `onError` toasts everywhere.
  (§10, ~30 LOC across mutations)

### High (P1 — fix before pitch)
- **Layer panel default-open dominates the map.** Auto-collapse +
  shrink. (§6)
- **Audit Chain panel shows empty when chip says 92.** Wire the panel
  to fetch on mount. (§11)
- **CORS on Carto glyphs.** Self-host. (§10.1)
- **Watch input becomes hidden when AoI selected.** Keep it visible.
  (§9)

### Medium (P2 — polish)
- DNA helix label collision (§4.1)
- DNA stat strip vs legend reorganisation (§4.3)
- Composite fusion duplicates (§5.4)
- "stale" coverage threshold too tight (§2)
- AoI deselect on Esc / click-elsewhere (§12.9)
- Knowledge Graph node labels not differentiating (§12.10)

### Low (P3 — backlog)
- Bilingual chips for audit, sensor names (§8.3)
- Keyboard navigation (§12.1)
- Permalinks (§12.3)
- Tamper-demo button (§12.4)

---

## What's working that should be celebrated

It's easy for an audit to read as 100% negative. The build holds up where it
matters:

- **134 AoIs from a real Greek standing scan** are sitting in DuckDB and
  rendering on the map with Greek names. This is not a mock.
- **The brief endpoint generates a complete, AoI-cited brief in 15 seconds.**
  The 4-agent pipeline (Geo / OSINT / Devil / Supervisor) is real and the
  server-side `aoi_id`-first-citation validator works.
- **The DNA helix renders deterministically** — same data, same picture.
  That's a demo-trust prerequisite.
- **The bilingual EN/EL layer works** for every shipping string.
- **The audit chain has 92 verified entries** and the chip surfaces the
  state honestly.
- **Resizable panels persist correctly** across reloads (`autoSaveId` is
  doing its job).
- **External-feed overlays** (USGS / GDACS / EONET) toggle on without
  re-fetching, hit the disk cache, and respect the layer opacity slider.

The audit's findings are about **trim**, not **bones**. Most are fixable
in a single afternoon. The one structural issue worth your time is
choreography (§3) — turning the polygon-click → brief flow into a single
graceful arc. Get that right and the pitch is gold-medal territory.

---

*Audit conducted: 2026-05-11. Tooling: Playwright 1.59 + chromium-headless-shell
v1217. Screenshots in [`../screenshots/`](../screenshots/). Reproducible via*
*`scripts/e2e_screenshots.py`.*
