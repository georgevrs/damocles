// Axios client + typed wrappers around the Damocles REST endpoints.
// The Vite dev server proxies /api and /ws to the FastAPI backend
// (see vite.config.ts). In production both are served from the same origin.

import axios from "axios";
import type {
  AuditPayload,
  Brief,
  BriefSummary,
  CitationChain,
  HealthPayload,
  VerifyVerdict,
  Watch,
  WatchGraph,
  WatchTemplate,
} from "./types";

const http = axios.create({ baseURL: "/", timeout: 30_000 });

// ─── Watches ─────────────────────────────────────────────────────────────────
export async function fetchWatchTemplates(): Promise<WatchTemplate[]> {
  return (await http.get<WatchTemplate[]>("/api/watches/templates")).data;
}

export async function createWatch(query: string): Promise<Watch> {
  return (await http.post<Watch>("/api/watches", { query })).data;
}

export async function getWatch(id: string) {
  return (await http.get(`/api/watches/${id}`)).data as {
    watch: Watch;
    is_done: boolean;
    last_event: Record<string, unknown> | null;
    event_count: number;
  };
}

// ─── Briefs ──────────────────────────────────────────────────────────────────
export async function listBriefsForWatch(watchId: string): Promise<BriefSummary[]> {
  return (await http.get<BriefSummary[]>("/api/briefs", { params: { watch_id: watchId } })).data;
}

export async function fetchBrief(id: string): Promise<Brief> {
  return (await http.get<Brief>(`/api/briefs/${id}`)).data;
}

export async function fetchCitationChain(briefId: string, sectionId: string): Promise<CitationChain> {
  return (await http.get<CitationChain>(`/api/briefs/${briefId}/citation/${sectionId}`)).data;
}

// ─── Graph (Cytoscape feed) ──────────────────────────────────────────────────
export async function fetchWatchGraph(watchId: string, limit = 800): Promise<WatchGraph> {
  return (await http.get<WatchGraph>(`/api/graph/${watchId}`, { params: { limit } })).data;
}

// ─── Audit ───────────────────────────────────────────────────────────────────
export async function fetchAuditPage(hoursBack = 24, limit = 100): Promise<AuditPayload> {
  return (await http.get<AuditPayload>("/api/audit", {
    params: { hours_back: hoursBack, limit },
  })).data;
}

export async function verifyAuditChain(): Promise<VerifyVerdict> {
  return (await http.get<VerifyVerdict>("/api/audit/verify")).data;
}

// W3-T1 demo-only tamper / restore. Backend gates on settings.DEMO_MODE,
// so hitting these in production deploys returns 404.
export interface TamperVerdict {
  tampered:        boolean;
  tampered_index:  number;
  entry_id:        string;
  original_chain:  string;
  tampered_chain:  string;
  verified:        boolean;
  first_bad_index: number | null;
  chain_total:     number;
  verdict:         string;
}
export async function tamperAuditChain(): Promise<TamperVerdict> {
  return (await http.post<TamperVerdict>("/api/audit/_tamper")).data;
}

export interface RestoreVerdict {
  restored:        boolean;
  verified:        boolean;
  first_bad_index: number | null;
  chain_total:     number;
  verdict:         string;
}
export async function restoreAuditChain(): Promise<RestoreVerdict> {
  return (await http.post<RestoreVerdict>("/api/audit/_restore")).data;
}

// ─── System (W3-T2 LLM provider swap) ────────────────────────────────────────
export interface LlmSwapResult {
  swapped:  boolean;
  previous: "gemini" | "ollama";
  current:  "gemini" | "ollama";
  model:    string;
  alive:    boolean;
}
export async function switchLlmProvider(provider: "gemini" | "ollama"): Promise<LlmSwapResult> {
  return (await http.post<LlmSwapResult>("/api/system/llm/switch", { provider })).data;
}

// ─── Health ──────────────────────────────────────────────────────────────────
export async function fetchHealth(): Promise<HealthPayload> {
  return (await http.get<HealthPayload>("/health")).data;
}

// ─── Phase 2: store + standing scan + AoI ────────────────────────────────────
export interface StoreStats {
  [table: string]: { count: number; latest: string | null };
}
export async function fetchStoreStats(): Promise<StoreStats> {
  return (await http.get<StoreStats>("/api/store/stats")).data;
}

export interface ScanRun {
  scan_id: string;
  kind: string;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  sensor_counts: string | null;
}
export interface StandingStatus {
  scheduler_active: boolean;
  cron: string;
  inflight_scan_id: string | null;
  history: ScanRun[];
  freshest_ok: ScanRun | null;
}
export async function fetchStandingStatus(): Promise<StandingStatus> {
  return (await http.get<StandingStatus>("/api/standing/status")).data;
}
export async function triggerStandingScan(): Promise<{ scan_id: string; status: string }> {
  return (await http.post("/api/standing/scan")).data;
}

// AoI: GeoJSON FeatureCollection consumed by the map AoI layer.
export interface AoIFeatureProperties {
  id: string;
  source: "ai" | "user";
  name_el: string;
  name_en: string | null;
  description: string | null;
  centroid_lat: number | null;
  centroid_lon: number | null;
  threat_grade: string | null;
  threat_summary: string | null;
  citation_event_ids: string[];
  scan_id: string | null;
  created_at: string | null;
  updated_at: string | null;
}
export interface AoIFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  properties: AoIFeatureProperties;
}
export interface AoIFeatureCollection {
  type: "FeatureCollection";
  features: AoIFeature[];
}

export async function fetchAoI(source: "ai" | "user" | "all" = "all"): Promise<AoIFeatureCollection> {
  return (await http.get<AoIFeatureCollection>("/api/aoi", { params: { source } })).data;
}

export async function createAoI(body: {
  name_el: string;
  name_en?: string;
  description?: string;
  geometry_geojson: GeoJSON.Polygon | GeoJSON.MultiPolygon;
}): Promise<AoIFeature> {
  return (await http.post<AoIFeature>("/api/aoi", body)).data;
}

export async function deleteAoI(aoiId: string): Promise<void> {
  await http.delete(`/api/aoi/${aoiId}`);
}

// ─── AoI explore (drill-down for Brief + Graph panels) ──────────────
export interface AoICompositeRow {
  id: string;
  threat_grade: "GREEN" | "AMBER" | "RED";
  confidence: number | null;
  summary: string;
  centroid_lat: number | null;
  centroid_lon: number | null;
  time_window_start: string | null;
  time_window_end: string | null;
  source_node_ids: string[];
  created_at: string | null;
  scan_id: string | null;
}

export interface AoISourceRow {
  id: string;
  type: "Vessel" | "NewsEvent" | "SocialSignal";
  label: string;
  lat: number | null;
  lon: number | null;
  props: Record<string, unknown>;
}

export interface AoIExplore {
  aoi: AoIFeature;
  composites: AoICompositeRow[];
  sources: AoISourceRow[];
  graph: {
    nodes: { id: string; type: string; label: string; lat: number | null; lon: number | null; props: Record<string, unknown> }[];
    edges: { source: string; target: string; type: string }[];
  };
}

export async function fetchAoIExplore(aoiId: string): Promise<AoIExplore> {
  return (await http.get<AoIExplore>(`/api/aoi/${aoiId}/explore`)).data;
}

// ─── AoI DNA (subgraph for Information DNA visualization) ────────
export interface DNANode {
  id:     string;
  type:   string;
  label:  string;
  lat:    number | null;
  lon:    number | null;
  props:  Record<string, unknown>;
  strand: "physical" | "information" | "center";
}
export interface DNAEdge {
  source: string;
  target: string;
  type:   string;
}
export interface DNABasePair {
  source: string;
  target: string;
  via:    string;
  type:   "BASE_PAIR";
}
export interface AoIDNA {
  aoi:        AoIFeature;
  nodes:      DNANode[];
  edges:      DNAEdge[];
  base_pairs: DNABasePair[];
  stats: {
    physical_count:    number;
    information_count: number;
    composite_count:   number;
    base_pair_count:   number;
  };
}
export async function fetchAoIDNA(aoiId: string): Promise<AoIDNA> {
  return (await http.get<AoIDNA>(`/api/aoi/${aoiId}/dna`)).data;
}

// ─── AoI-scoped brief (4-agent pipeline + aoi:// citation in BLUF) ────
export async function generateAoIBrief(aoiId: string): Promise<Brief> {
  return (await http.post<Brief>(`/api/aoi/${aoiId}/brief`)).data;
}

// ─── Standing-scan vessels (always-on map layer) ─────────────────────
export interface VesselFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Point;
  properties: {
    node_id: string;
    node_type: "Vessel";
    label: string;
    mmsi: string | null;
    ts: string | null;
    vessel_name: string | null;
    flag: string | null;
    length_m: number | null;
    ais_status: string | null;
    confidence: number | null;
    dark_vessel_score: number | null;
  };
}
export async function fetchVesselTrajectory(eventId: string, hours = 24 * 14): Promise<GeoJSON.FeatureCollection> {
  return (await http.get(`/api/map/vessel/${encodeURIComponent(eventId)}/trajectory`, {
    params: { hours },
  })).data;
}

export async function fetchVessels(opts: {
  bbox?: [number, number, number, number];
  hours?: number;
  limit?: number;
  minConfidence?: number;
} = {}): Promise<{ type: "FeatureCollection"; features: VesselFeature[] }> {
  const params: Record<string, string | number> = {};
  if (opts.bbox)                        params.bbox = opts.bbox.join(",");
  if (opts.hours)                       params.hours = opts.hours;
  if (opts.limit)                       params.limit = opts.limit;
  if (opts.minConfidence !== undefined) params.min_confidence = opts.minConfidence;
  return (await http.get("/api/map/vessels", { params })).data;
}

export interface VesselTrajectoryPoint {
  lon:        number;
  lat:        number;
  ts:         string;
  speed_kn:   number | null;
  course_deg: number | null;
}

export interface VesselDetailData {
  event_id:              string;
  mmsi:                  string | null;
  ts:                    string | null;
  lat:                   number;
  lon:                   number;
  vessel_name:           string | null;
  flag:                  string | null;
  length_m:              number | null;
  ais_status:            string | null;
  speed_kn:              number | null;
  course_deg:            number | null;
  heading_deg:           number | null;
  sar_tile_id:           string | null;
  confidence:            number | null;
  dark_vessel_score:     number | null;
  ais_match_distance_km: number | null;
  trajectory_points:     VesselTrajectoryPoint[];
  n_trajectory_points:   number;
}

export async function fetchVesselDetail(eventId: string, trajectoryLimit = 20): Promise<VesselDetailData> {
  return (await http.get<VesselDetailData>(
    `/api/map/vessels/${encodeURIComponent(eventId)}`,
    { params: { trajectory_limit: trajectoryLimit } },
  )).data;
}

// ─── OpenSky flights (live, no cache) ────────────────────────────────
export interface FlightFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Point;
  properties: {
    icao24: string;
    callsign: string | null;
    origin_country: string;
    altitude_m: number | null;
    on_ground: boolean;
    velocity_ms: number | null;
    heading: number | null;
    vertical_rate: number | null;
    ts: number | null;
  };
}
export async function fetchFlights(opts: {
  bbox?: [number, number, number, number];
} = {}): Promise<{ type: "FeatureCollection"; features: FlightFeature[] }> {
  const params: Record<string, string | number> = {};
  if (opts.bbox) params.bbox = opts.bbox.join(",");
  return (await http.get("/api/map/flights", { params })).data;
}

// ─── Link-preview (og:image + og:title) ──────────────────────────────
export interface LinkPreview {
  url: string;
  title: string | null;
  image: string | null;
  description: string | null;
  source: string;
  ok: boolean;
  reason?: string;
}
export async function fetchPreview(url: string): Promise<LinkPreview> {
  return (await http.get<LinkPreview>("/api/preview", { params: { url } })).data;
}

export interface TrajectoryFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.LineString;
  properties: {
    mmsi: string;
    n_points: number;
    first_ts: string | null;
    last_ts: string | null;
  };
}
export async function fetchTrajectories(opts: {
  bbox?: [number, number, number, number];
  hours?: number;
  minPoints?: number;
  maxVessels?: number;
} = {}): Promise<{ type: "FeatureCollection"; features: TrajectoryFeature[] }> {
  const params: Record<string, string | number> = {};
  if (opts.bbox)        params.bbox = opts.bbox.join(",");
  if (opts.hours)       params.hours = opts.hours;
  if (opts.minPoints)   params.min_points = opts.minPoints;
  if (opts.maxVessels)  params.max_vessels = opts.maxVessels;
  return (await http.get("/api/map/trajectories", { params })).data;
}

// ─── External event overlays — earthquakes / disasters / EONET ───────
export interface ExternalEventFeature {
  type: "Feature";
  id: string;
  geometry: GeoJSON.Point;
  properties: {
    kind: "earthquake" | "disaster" | "eonet";
    threat_grade: "RED" | "AMBER" | "GREEN";
    label: string;
    source_url?: string | null;
    ts?: string | null;
    magnitude?: number | null;
    depth_km?: number | null;
    place?: string | null;
    alert_level?: string | null;
    event_type?: string | null;
    category?: string | null;
    title?: string | null;
    felt?: number | null;
    tsunami?: boolean | null;
  };
}
export interface ExternalEventCollection {
  type: "FeatureCollection";
  features: ExternalEventFeature[];
  meta?: Record<string, unknown>;
}

export async function fetchEarthquakes(days = 7, minMag = 3.5): Promise<ExternalEventCollection> {
  return (await http.get<ExternalEventCollection>("/api/external/earthquakes", {
    params: { days, min_mag: minMag },
  })).data;
}

export async function fetchDisasters(): Promise<ExternalEventCollection> {
  return (await http.get<ExternalEventCollection>("/api/external/disasters")).data;
}

export async function fetchEonet(days = 14, status: "open"|"closed"|"all" = "open"): Promise<ExternalEventCollection> {
  return (await http.get<ExternalEventCollection>("/api/external/eonet", {
    params: { days, status },
  })).data;
}

export async function fetchNewsHeatmap(opts: {
  bbox?: [number, number, number, number];
  hours?: number;
  h3Resolution?: number;
} = {}): Promise<GeoJSON.FeatureCollection> {
  const params: Record<string, string | number> = {};
  if (opts.bbox)         params.bbox = opts.bbox.join(",");
  if (opts.hours)        params.hours = opts.hours;
  if (opts.h3Resolution) params.h3_resolution = opts.h3Resolution;
  return (await http.get("/api/map/news_heatmap", { params })).data;
}

// ─── WebSocket helper ────────────────────────────────────────────────────────
// Returns a setup that the caller can subscribe to via callbacks. Keeps the
// React component code free of WebSocket lifecycle details.
export function openWatchProgressSocket(
  watchId: string,
  onEvent: (e: Record<string, unknown>) => void,
  onClose?: () => void,
): WebSocket {
  // In dev Vite proxies the /ws path; in prod nginx does the same. The host
  // changes between dev and prod, so we resolve at runtime.
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/watches/${watchId}`);
  ws.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); }
    catch { /* dropped malformed frame */ }
  };
  ws.onclose = () => onClose?.();
  return ws;
}
