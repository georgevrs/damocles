// Information DNA — bioluminescent double helix showing one AoI's evidence,
// encoded across three dimensions:
//
//   • Y-axis (top → bottom)  = time (earliest member at top, latest at bottom)
//   • Node size              = confidence (composites) / parent confidence (sources)
//   • Rung thickness         = corroboration strength (members of shared composite)
//
// Strands:
//   • Left strand  = physical signals (vessels, SAR detections)
//   • Right strand = information signals (news, social, telegram)
//   • Centerline   = composite events ("fused" cells)
//
// When every member event shares the same timestamp (a common pattern with
// batched SAR fetches — see docs/AOI_QUALITY_REPORT.md §5), the temporal
// axis collapses and we fall back to deterministic per-node hash jitter so
// the helix still reads as a helix, not a vertical pile.
//
// Pure SVG. No D3. Positions are deterministic — same AoI looks identical
// on every render, which matters for analyst trust.

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, AlertTriangle, Clock, Sparkles } from "lucide-react";
import { fetchAoIDNA, type AoIDNA, type DNANode } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

const HELIX_TURNS = 1.8;
const MARGIN_X = 36;
const MARGIN_TOP = 52;
const MARGIN_BOTTOM = 32;

const GRADE_FILL: Record<string, string> = {
  RED:   "#ef4444",
  AMBER: "#f59e0b",
  GREEN: "#10b981",
};

const TYPE_FILL: Record<string, string> = {
  Vessel:         "#22d3ee",
  NewsEvent:      "#f59e0b",
  SocialSignal:   "#d946ef",
  CompositeEvent: "#10b981",
  AreaOfInterest: "#fbbf24",
};

interface PositionedNode extends DNANode {
  x: number;
  y: number;
  fill: string;
  radius: number;
  ts: number | null;          // unix ms, or null
}

// ─────────────────────── time-domain helpers ───────────────────────

function nodeTimestamp(n: DNANode): number | null {
  const props = n.props ?? {};
  const ts = (props.ts as string | undefined) ?? null;
  if (!ts) return null;
  const ms = new Date(ts).getTime();
  return Number.isFinite(ms) ? ms : null;
}

// Deterministic [0,1) hash from a string id. Used when timestamps collapse.
function hash01(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 100000) / 100000;
}

function fmtTime(ms: number): string {
  const d = new Date(ms);
  return d.toLocaleString(undefined, {
    year: "2-digit", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtSpan(spanMs: number): string {
  if (spanMs < 60_000)              return "<1m";
  if (spanMs < 3_600_000)           return `${Math.round(spanMs / 60_000)}m`;
  if (spanMs < 86_400_000)          return `${(spanMs / 3_600_000).toFixed(1)}h`;
  return `${(spanMs / 86_400_000).toFixed(1)}d`;
}

// ─────────────────────── positioning ───────────────────────

interface Positioned {
  nodes:      PositionedNode[];
  timeRange:  { min: number; max: number; span: number; collapsed: boolean } | null;
}

function positionNodes(dna: AoIDNA, width: number, height: number): Positioned {
  const usableH = height - MARGIN_TOP - MARGIN_BOTTOM;
  const usableW = width  - MARGIN_X * 2;
  const cx      = width / 2;
  const halfA   = usableW / 2 - 6;

  const physical    = dna.nodes.filter((n) => n.strand === "physical");
  const information = dna.nodes.filter((n) => n.strand === "information");
  const composites  = dna.nodes.filter((n) => n.type === "CompositeEvent");

  // 1. Determine the temporal domain across source nodes.
  const tsArray = [...physical, ...information]
    .map(nodeTimestamp)
    .filter((t): t is number => t !== null);
  let timeRange: Positioned["timeRange"] = null;
  if (tsArray.length >= 2) {
    const min = Math.min(...tsArray);
    const max = Math.max(...tsArray);
    const span = max - min;
    timeRange = { min, max, span, collapsed: span < 60_000 };
  } else if (tsArray.length === 1) {
    timeRange = { min: tsArray[0], max: tsArray[0], span: 0, collapsed: true };
  }

  // 2. Map each node to a normalised t ∈ [0,1]
  //    Real time when we have a usable span; deterministic hash otherwise.
  const tNorm = (n: DNANode): number => {
    if (timeRange && !timeRange.collapsed) {
      const ts = nodeTimestamp(n);
      if (ts !== null) return (ts - timeRange.min) / timeRange.span;
    }
    return hash01(n.id);
  };

  // 3. Source-node confidence — sources don't carry their own confidence,
  //    so look it up via the parent composite (the COMPOSED_OF edge target).
  const compositeConfidenceById: Record<string, number> = {};
  composites.forEach((c) => {
    const conf = c.props?.confidence as number | undefined;
    compositeConfidenceById[c.id] = typeof conf === "number" ? conf : 0.5;
  });
  const sourceConfidence = (sourceId: string): number => {
    // Find a composite whose member set includes this source
    const parentEdge = dna.edges.find(
      (e) => e.type === "COMPOSED_OF" && e.target === sourceId,
    );
    if (parentEdge) return compositeConfidenceById[parentEdge.source] ?? 0.5;
    return 0.5;
  };

  // 4. Place strand nodes
  const out: PositionedNode[] = [];
  const placeStrand = (nodes: DNANode[], side: -1 | 1) => {
    if (nodes.length === 0) return;
    const phase = side === -1 ? 0 : Math.PI;
    nodes.forEach((n) => {
      const t = tNorm(n);
      const y = MARGIN_TOP + t * usableH;
      const x = cx + side * halfA * Math.cos(t * HELIX_TURNS * 2 * Math.PI + phase);
      const grade = (n.props?.threat_grade as string | undefined) ?? null;
      const fill  = grade && GRADE_FILL[grade] ? GRADE_FILL[grade] : TYPE_FILL[n.type] ?? "#94a3b8";
      const conf  = sourceConfidence(n.id);
      // 3.0 px at confidence 0, 6.5 px at confidence 1
      const radius = 3.0 + conf * 3.5;
      out.push({ ...n, x, y, fill, radius, ts: nodeTimestamp(n) });
    });
  };
  placeStrand(physical, -1);
  placeStrand(information, +1);

  // 5. Place composites on the centerline at the mean-Y of their members
  const ySources = new Map(out.map((n) => [n.id, n.y]));
  composites.forEach((c) => {
    const memberIds = dna.edges
      .filter((e) => e.source === c.id && e.type === "COMPOSED_OF")
      .map((e) => e.target);
    const ys = memberIds.map((id) => ySources.get(id)).filter((y): y is number => typeof y === "number");
    const y = ys.length > 0
      ? ys.reduce((a, b) => a + b, 0) / ys.length
      : (MARGIN_TOP + usableH / 2);
    const grade = (c.props?.threat_grade as string | undefined) ?? "GREEN";
    const conf  = (c.props?.confidence as number | undefined) ?? 0.5;
    const radius = 4.5 + conf * 4.5;     // composites are visually heavier (4.5–9 px)
    out.push({
      ...c,
      x: cx,
      y,
      fill:   GRADE_FILL[grade] ?? TYPE_FILL.CompositeEvent,
      radius,
      ts:    null,
    });
  });

  return { nodes: out, timeRange };
}

// ─────────────────────── top-level component ───────────────────────

export default function InformationDNA() {
  const { t, lang } = useT();
  const activeAoI = useDamocles((s) => s.activeAoI);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["aoi-dna", activeAoI?.id],
    queryFn:  () => fetchAoIDNA(activeAoI?.id ?? ""),
    enabled:  !!activeAoI?.id,
    staleTime: 60_000,
  });

  if (!activeAoI) return <DNAEmptyState />;
  if (isLoading)   return <DNALoading />;
  if (isError || !data) return <DNAErrorState />;
  return <DNAHelix dna={data} t={t} lang={lang} />;
}

function DNAHelix({
  dna, t, lang,
}: { dna: AoIDNA; t: (k: string) => string; lang: "en" | "el" }) {
  const W = 320;
  const H = 480;

  const { nodes: positioned, timeRange } = useMemo(
    () => positionNodes(dna, W, H), [dna],
  );
  const nodeById = useMemo(
    () => new Map(positioned.map((n) => [n.id, n])),
    [positioned],
  );

  const composedEdges = dna.edges.filter((e) => e.type === "COMPOSED_OF");
  const basePairs    = dna.base_pairs;

  // Per-composite member count — used to thicken its base-pair rungs to
  // reflect corroboration strength.
  const memberCountByComposite: Record<string, number> = useMemo(() => {
    const m: Record<string, number> = {};
    for (const e of composedEdges) {
      m[e.source] = (m[e.source] ?? 0) + 1;
    }
    return m;
  }, [composedEdges]);

  const aoiName =
    (lang === "en"
        ? dna.aoi.properties.name_en || dna.aoi.properties.name_el
        : dna.aoi.properties.name_el || dna.aoi.properties.name_en)
    || dna.aoi.id.slice(0, 10);

  return (
    <div className="relative h-full w-full overflow-hidden bg-gradient-to-b from-panel-bg via-slate-950 to-panel-bg p-3">
      {/* Header */}
      <div className="absolute left-3 right-3 top-2 z-10 flex items-center gap-2 text-[10px] uppercase tracking-wider text-panel-muted">
        <Sparkles size={11} className="text-amber-300" />
        <span>{t("dna.title")}</span>
        <span className="font-mono normal-case text-panel-text">{aoiName}</span>
      </div>

      {/* Stat strip */}
      <div className="absolute left-3 right-3 top-7 z-10 flex items-center gap-2 font-mono text-[9px] text-panel-muted">
        <span>P {dna.stats.physical_count}</span>
        <span>·</span>
        <span>I {dna.stats.information_count}</span>
        <span>·</span>
        <span>{t("dna.composites")} {dna.stats.composite_count}</span>
        <span>·</span>
        <span className="text-amber-300">{dna.stats.base_pair_count} {t("dna.base_pairs")}</span>
        {timeRange && !timeRange.collapsed && (
          <>
            <span className="ml-auto flex items-center gap-1 text-cyan-300">
              <Clock size={9} />
              <span>{fmtSpan(timeRange.span)}</span>
            </span>
          </>
        )}
        {timeRange && timeRange.collapsed && (
          <span className="ml-auto text-amber-300/70" title={t("dna.time_collapsed_hint")}>
            <Clock size={9} className="inline" /> {t("dna.time_collapsed")}
          </span>
        )}
      </div>

      {/* Canvas */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        className="absolute inset-0 h-full w-full"
      >
        <defs>
          <radialGradient id="dna-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="white" stopOpacity="0.7" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="strand-physical" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#22d3ee" stopOpacity="0.55" />
            <stop offset="1" stopColor="#22d3ee" stopOpacity="0.15" />
          </linearGradient>
          <linearGradient id="strand-info" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f59e0b" stopOpacity="0.55" />
            <stop offset="1" stopColor="#f59e0b" stopOpacity="0.15" />
          </linearGradient>
        </defs>

        <StrandPath width={W} height={H} side={-1} gradientId="strand-physical" />
        <StrandPath width={W} height={H} side={+1} gradientId="strand-info" />

        {/* Time-axis tick marks on the left edge */}
        {timeRange && !timeRange.collapsed && (
          <TimeAxis height={H} timeRange={timeRange} />
        )}

        {/* COMPOSED_OF pull-lines (faint) */}
        {composedEdges.map((e, i) => {
          const a = nodeById.get(e.source);
          const b = nodeById.get(e.target);
          if (!a || !b) return null;
          return (
            <line
              key={`co-${i}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="#475569" strokeWidth={0.6} strokeOpacity={0.45}
            />
          );
        })}

        {/* Base-pair rungs — thickness encodes corroboration strength */}
        {basePairs.map((bp, i) => {
          const a = nodeById.get(bp.source);
          const b = nodeById.get(bp.target);
          if (!a || !b) return null;
          const strength = memberCountByComposite[bp.via] ?? 2;
          // 0.8 px at 2 sources, 2.4 px at 8+
          const width = Math.min(2.4, 0.8 + 0.2 * Math.max(0, strength - 2));
          return (
            <line
              key={`bp-${i}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="#fbbf24" strokeWidth={width} strokeOpacity={0.7}
              strokeDasharray="2 2"
            >
              <title>via {bp.via} · {strength} sources</title>
            </line>
          );
        })}

        {positioned.map((n) => (
          <DNANodeMarker key={n.id} node={n} />
        ))}
      </svg>

      {/* Legend */}
      <div className="pointer-events-none absolute bottom-2 left-3 right-3 z-10 flex flex-wrap items-center gap-2 font-mono text-[9px] text-panel-muted">
        <Legend dot="#22d3ee" label={t("dna.legend.physical")} />
        <Legend dot="#f59e0b" label={t("dna.legend.information")} />
        <Legend dot="#10b981" label={t("dna.legend.composite")} />
        <span className="ml-auto flex items-center gap-1">
          <svg width="16" height="4" viewBox="0 0 16 4" aria-hidden>
            <line x1="0" y1="2" x2="16" y2="2" stroke="#fbbf24" strokeWidth="1" strokeDasharray="2 2" />
          </svg>
          <span>{t("dna.legend.base_pair")}</span>
        </span>
      </div>
    </div>
  );
}

// ─────────────────────── sub-components ───────────────────────

function StrandPath({
  width, height, side, gradientId,
}: { width: number; height: number; side: -1 | 1; gradientId: string }) {
  const usableH = height - MARGIN_TOP - MARGIN_BOTTOM;
  const usableW = width  - MARGIN_X * 2;
  const cx      = width / 2;
  const halfA   = usableW / 2 - 6;
  const phaseOffset = side === -1 ? 0 : Math.PI;
  const STEPS = 96;
  const pts: string[] = [];
  for (let i = 0; i <= STEPS; i++) {
    const t = i / STEPS;
    const y = MARGIN_TOP + t * usableH;
    const x = cx + side * halfA * Math.cos(t * HELIX_TURNS * 2 * Math.PI + phaseOffset);
    pts.push(`${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`);
  }
  return (
    <path
      d={pts.join(" ")}
      fill="none"
      stroke={`url(#${gradientId})`}
      strokeWidth={1.5}
      strokeLinecap="round"
    />
  );
}

function TimeAxis({
  height, timeRange,
}: {
  height: number;
  timeRange: { min: number; max: number; span: number; collapsed: boolean };
}) {
  const usableH = height - MARGIN_TOP - MARGIN_BOTTOM;
  // Five tick marks — top, three internal quarters, bottom
  const ticks = 5;
  return (
    <g>
      {Array.from({ length: ticks }, (_, i) => {
        const t = i / (ticks - 1);
        const y = MARGIN_TOP + t * usableH;
        const tsMs = timeRange.min + t * timeRange.span;
        return (
          <g key={i}>
            <line
              x1={6} y1={y} x2={10} y2={y}
              stroke="#475569" strokeWidth={0.6}
            />
            {(i === 0 || i === ticks - 1) && (
              <text
                x={12} y={y + 2}
                fontSize="7" fontFamily="monospace" fill="#64748b"
              >
                {fmtTime(tsMs)}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}

function DNANodeMarker({ node }: { node: PositionedNode }) {
  const labelOffset = node.strand === "physical" ? -10 : (node.strand === "information" ? 10 : 12);
  const textAnchor  = node.strand === "physical" ? "end" : (node.strand === "information" ? "start" : "middle");
  const textY       = node.strand === "center" ? node.y - 12 : node.y;
  const labelText   = (node.label || node.id.slice(0, 8)).slice(0, 22);
  // Centerline (composite) labels dim by default to avoid the stack-of-text
  // overlay; revealed on hover.
  const labelOpacity = node.strand === "center" ? 0 : 0.85;

  // Tooltip — shows label, type, and (if available) timestamp
  const tooltipParts = [node.label || node.id, node.type];
  if (node.ts) tooltipParts.push(fmtTime(node.ts));

  return (
    <g className="group">
      <circle cx={node.x} cy={node.y} r={node.radius * 2.5} fill="url(#dna-glow)" opacity={0.35} />
      <circle
        cx={node.x} cy={node.y} r={node.radius}
        fill={node.fill}
        stroke="#0b0f17" strokeWidth={1}
      />
      <text
        x={node.x + labelOffset} y={textY}
        fontSize="8" fontFamily="monospace" fill="#cbd5e1"
        textAnchor={textAnchor} dominantBaseline="middle"
        opacity={labelOpacity}
        style={{ transition: "opacity 120ms" }}
        className="group-hover:!opacity-100"
      >
        {labelText}
      </text>
      <title>{tooltipParts.join(" · ")}</title>
    </g>
  );
}

function Legend({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: dot }} />
      <span>{label}</span>
    </span>
  );
}

function DNAEmptyState() {
  const { t } = useT();
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-[11px] text-panel-muted">
      <Sparkles size={20} className="text-amber-300/60" />
      <div className="font-mono uppercase tracking-wider text-panel-muted/80">
        {t("dna.title")}
      </div>
      <div className="max-w-xs leading-relaxed">{t("dna.empty")}</div>
    </div>
  );
}

function DNALoading() {
  const { t } = useT();
  return (
    <div className="flex h-full items-center justify-center gap-2 text-[11px] text-panel-muted">
      <Loader2 size={13} className="animate-spin" />
      <span>{t("dna.loading")}</span>
    </div>
  );
}

function DNAErrorState() {
  const { t } = useT();
  return (
    <div className="flex h-full items-center justify-center gap-2 text-[11px] text-rose-200">
      <AlertTriangle size={13} />
      <span>{t("dna.error")}</span>
    </div>
  );
}
