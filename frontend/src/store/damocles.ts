// Zustand store — the one place the UI keeps cross-panel state.
//
// Cross-panel concerns:
//   - The currently-active citation. When a judge clicks a sentence in the
//     BriefPanel, the MapPanel needs to fly to the source's coordinates and
//     the GraphPanel needs to highlight the cited node. This store owns that.
//   - The current Watch + Brief selection (so the bottom strip can show
//     the right progress + audit slice).

import { create } from "zustand";
import type { AoIFeature, VesselFeature } from "../api";
import type { Brief, CitationChain, ProgressEvent, SourceNode, Watch } from "../types";

// Phase 2 layer toggles. Each entry: visible + opacity (0..1).
export type MapLayerKey =
  | "vessels" | "news" | "composites"
  | "aoi_ai" | "aoi_user"
  | "trajectories" | "news_heatmap"
  | "sar" | "flight"
  | "earthquakes" | "disasters" | "eonet"
  | "satellite_basemap";

export interface MapLayerState {
  visible: boolean;
  opacity: number;
}

export const DEFAULT_LAYERS: Record<MapLayerKey, MapLayerState> = {
  vessels:        { visible: true,  opacity: 0.85 },
  news:           { visible: true,  opacity: 0.7 },
  composites:     { visible: true,  opacity: 0.85 },
  aoi_ai:         { visible: true,  opacity: 0.5 },
  aoi_user:       { visible: true,  opacity: 0.55 },
  trajectories:   { visible: false, opacity: 0.7 },
  news_heatmap:   { visible: false, opacity: 0.6 },
  sar:            { visible: true,  opacity: 0.9 },
  flight:         { visible: false, opacity: 0.85 },
  earthquakes:    { visible: false, opacity: 0.85 },
  disasters:      { visible: false, opacity: 0.9 },
  eonet:          { visible: false, opacity: 0.85 },
  satellite_basemap: { visible: false, opacity: 1.0 },
};

interface DamoclesState {
  // The Watch currently being viewed / created
  activeWatch:    Watch | null;
  activeBrief:    Brief | null;

  // Live pipeline progress — appended as WS events arrive
  progressEvents: ProgressEvent[];
  progressDone:   boolean;

  // The "click a sentence" state — drives map fly-to + graph highlight
  activeCitation: CitationChain | null;
  activeSectionId: string | null;

  // The "click a source card" state — drives the EvidenceModal
  activeEvidence: SourceNode | null;

  // Phase 2: AoI clicked on the map — drives BriefPanel detail card,
  // GraphPanel highlight, and a focused MapPanel emphasis.
  activeAoI: AoIFeature | null;

  // Phase 2: vessel clicked on the map — drives BriefPanel vessel card
  // and a per-vessel trajectory polyline overlay.
  activeVessel: VesselFeature | null;

  // Phase 2: map layer visibility + draw mode
  mapLayers:     Record<MapLayerKey, MapLayerState>;
  drawingMode:   boolean;

  // ─── Actions ───────────────────────────────────────────────────────────
  setActiveWatch:    (w: Watch | null) => void;
  setActiveBrief:    (b: Brief | null) => void;
  appendProgress:    (e: ProgressEvent) => void;
  resetProgress:     () => void;
  markProgressDone:  () => void;
  setActiveCitation: (c: CitationChain | null, sectionId: string | null) => void;
  clearCitation:     () => void;
  openEvidence:      (s: SourceNode) => void;
  closeEvidence:     () => void;
  setLayer:          (key: MapLayerKey, patch: Partial<MapLayerState>) => void;
  setDrawingMode:    (on: boolean) => void;
  setActiveAoI:      (a: AoIFeature | null) => void;
  setActiveVessel:   (v: VesselFeature | null) => void;
}

export const useDamocles = create<DamoclesState>((set) => ({
  activeWatch:     null,
  activeBrief:     null,
  progressEvents:  [],
  progressDone:    false,
  activeCitation:  null,
  activeSectionId: null,
  activeEvidence:  null,
  activeAoI:       null,
  activeVessel:    null,
  mapLayers:       { ...DEFAULT_LAYERS },
  drawingMode:     false,

  setActiveWatch:    (w) => set({ activeWatch: w }),
  setActiveBrief:    (b) => set({ activeBrief: b }),
  appendProgress:    (e) => set((s) => ({ progressEvents: [...s.progressEvents, e] })),
  resetProgress:     () => set({ progressEvents: [], progressDone: false }),
  markProgressDone:  () => set({ progressDone: true }),
  setActiveCitation: (c, sectionId) => set({ activeCitation: c, activeSectionId: sectionId }),
  clearCitation:     () => set({ activeCitation: null, activeSectionId: null }),
  openEvidence:      (s) => set({ activeEvidence: s }),
  closeEvidence:     () => set({ activeEvidence: null }),
  setLayer:          (key, patch) => set((s) => ({
    mapLayers: { ...s.mapLayers, [key]: { ...s.mapLayers[key], ...patch } },
  })),
  setDrawingMode:    (on) => set({ drawingMode: on }),
  setActiveAoI:      (a) => set({ activeAoI: a }),
  setActiveVessel:   (v) => set({ activeVessel: v }),
}));
