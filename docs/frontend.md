# Frontend

React + TypeScript + Vite + Zustand + MapLibre GL + Cytoscape. Three-panel analyst UI with the gold-medal citation-click flow.

## Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ DAMOCLES · LLM badge · audit verdict ·  [chips]  [free-text]  [Run]   │  WatchInput
├────────────────────────┬───────────────────────────┬───────────────────┤
│                        │                           │                   │
│       MapPanel         │       BriefPanel          │     GraphPanel    │
│       (30%)            │       (40%)               │     (30%)         │
│                        │                           │                   │
│    MapLibre GL +       │  Section cards w/         │  Cytoscape        │
│    CARTO Dark Matter   │  CitableText + inline     │  force-directed   │
│    + sensor markers    │  CitationExpansion        │  graph w/ feature-│
│                        │                           │  state highlight  │
├────────────────────────┴───────────────────────────┴───────────────────┤
│      ProgressStream            │              AuditLog                 │  Bottom strip
│      (live WS events)          │              (entries + Verify)       │
└────────────────────────────────────────────────────────────────────────┘
        EvidenceModal renders on top when activeEvidence is set
```

[`frontend/src/App.tsx`](../frontend/src/App.tsx) is the layout shell — all state lives in the Zustand store; each panel subscribes to what it needs.

## State management — the Zustand store

[`frontend/src/store/damocles.ts`](../frontend/src/store/damocles.ts)

The single place cross-panel state lives:

```typescript
interface DamoclesState {
  activeWatch:    Watch | null;
  activeBrief:    Brief | null;

  progressEvents: ProgressEvent[];
  progressDone:   boolean;

  // The "click a sentence" handle — drives map flyTo + graph highlight
  activeCitation:  CitationChain | null;
  activeSectionId: string | null;

  // The "click a source card" handle — drives EvidenceModal
  activeEvidence:  SourceNode | null;

  // ... actions: setActiveWatch, setActiveBrief, appendProgress,
  //              setActiveCitation, openEvidence, closeEvidence, ...
}
```

This is the *only* store. No Redux, no Context, no prop drilling beyond a couple of layers.

**Why Zustand?** The cross-panel coupling is real — clicking a brief sentence has to reach the map, the graph, AND the citation expansion. Lifting that into App-level useState would force re-renders on every panel; React Context with selective subscriptions adds boilerplate. Zustand gives selective subscriptions for free via `useDamocles((s) => s.activeCitation)`.

## The cross-panel sync — how the gold-medal click works

```
                    User clicks BLUF in BriefPanel
                                ↓
            CitableText.onClick → fetchCitationChain(briefId, sectionId)
                                ↓
                  setActiveCitation(chain, sectionId)
                                ↓
        ┌───────────────────────┼───────────────────────┐
        ↓                       ↓                       ↓
    MapPanel               GraphPanel             BriefPanel
    (subscribes)          (subscribes)           (subscribes)
        ↓                       ↓                       ↓
   map.flyTo({               cy.batch(() => {       <CitationExpansion
     center: source           // dim all,             chain={...} /> drops
     coords,                  // highlight             below the active
     duration: 800            // cited nodes,          section. Cards
   })                          // animate camera       become clickable.
                              // fit
                            })
        ↓
  Active vessel              Cited nodes get          User clicks a card
  marker shows               amber border ring;        ↓
  amber pulse ring           others fade to 18%        openEvidence(src)
                                                       ↓
                                                  EvidenceModal
                                                  opens with
                                                  raw_evidence
```

Every panel reads `activeCitation` (or `activeSectionId`) from the store and re-renders only when those slices change. This is why selective subscription matters — `useDamocles((s) => s.progressEvents)` doesn't re-render the map.

## Components

### `WatchInput` — the top bar
[`frontend/src/components/WatchInput.tsx`](../frontend/src/components/WatchInput.tsx)

- 4 quick-launch chips fed by `GET /api/watches/templates` (cached `staleTime: Infinity`)
- Free-text input, submit on Enter or button-click
- `SystemBadges` sub-component: LLM model badge + audit verdict badge, polled every 15-30s
- On submit: `createWatch` → `setActiveWatch` → `setActiveBrief(null)` → `resetProgress()`

The audit badge is the demo's permanent counter-tampering signal. Three states:
- `audit OK · 41` (green) — chain rehashes correctly
- `audit empty` (amber) — pre-first-run
- `TAMPER @ 4` (red, with bright background) — verify failed at index 4

Defensive optional chaining throughout (`health?.llm?.ok`, `verdict?.verified === true`) — the `data` field of React Query is `undefined` until first fetch, and HMR transitions can leave it transiently partial. Documented in [limitations.md §6.16](limitations.md).

### `MapPanel` — the map
[`frontend/src/components/MapPanel.tsx`](../frontend/src/components/MapPanel.tsx)

MapLibre GL with the CARTO Dark Matter vector style. Plots three sensor-derived layers fed by `GET /api/graph/{watch_id}` (deduped by TanStack Query with `GraphPanel`).

Layers (bottom → top):
1. **Aegean AOI** — amber dashed polygon overlay
2. **Composite events** — diamond icons (SVG data-URLs, baked at module-load), green/amber/red by threat grade, sized by corroboration_count
3. **News events** — circles, colored by Goldstein scale (red conflictual → emerald cooperative), sized by mentions
4. **Vessels** — circles, **cyan if broadcasting / red if AIS-dark**, sized by length_m
5. **Vessel pulse ring** — only visible for the cited vessel via `feature-state`

`feature-state` drives the active/dimmed visual — clicking a brief section calls `map.setFeatureState({source: "vessels", id: ...}, {active: true, dimmed: false})`. Paint-property expressions read those states and adjust opacity. **Filters can't read feature-state** (caught us during Day 20 — see [limitations.md §6.15](limitations.md)).

The `flyTo` hook lives in a `useEffect` that depends on `activeCitation`:
```typescript
useEffect(() => {
  const sn = activeCitation?.source_nodes.find((n) => n.map_highlight);
  if (sn?.map_highlight) {
    map.flyTo({
      center:    [sn.map_highlight.lon, sn.map_highlight.lat],
      zoom:      9.5,
      duration:  800,
      essential: true,
    });
  }
}, [activeCitation, fcs]);
```

Why MapLibre GL not commercial Mapbox? Same UX, BSD-3, no API token, no US-vendor lock-in. Today's tile style is hosted by CARTO — for full sovereignty we'd swap to self-hosted Protomaps (`.pmtiles`), same MapLibre style format. See [architecture.md §"Sovereignty above convenience"](architecture.md).

### `BriefPanel` — the brief
[`frontend/src/components/BriefPanel.tsx`](../frontend/src/components/BriefPanel.tsx)

- Polls `GET /api/briefs?watch_id=<id>` every 3s until a brief lands
- Renders sections sorted: BLUF → Key Judgments → Supporting → Devil → Recommendation
- Color-coded section borders: amber (BLUF), neutral (KJ/Supporting), rose (Devil), emerald (Recommendation)
- Devil section shows a `devil X%` chip; Recommendation shows urgency chip (ROUTINE/PRIORITY/IMMEDIATE)
- During pipeline run: shimmer skeleton matching the eventual layout (not just a spinner)

Each section's text is wrapped in `CitableText`.

### `CitableText` — the click handler
[`frontend/src/components/CitableText.tsx`](../frontend/src/components/CitableText.tsx)

Text with confidence-tinted dotted underline:
- `≥ 0.80` — emerald (`decoration-emerald-400/70`)
- `0.60-0.80` — amber
- `< 0.60` — rose

On click:
1. `fetchCitationChain(briefId, sectionId)` (axios)
2. `setActiveCitation(chain, sectionId)`
3. Loading spinner inline next to the text
4. Active section gets a pinned amber ring (`ring-1 ring-amber-400/40 bg-amber-400/5`)

Hover surfaces the confidence percentage + citation count via the `title` attribute.

### `CitationExpansion` — the inline chain
[`frontend/src/components/CitationExpansion.tsx`](../frontend/src/components/CitationExpansion.tsx)

Renders below the active section. One source card per cited node:
- Anchor icon (cyan) for Vessel
- Newspaper icon (amber) for NewsEvent
- MessageSquare icon (fuchsia) for SocialSignal
- GitBranch icon (slate) for CompositeEvent

Each card surfaces enough metadata to be analyst-readable inline (vessel name + AIS status + length, headline + Goldstein, message preview + channel, threat grade + confidence). Click a card → `openEvidence(src)` → EvidenceModal opens.

### `EvidenceModal` — the raw artefact
[`frontend/src/components/EvidenceModal.tsx`](../frontend/src/components/EvidenceModal.tsx)

Full-screen overlay with backdrop click + Escape-key dismiss. Per-node-type renderers:

- **Vessel** — fetches the cached SAR PNG from `/static/sar/<tile_id>.png` (with detection bounding box drawn on it from the geospatial sensor). Plus AIS status, MMSI, length, dark-vessel score, CFAR confidence.
- **NewsEvent** — headline, "Open original article" button (new tab; we don't iframe because most outlets `X-Frame-Options: deny`), Goldstein bar (red→emerald gradient), CAMEO code, mention count.
- **SocialSignal** — message text in a fuchsia-bordered card, channel, language, views/forwards, matched_place.
- **CompositeEvent** — threat-grade chip, summary, corroboration count, centroid.

Closes via Escape, X button, or backdrop click. Focus-trap a11y is documented as DEBT in [limitations.md §6.10](limitations.md).

### `GraphPanel` — Cytoscape
[`frontend/src/components/GraphPanel.tsx`](../frontend/src/components/GraphPanel.tsx)

Cytoscape `cose` (Compound Spring Embedder) force-directed layout. Per-type styling:

| Type | Shape | Color |
| --- | --- | --- |
| Watch | round-rectangle | white |
| CompositeEvent | diamond | amber |
| Vessel | ellipse | cyan |
| NewsEvent | ellipse | yellow |
| SocialSignal | ellipse | fuchsia |
| Brief | round-triangle | gray |
| BriefSection | round-rectangle | gray (smaller) |

Edges by type: `CITES` is amber (the gold-medal edge); `COMPOSED_OF` is dashed; others are gray solid; `CONTAINS` is dotted.

Bidirectional sync:
- **activeCitation → graph**: dims all, highlights cited nodes (amber border), brightens active section, animates `cy.fit({eles, padding: 60}, {duration: 600})` to bring the highlighted set into view.
- **Graph node click → brief**: handler reads the latest `activeBrief` via `useDamocles.getState()` (no extra re-renders), finds the `BriefSection` that cites the clicked node, fires its citation chain. Clicking a `BriefSection` node directly triggers its own citation chain.

Hover popover surfaces `node_id (truncated) · type · label`.

The store-via-getState pattern matters: subscribing `activeBrief` would re-render the whole Cytoscape canvas every time the brief updates (~3s during pipeline run). Reading via `getState()` inside the click handler reads the freshest value at click time without subscribing.

### `ProgressStream` — bottom-left
[`frontend/src/components/ProgressStream.tsx`](../frontend/src/components/ProgressStream.tsx)

Opens a WebSocket on `activeWatch` change. Each frame from `WS /ws/watches/{id}` is appended to the store; the panel renders them as a monospace event log with status colors (green=complete, red=failed, amber=skipped).

WebSocket lifecycle:
```typescript
useEffect(() => {
  if (!activeWatch) return;
  const ws = openWatchProgressSocket(activeWatch.id, (e) => {
    appendProgress(e as ProgressEvent);
    if (e.stage === "complete") markProgressDone();
  });
  return () => ws.close();
}, [activeWatch]);
```

The store's progress events are reset by `WatchInput` on every new watch, so the stream is per-watch.

### `AuditLog` — bottom-right
[`frontend/src/components/AuditLog.tsx`](../frontend/src/components/AuditLog.tsx)

- Polls `GET /api/audit?hours_back=24&limit=50` every 5s
- Shows `timestamp · action_type · actor · chain_hash[:12]` per row
- "Verify chain" button calls `GET /api/audit/verify` and shows the verdict (green or red) in a banner above the entry list

The persistent badge in the top-bar's `SystemBadges` already shows the verdict — this panel is for the deeper drill-down.

## API client

[`frontend/src/api.ts`](../frontend/src/api.ts)

Typed axios wrappers around every REST endpoint:

```typescript
fetchWatchTemplates(): Promise<WatchTemplate[]>
createWatch(query: string): Promise<Watch>
getWatch(id: string): Promise<{ watch: Watch; is_done: boolean; ... }>
listBriefsForWatch(watchId: string): Promise<BriefSummary[]>
fetchBrief(id: string): Promise<Brief>
fetchCitationChain(briefId: string, sectionId: string): Promise<CitationChain>
fetchWatchGraph(watchId: string, limit?: number): Promise<WatchGraph>
fetchAuditPage(hoursBack?: number, limit?: number): Promise<AuditPayload>
verifyAuditChain(): Promise<VerifyVerdict>
fetchHealth(): Promise<HealthPayload>
```

Plus `openWatchProgressSocket(watchId, onEvent, onClose)` for the WS lifecycle.

The Vite dev server proxies `/api`, `/static`, and `/ws` to `http://localhost:8000` — see [`frontend/vite.config.ts`](../frontend/vite.config.ts). In production both serve from the same origin so the proxy is a no-op.

## Type system

[`frontend/src/types.ts`](../frontend/src/types.ts) — hand-mirrored from the backend Pydantic shapes. See [data-model.md](data-model.md). Update both files in the same commit when shapes change; the e2e test catches drift.

## Styling

Tailwind 3.4 with a custom dark theme. Tokens in [`frontend/tailwind.config.ts`](../frontend/tailwind.config.ts):

- `bg-panel-bg` (outer background, `#0b0f17`)
- `bg-panel-surface` (panel surface, `#101522`)
- `border-panel-border` (`#1c2433`)
- `text-panel-text` / `text-panel-muted`
- Threat palette: `bg-threat-{green,amber,red,unknown}`

Custom CSS lives in [`frontend/src/index.css`](../frontend/src/index.css):
- MapLibre control color overrides (dark-themed buttons, attribution)
- Subtle scrollbar
- `.skeleton` shimmer animation (1.6s ease-in-out)
- `ping-ring` keyframe for vessel pulse rings (defined for future use)

## Performance characteristics

- **First paint**: ~400 ms after Vite serves the bundle
- **Time to interactive**: ~600 ms (after MapLibre's WebGL context initializes + style.json fetch)
- **Brief click → flyTo + graph highlight**: ~30 ms (network) + 800 ms (animation)
- **Bundle size**: ~240 KB gzipped (app code) + ~218 KB gzipped (MapLibre) + ~80 KB gzipped (Cytoscape) = ~540 KB total over the wire

The MapLibre chunk dominates. Code-splitting via dynamic import on first map interaction would shave ~218 KB off initial load — documented as future polish but acceptable for the demo.

## Build + dev

```bash
# install once
npm --prefix frontend install

# dev (Vite hot reload, hits localhost:8000 backend via proxy)
npm --prefix frontend run dev
# → http://localhost:5173 (NOT 127.0.0.1, see limitations §6.5)

# typecheck + production build
npm --prefix frontend run build
# → frontend/dist/, ready for nginx
```

Vite binds `localhost` (IPv6 ::1) only on Windows. `127.0.0.1` returns connection-refused — hit `localhost:5173` instead. Documented in [limitations.md §6.5](limitations.md).

## Limitations to note

The full ledger lives in [limitations.md §6](limitations.md). Highlights:
- **Section-level click**, not sentence-level (matches our backend data model)
- **No focus trap** in modal (a11y debt)
- **Reverse-sync from graph picks the first citing section** if multiple cite the same node
- **No Vitest tests yet** — the citation click handler is the gold-medal moment and a 3-test minimum should land before demo dry-runs

## How to add a panel

1. Drop a new component file in `frontend/src/components/`.
2. Subscribe to whatever store slice you need: `const x = useDamocles((s) => s.x)`.
3. Mount it in `App.tsx` — choose a layout slot (replace one of the bottom-strip halves, add a fourth panel via `flex-1`, or render as a modal layer alongside `<EvidenceModal />`).
4. If the panel needs to fetch data: use `useQuery` with a key that includes `activeWatch?.id` so it refetches on watch change.
5. If the panel needs to react to citation clicks: subscribe to `activeCitation` and add a `useEffect` that fires your visualization update.

That's it — Zustand handles the wiring; the existing panels show the patterns.
