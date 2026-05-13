// GraphPanel — Phase 2: Sigma.js + graphology (WebGL).
//
// Replaces Cytoscape.js. Sigma renders to a single WebGL canvas, scales to
// tens of thousands of nodes, and lets us drive citation highlights without
// the per-class style inflation Cytoscape needed.
//
// Rendering choices
// -----------------
//   * Layout: ForceAtlas2 worker for the initial layout. Subsequent updates
//     run a short FA2 pass; we don't re-layout from scratch unless node
//     count grows by >25%.
//   * Highlight: nodeReducer + edgeReducer rewrite attributes per frame.
//     When activeCitation is set, cited nodes pop (1.5x size, amber); the
//     active BriefSection gets a brighter cream halo via size 1.8x; everyone
//     else dims to dark slate with hidden labels.
//   * Reverse-click parity (BriefSection ↔ source) is preserved.

import { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import Sigma from "sigma";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import { circular } from "graphology-layout";
import type { Attributes } from "graphology-types";
import { useQuery } from "@tanstack/react-query";
import { Network, Loader2 } from "lucide-react";
import { fetchAoIExplore, fetchCitationChain, fetchWatchGraph } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";
import type { GraphNode, WatchGraph } from "../types";

const NODE_COLORS: Record<string, string> = {
  Watch:          "#e2e8f0",
  CompositeEvent: "#f59e0b",
  Vessel:         "#22d3ee",
  NewsEvent:      "#fbbf24",
  SocialSignal:   "#e879f9",
  AirspaceEvent:  "#a78bfa",
  Brief:          "#cbd5e1",
  BriefSection:   "#94a3b8",
  AreaOfInterest: "#fb923c",
};

const NODE_SIZES: Record<string, number> = {
  Watch:          8,
  CompositeEvent: 7,
  Brief:          7,
  BriefSection:   4.5,
  Vessel:         4.5,
  NewsEvent:      4,
  SocialSignal:   4,
  AirspaceEvent:  4,
  AreaOfInterest: 6,
};

const EDGE_COLOR_DEFAULT = "#1c2433";
const EDGE_COLOR_CITES   = "#f59e0b";
const HIGHLIGHT          = "#fbbf24";
const ACTIVE             = "#fde68a";
const DIM_NODE           = "#1c2433";
const DIM_EDGE           = "#0f172a";

function nodeLabel(n: GraphNode): string {
  // Differentiating labels — the E2E audit (§12.10) found nodes labelled
  // "Vessel · Vessel · Vessel" which gave the analyst no way to tell them
  // apart. Use the data: MMSI tail for vessels, headline first words for
  // news, channel for social, etc.
  const props = (n as GraphNode & { props?: Record<string, unknown> }).props ?? {};
  switch (n.type) {
    case "Watch":          return "Watch";
    case "CompositeEvent": return (n.label || "composite").slice(0, 14);
    case "Brief":          return "Brief";
    case "BriefSection":   return (n.label || "section").slice(0, 10);
    case "AreaOfInterest": return (n.label || "AoI").slice(0, 16);
    case "Vessel": {
      const mmsi = (props.mmsi as string | undefined) ?? "";
      const name = (props.vessel_name as string | undefined) ?? "";
      const ais  = (props.ais_status as string | undefined) ?? "";
      const len  = props.length_m as number | undefined;
      if (name)        return name.slice(0, 14);
      if (mmsi)        return "V " + mmsi.slice(-4);
      // SAR-only detection — no AIS broadcast → no name, no MMSI. Use
      // status + length so each node says something the analyst can read.
      if (ais && ais !== "unknown" && len) return `${ais} ${Math.round(len)}m`;
      if (ais && ais !== "unknown")        return ais;
      if (len)                              return `${Math.round(len)}m SAR`;
      return "SAR · ?";
    }
    case "NewsEvent": {
      const head = (props.headline as string | undefined) ?? n.label ?? "news";
      return head.split(/\s+/).slice(0, 3).join(" ").slice(0, 18);
    }
    case "SocialSignal": {
      const ch = (props.channel as string | undefined) ?? "";
      return ch ? "@" + ch.slice(0, 12) : (n.label || "social").slice(0, 12);
    }
    default:               return (n.label || n.type).slice(0, 14);
  }
}

// Sigma 3 validates x/y on every addNode, so we seed temporary positions
// here. circular + ForceAtlas2 will overwrite them after the live copy.
//
// We deliberately don't set `type: "circle"` — Sigma's default NodeProgram
// picks up the `color` attribute and renders correctly. Setting an
// unregistered program type silently breaks colour rendering.
function buildGraph(g: WatchGraph): Graph {
  const graph = new Graph({ multi: true, type: "directed" });
  const n = Math.max(1, g.nodes.length);
  g.nodes.forEach((node, i) => {
    const angle = (i / n) * 2 * Math.PI;
    graph.addNode(node.id, {
      label:    nodeLabel(node),
      size:     NODE_SIZES[node.type] ?? 4,
      color:    NODE_COLORS[node.type] ?? "#475569",
      nodeKind: node.type,
      x:        Math.cos(angle),
      y:        Math.sin(angle),
    });
  });
  for (const e of g.edges) {
    if (!graph.hasNode(e.source) || !graph.hasNode(e.target)) continue;
    graph.addEdge(e.source, e.target, {
      type:    "arrow",
      size:    1,
      color:   e.type === "CITES" ? EDGE_COLOR_CITES : EDGE_COLOR_DEFAULT,
      relType: e.type,
    });
  }
  return graph;
}

export default function GraphPanel({ className }: { className?: string }) {
  const { t } = useT();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef     = useRef<Sigma | null>(null);
  const graphRef     = useRef<Graph | null>(null);
  const fa2Ref       = useRef<FA2Layout | null>(null);

  const [hover, setHover] = useState<{ id: string; type: string; label: string } | null>(null);

  const activeWatch     = useDamocles((s) => s.activeWatch);
  const activeCitation  = useDamocles((s) => s.activeCitation);
  const activeSectionId = useDamocles((s) => s.activeSectionId);
  const activeAoI       = useDamocles((s) => s.activeAoI);
  const setActiveCitation = useDamocles((s) => s.setActiveCitation);

  const { data: watchGraph } = useQuery({
    queryKey: ["graph", activeWatch?.id],
    queryFn: () => activeWatch ? fetchWatchGraph(activeWatch.id, 800) : Promise.resolve(null),
    enabled: !!activeWatch && !activeAoI,
    refetchInterval: 8000,
  });

  // When an AoI is selected, swap to its subgraph (AoI + member composites + sources).
  // Falls back to the watch graph when no AoI is selected.
  const { data: aoiExplore } = useQuery({
    queryKey: ["aoi-explore", activeAoI?.id],
    queryFn: () => activeAoI ? fetchAoIExplore(activeAoI.id) : Promise.resolve(null),
    enabled: !!activeAoI,
    staleTime: 60_000,
  });

  const graph = activeAoI ? (aoiExplore?.graph ?? null) : watchGraph;

  // Build a stable graphology instance.
  const graphology = useMemo(() => (graph ? buildGraph(graph as WatchGraph) : null), [graph]);

  // ─── Mount Sigma once ──────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || sigmaRef.current) return;
    // Empty graph until data lands; Sigma needs a graph at construction.
    const empty = new Graph({ multi: true, type: "directed" });
    graphRef.current = empty;
    // Sigma 3 picks up the `color` attribute from each node automatically.
    // We set `defaultNodeColor` only as a fallback for nodes missing the
    // attribute — should not happen given buildGraph always sets it.
    const sigma = new Sigma(empty, containerRef.current, {
      labelColor: { color: "#cbd5e1" },
      labelSize: 11,
      labelFont: "ui-monospace, SFMono-Regular, Menlo, monospace",
      labelDensity: 0.7,
      labelGridCellSize: 60,
      labelRenderedSizeThreshold: 4,
      defaultNodeColor: "#475569",
      defaultEdgeColor: EDGE_COLOR_DEFAULT,
      enableEdgeEvents: false,
      minCameraRatio: 0.05,
      maxCameraRatio: 6,
      renderEdgeLabels: false,
    });

    sigma.on("enterNode", ({ node }) => {
      const g = graphRef.current;
      if (!g) return;
      const a = g.getNodeAttributes(node);
      setHover({ id: node, type: a.nodeKind, label: a.label });
    });
    sigma.on("leaveNode", () => setHover(null));

    sigma.on("clickNode", async ({ node }) => {
      const g = graphRef.current;
      if (!g) return;
      const kind = g.getNodeAttributes(node).nodeKind as string;
      const brief = useDamocles.getState().activeBrief;
      if (!brief) return;
      try {
        if (kind === "BriefSection") {
          const chain = await fetchCitationChain(brief.id, node);
          setActiveCitation(chain, node);
          return;
        }
        const citing = brief.sections.find((s) => s.citation_node_ids.includes(node));
        if (!citing) return;
        const chain = await fetchCitationChain(brief.id, citing.id);
        setActiveCitation(chain, citing.id);
      } catch (e) {
        console.error("citation chain (sigma click)", e);
      }
    });

    sigmaRef.current = sigma;
    return () => {
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
  }, [setActiveCitation]);

  // ─── When data lands or changes, swap graph + start the FA2 worker ──────
  // The worker iterates ForceAtlas2 in the background and Sigma re-renders
  // each tick, producing the visible "settling" animation. Stops after
  // ~3.5s so we don't pin a CPU core.
  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma || !graphology) return;

    // Stop any previous worker before swapping data.
    if (fa2Ref.current) {
      fa2Ref.current.stop();
      fa2Ref.current.kill();
      fa2Ref.current = null;
    }

    const live = graphRef.current;
    if (!live) return;

    live.clear();
    graphology.forEachNode((id, attrs) => live.addNode(id, { ...attrs }));
    graphology.forEachEdge((id, attrs, source, target) => {
      try { live.addEdgeWithKey(id, source, target, { ...attrs }); }
      catch { live.addEdge(source, target, { ...attrs }); }
    });

    // Circular seed so FA2 doesn't start from a degenerate state.
    circular.assign(live);

    // Animated layout — runs off the main thread, Sigma redraws on each tick.
    const settings = forceAtlas2.inferSettings(live);
    const layout = new FA2Layout(live, { settings });
    layout.start();
    fa2Ref.current = layout;

    // Auto-stop the worker after a few seconds so the layout settles.
    const stopTimer = window.setTimeout(() => {
      layout.stop();
    }, 3500);

    sigma.refresh();
    return () => {
      window.clearTimeout(stopTimer);
      layout.stop();
      try { layout.kill(); } catch { /* already killed */ }
      if (fa2Ref.current === layout) fa2Ref.current = null;
    };
  }, [graphology]);

  // ─── Citation / AoI highlight: redirect via reducers ────────────────────
  // An AoI selection promotes its citation_event_ids (the composites that
  // were clustered) to the same "highlighted" set as a brief citation.
  useEffect(() => {
    const sigma = sigmaRef.current;
    if (!sigma) return;

    const cited = new Set<string>(
      (activeCitation?.source_nodes ?? []).map((s) => s.node_id),
    );
    if (activeAoI?.properties?.citation_event_ids) {
      for (const id of activeAoI.properties.citation_event_ids) cited.add(id);
    }
    const sectionId = activeSectionId;
    const anyHighlight = cited.size > 0 || !!sectionId;

    sigma.setSetting("nodeReducer", (node: string, data: Attributes) => {
      const out = { ...data };
      if (!anyHighlight) return out;
      if (node === sectionId) {
        out.color = ACTIVE;
        out.size = (data.size ?? 4) * 1.8;
        out.zIndex = 3;
        return out;
      }
      if (cited.has(node)) {
        out.color = HIGHLIGHT;
        out.size = (data.size ?? 4) * 1.5;
        out.zIndex = 2;
        return out;
      }
      out.color = DIM_NODE;
      out.label = "";
      out.zIndex = 0;
      return out;
    });

    sigma.setSetting("edgeReducer", (edge: string, data: Attributes) => {
      if (!anyHighlight) return data;
      const g = graphRef.current;
      if (!g) return data;
      const [src, tgt] = g.extremities(edge);
      const onPath =
        (src === sectionId && cited.has(tgt)) ||
        (cited.has(src) && cited.has(tgt));
      if (onPath && data.relType === "CITES") {
        return { ...data, color: HIGHLIGHT, size: (data.size ?? 1) * 2 };
      }
      return { ...data, color: DIM_EDGE, hidden: false };
    });

    sigma.refresh();
  }, [activeCitation, activeSectionId, activeAoI]);

  const stats = graph
    ? `${graph.nodes.length} nodes · ${graph.edges.length} edges`
    : "—";

  const reLayout = () => {
    const live = graphRef.current;
    if (!live) return;
    if (fa2Ref.current) {
      fa2Ref.current.stop();
      fa2Ref.current.kill();
      fa2Ref.current = null;
    }
    circular.assign(live);
    const settings = forceAtlas2.inferSettings(live);
    const layout = new FA2Layout(live, { settings });
    layout.start();
    fa2Ref.current = layout;
    window.setTimeout(() => layout.stop(), 3500);
    sigmaRef.current?.refresh();
  };

  return (
    <div className={"flex flex-col overflow-hidden bg-panel-bg " + (className ?? "")}>
      <div className="flex items-center gap-2 border-b border-panel-border px-3 py-2 text-xs text-panel-muted">
        <Network size={14} />
        <span>{t("panel.graph")}</span>
        <span className="ml-auto font-mono text-[10px]">{stats}</span>
        <button
          onClick={reLayout}
          className="rounded border border-panel-border px-1.5 py-0.5 text-[10px] hover:border-panel-text/40"
          title={t("panel.graph.relayout")}
        >
          {t("panel.graph.relayout")}
        </button>
      </div>

      <div className="relative flex-1">
        {!activeWatch && !activeAoI && (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-panel-muted">
            {t("panel.graph.empty")}
          </div>
        )}
        {((activeWatch && !watchGraph) || (activeAoI && !aoiExplore)) && (
          <div className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-panel-muted">
            <Loader2 size={14} className="animate-spin" /> {t("panel.graph.loading")}
          </div>
        )}

        <div ref={containerRef} className="absolute inset-0" />

        {hover && (
          <div className="pointer-events-none absolute left-2 bottom-2 z-10 rounded-md border border-panel-border bg-panel-bg/95 px-2 py-1 text-[10px] text-panel-text backdrop-blur-sm">
            <div className="text-panel-muted">{hover.type}</div>
            <div className="font-mono">{hover.label}</div>
            <div className="font-mono text-panel-muted">{hover.id.slice(0, 12)}…</div>
          </div>
        )}

        <div className="pointer-events-none absolute right-2 bottom-2 z-10 space-y-0.5 rounded-md bg-panel-bg/85 px-2 py-1 text-[10px] backdrop-blur-sm">
          <Legend color="#f59e0b" label={t("graph.legend.composite")} />
          <Legend color="#22d3ee" label={t("graph.legend.vessel")} />
          <Legend color="#fbbf24" label={t("graph.legend.news")} />
          <Legend color="#e879f9" label={t("graph.legend.social")} />
          <Legend color="#fb923c" label={t("graph.legend.aoi")} />
          <Legend color="#cbd5e1" label={t("graph.legend.brief")} />
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-panel-muted">
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      <span>{label}</span>
    </div>
  );
}
