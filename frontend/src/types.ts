// TypeScript types mirroring the backend Pydantic models.
// Kept hand-written rather than generated from openapi.json so the file
// reads cleanly and we can comment domain-specific fields.

export type ThreatGrade = "GREEN" | "AMBER" | "RED";
export type AISStatus  = "broadcasting" | "dark" | "unknown";
export type Urgency    = "ROUTINE" | "PRIORITY" | "IMMEDIATE";
export type SectionType =
  | "BLUF" | "KEY_JUDGMENT" | "SUPPORTING" | "DEVILS_ADVOCATE" | "RECOMMENDATION";

// ─── Watch ───────────────────────────────────────────────────────────────────
export interface WatchTemplate {
  id: string;
  label: string;
  query: string;
  icon: string;        // lucide-react icon name; we map to component at render time
}

export interface WatchSpec {
  region: string;
  custom_bbox: [number, number, number, number] | null;
  domain: "maritime" | "border" | "airspace" | "information" | "multi";
  time_window_days: number;
  keywords: string[];
  threat_indicators: string[];
  confidence: number;
  parse_notes: string | null;
}

export interface Watch {
  id: string;
  raw_query: string;
  spec: WatchSpec;
  created_at: string;
  status: "pending" | "processing" | "complete" | "error";
  brief_id: string | null;
}

// ─── Pipeline progress ───────────────────────────────────────────────────────
export interface ProgressEvent {
  stage: string;
  status: "started" | "progress" | "complete" | "failed" | "skipped";
  detail: string;
  progress_pct: number;
}

// ─── Brief ───────────────────────────────────────────────────────────────────
export interface BriefSection {
  id: string;
  section_type: SectionType;
  text: string;
  citation_node_ids: string[];
  confidence: number;
  agent_source: string;
  extra: Record<string, unknown>;
}

export interface BriefSummary {
  id: string;
  watch_id: string;
  created_at: string;
  metadata: {
    agents_consulted?: string[];
    processing_duration_seconds?: number;
    sources_count?: number;
    [k: string]: unknown;
  };
}

export interface Brief extends BriefSummary {
  sections: BriefSection[];
}

// ─── Citation chain (the gold-medal endpoint) ────────────────────────────────
export type SourceNodeType = "Vessel" | "NewsEvent" | "SocialSignal" | "CompositeEvent";

export interface SourceNode {
  node_id: string;
  node_type: SourceNodeType;
  cites_via: string | null;
  properties: Record<string, unknown>;
  raw_evidence: {
    type: "SAR_TILE" | "ARTICLE_URL" | "TELEGRAM_MESSAGE" | "COMPOSITE";
    url?: string;
    tile_id?: string;
    content?: string;
    metadata?: Record<string, unknown>;
  };
  map_highlight: { lat: number; lon: number; radius_km: number } | null;
  graph_highlight: { node_id: string };
}

export interface CitationChain {
  section: BriefSection;
  source_nodes: SourceNode[];
  corroboration_chain: SourceNode[];
  confidence_breakdown: {
    section_confidence: number;
    source_count: number;
    corroboration_count: number;
  };
}

// ─── Graph endpoint (Cytoscape feed) ─────────────────────────────────────────
export interface GraphNode {
  id: string;
  type: string;
  label: string;
  lat: number | null;
  lon: number | null;
  props: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface WatchGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ─── Audit ───────────────────────────────────────────────────────────────────
export interface AuditEntry {
  id: string;
  timestamp: string;
  action_type: string;
  actor: string;
  payload_hash: string;
  previous_hash: string;
  chain_hash: string;
  chain_valid: boolean;
}

export interface AuditPayload {
  entries: AuditEntry[];
  count: number;
  hours_back: number;
  verified: boolean;
  chain_total: number;
  first_bad_index: number | null;
  note: string | null;
}

export interface VerifyVerdict {
  verified: boolean;
  chain_total: number;
  first_bad_index: number | null;
  verdict: string;
}

// ─── Health ──────────────────────────────────────────────────────────────────
export interface HealthPayload {
  status: "ok" | "degraded";
  env: "development" | "production";
  demo_mode: boolean;
  neo4j: { ok: boolean; uri: string };
  llm:   { ok: boolean; provider: string; model: string };
}
