// Information DNA — bioluminescent double helix showing one AoI's evidence.
//
// Two strands wind down a vertical axis:
//   • Left strand  = physical signals (vessels, SAR detections)
//   • Right strand = information signals (news, social, telegram)
//
// Composite events sit *between* the strands — they are the "fused" cells
// where physical and information evidence cross-corroborated. A base pair
// is rendered as a faint horizontal line whenever a physical source and an
// information source share a composite parent (i.e. corroborated each other).
//
// The visual is pure SVG — no D3, no force layout. Nodes are positioned
// deterministically along the helix so the same AoI looks the same on
// every render, which matters for analyst trust ("the picture moved
// because the data moved, not because the layout shuffled").

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, AlertTriangle, Sparkles } from "lucide-react";
import { fetchAoIDNA, type AoIDNA, type DNANode } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

const HELIX_TURNS = 1.6;        // Number of full helix rotations across the height
const MARGIN_X = 32;
const MARGIN_TOP = 40;
const MARGIN_BOTTOM = 28;

// Threat-grade colour palette (matches the rest of the app)
const GRADE_FILL: Record<string, string> = {
  RED:   "#ef4444",
  AMBER: "#f59e0b",
  GREEN: "#10b981",
};

// Node-type colour palette for source events on the strands
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
}

function positionNodes(dna: AoIDNA, width: number, height: number): PositionedNode[] {
  const usableH = height - MARGIN_TOP - MARGIN_BOTTOM;
  const usableW = width - MARGIN_X * 2;
  const cx      = width / 2;
  const halfA   = usableW / 2 - 4;

  const physical    = dna.nodes.filter((n) => n.strand === "physical");
  const information = dna.nodes.filter((n) => n.strand === "information");
  const composites  = dna.nodes.filter((n) => n.type === "CompositeEvent");
  // AoI root is hidden from the helix — its name is shown in the header.

  const out: PositionedNode[] = [];

  const placeStrand = (nodes: DNANode[], side: -1 | 1) => {
    if (nodes.length === 0) return;
    nodes.forEach((n, i) => {
      const t = nodes.length === 1 ? 0.5 : i / (nodes.length - 1);
      const y = MARGIN_TOP + t * usableH;
      // Offset 0 (left) vs π (right) so the two strands wind opposite
      const phaseOffset = side === -1 ? 0 : Math.PI;
      const x = cx + side * halfA * Math.cos(t * HELIX_TURNS * 2 * Math.PI + phaseOffset);
      const grade = (n.props.threat_grade as string | undefined) ?? null;
      const fill  = grade && GRADE_FILL[grade] ? GRADE_FILL[grade] : TYPE_FILL[n.type] ?? "#94a3b8";
      out.push({ ...n, x, y, fill, radius: 5 });
    });
  };

  placeStrand(physical, -1);
  placeStrand(information, +1);

  // Composites: stack vertically along the centerline, biased toward the
  // mean Y of their member sources.
  const sourceById = new Map(out.map((n) => [n.id, n]));
  composites.forEach((c) => {
    const memberIds = (dna.edges
      .filter((e) => e.source === c.id && e.type === "COMPOSED_OF")
      .map((e) => e.target));
    const ys = memberIds.map((id) => sourceById.get(id)?.y).filter((y): y is number => typeof y === "number");
    const y = ys.length > 0 ? ys.reduce((a, b) => a + b, 0) / ys.length : (MARGIN_TOP + usableH / 2);
    const grade = (c.props.threat_grade as string | undefined) ?? "GREEN";
    out.push({
      ...c,
      x: cx,
      y,
      fill: GRADE_FILL[grade] ?? TYPE_FILL.CompositeEvent,
      radius: 7,
    });
  });

  return out;
}

export default function InformationDNA() {
  const { t } = useT();
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

  return <DNAHelix dna={data} t={t} />;
}

function DNAHelix({
  dna, t,
}: { dna: AoIDNA; t: (k: string) => string }) {
  // Default canvas dims — SVG scales to container via viewBox + preserveAspectRatio
  const W = 320;
  const H = 480;

  const positioned = useMemo(() => positionNodes(dna, W, H), [dna]);
  const nodeById = useMemo(() => new Map(positioned.map((n) => [n.id, n])), [positioned]);

  // Edges — composite -> source on the strand
  const composedEdges = dna.edges.filter((e) => e.type === "COMPOSED_OF");
  const basePairs    = dna.base_pairs;

  return (
    <div className="relative h-full w-full overflow-hidden bg-gradient-to-b from-panel-bg via-slate-950 to-panel-bg p-3">
      {/* Header */}
      <div className="absolute left-3 right-3 top-2 z-10 flex items-center gap-2 text-[10px] uppercase tracking-wider text-panel-muted">
        <Sparkles size={11} className="text-amber-300" />
        <span>{t("dna.title")}</span>
        <span className="font-mono normal-case text-panel-text">
          {dna.aoi.properties.name_el || dna.aoi.properties.name_en || dna.aoi.id.slice(0, 10)}
        </span>
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

        {/* Strand backbones — sinusoidal paths */}
        <StrandPath
          width={W} height={H} side={-1}
          gradientId="strand-physical"
        />
        <StrandPath
          width={W} height={H} side={+1}
          gradientId="strand-info"
        />

        {/* Composite -> source pull-lines (faint) */}
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

        {/* Base pairs — physical ↔ information rungs */}
        {basePairs.map((bp, i) => {
          const a = nodeById.get(bp.source);
          const b = nodeById.get(bp.target);
          if (!a || !b) return null;
          return (
            <line
              key={`bp-${i}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="#fbbf24" strokeWidth={0.9} strokeOpacity={0.65}
              strokeDasharray="2 2"
            />
          );
        })}

        {/* Nodes */}
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

function StrandPath({
  width, height, side, gradientId,
}: { width: number; height: number; side: -1 | 1; gradientId: string }) {
  const usableH = height - MARGIN_TOP - MARGIN_BOTTOM;
  const usableW = width - MARGIN_X * 2;
  const cx      = width / 2;
  const halfA   = usableW / 2 - 4;
  const phaseOffset = side === -1 ? 0 : Math.PI;
  const STEPS = 80;
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

function DNANodeMarker({ node }: { node: PositionedNode }) {
  const labelOffset = node.strand === "physical" ? -10 : (node.strand === "information" ? 10 : 12);
  const textAnchor = node.strand === "physical" ? "end" : (node.strand === "information" ? "start" : "middle");
  const textY = node.strand === "center" ? node.y - 12 : node.y;
  const labelText = (node.label || node.id.slice(0, 8)).slice(0, 22);
  return (
    <g>
      {/* outer glow */}
      <circle cx={node.x} cy={node.y} r={node.radius * 2.5} fill="url(#dna-glow)" opacity={0.35} />
      {/* core */}
      <circle
        cx={node.x} cy={node.y} r={node.radius}
        fill={node.fill}
        stroke="#0b0f17" strokeWidth={1}
      />
      <text
        x={node.x + labelOffset} y={textY}
        fontSize="8" fontFamily="monospace" fill="#cbd5e1"
        textAnchor={textAnchor} dominantBaseline="middle"
      >
        {labelText}
      </text>
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
