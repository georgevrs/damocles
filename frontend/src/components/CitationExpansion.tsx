// CitationExpansion — when a section is the active citation, render the
// resolved source nodes inline below it. This is the BriefPanel's
// instant-feedback proof that the click traversed the graph.
//
// On Day 19 we'll add an EvidenceModal that opens on a source-card click
// to show the raw SAR tile / article / Telegram message. For now, each
// card surfaces enough metadata to be analyst-readable.

import {
  Anchor, Newspaper, MessageSquare, GitBranch, X, Map as MapIcon,
  type LucideIcon,
} from "lucide-react";
import type { CitationChain, SourceNode, SourceNodeType } from "../types";
import { useDamocles } from "../store/damocles";

const ICONS: Record<SourceNodeType, LucideIcon> = {
  Vessel:         Anchor,
  NewsEvent:      Newspaper,
  SocialSignal:   MessageSquare,
  CompositeEvent: GitBranch,
};

const COLORS: Record<SourceNodeType, string> = {
  Vessel:         "border-cyan-400/30 bg-cyan-400/5 text-cyan-200",
  NewsEvent:      "border-amber-400/30 bg-amber-400/5 text-amber-200",
  SocialSignal:   "border-fuchsia-400/30 bg-fuchsia-400/5 text-fuchsia-200",
  CompositeEvent: "border-slate-400/30 bg-slate-400/5 text-slate-200",
};

function SourceCard({ src }: { src: SourceNode }) {
  const Icon = ICONS[src.node_type] ?? GitBranch;
  const tone = COLORS[src.node_type] ?? COLORS.CompositeEvent;
  const md   = src.raw_evidence.metadata ?? {};
  const props = src.properties ?? {};
  const openEvidence = useDamocles((s) => s.openEvidence);

  // Render a node-type-specific summary line + optional metadata grid.
  let title = "";
  let subtitle = "";
  if (src.node_type === "Vessel") {
    const lat = (props.lat as number | undefined)?.toFixed(3);
    const lon = (props.lon as number | undefined)?.toFixed(3);
    title = (props.vessel_name as string) || (props.mmsi as string) || "Unknown vessel";
    subtitle = `${lat ?? "?"}, ${lon ?? "?"} · AIS ${(props.ais_status as string) ?? "?"}`;
  } else if (src.node_type === "NewsEvent") {
    title = (props.headline as string) || (md.headline as string) || (props.source_url as string) || "Article";
    subtitle = `${(md.source_name as string) ?? props.source_name ?? "?"} · Goldstein ${(md.goldstein_scale as number) ?? props.goldstein_scale ?? "?"}`;
  } else if (src.node_type === "SocialSignal") {
    title = (props.text as string)?.slice(0, 110) || "Social signal";
    subtitle = `${props.channel} · ${props.language ?? "?"} · ${props.views ?? 0} views`;
  } else {
    title = (props.summary as string) || src.node_type;
    subtitle = `${props.threat_grade ?? "?"} · conf ${props.confidence ?? "?"}`;
  }

  return (
    <button
      type="button"
      onClick={() => openEvidence(src)}
      className={
        "flex w-full items-start gap-2 rounded-md border px-2 py-1.5 text-left text-xs transition-colors " +
        tone + " hover:bg-panel-text/5"
      }
      title="Open evidence"
    >
      <Icon size={13} className="mt-0.5 shrink-0 opacity-80" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider opacity-60">{src.node_type}</span>
          {src.map_highlight && (
            <span className="flex items-center gap-0.5 text-[10px] opacity-60">
              <MapIcon size={9} />
              {src.map_highlight.lat.toFixed(2)}, {src.map_highlight.lon.toFixed(2)}
            </span>
          )}
          <span className="ml-auto font-mono text-[9px] opacity-50">{src.node_id.slice(0, 8)}</span>
        </div>
        <div className="mt-0.5 truncate text-panel-text/90">{title}</div>
        <div className="text-[10px] text-panel-muted">{subtitle}</div>
        {src.raw_evidence.url && (
          <span className="mt-1 inline-block truncate text-[10px] text-amber-300/80">
            {src.raw_evidence.url.length > 70
              ? src.raw_evidence.url.slice(0, 70) + "…"
              : src.raw_evidence.url}
          </span>
        )}
      </div>
    </button>
  );
}

export default function CitationExpansion({ chain }: { chain: CitationChain }) {
  const clearCitation = useDamocles((s) => s.clearCitation);
  const cb = chain.confidence_breakdown;

  return (
    <div className="mt-2 space-y-2 rounded-md border border-amber-400/20 bg-amber-400/5 p-2">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-amber-300/80">
        <span>Citation chain</span>
        <span className="text-panel-muted normal-case">
          · {cb.source_count} source{cb.source_count === 1 ? "" : "s"}
          {cb.corroboration_count > 0 && ` · ${cb.corroboration_count} corroborating`}
        </span>
        <button
          onClick={clearCitation}
          className="ml-auto rounded p-0.5 text-panel-muted hover:bg-panel-text/10 hover:text-panel-text"
          title="dismiss"
        >
          <X size={12} />
        </button>
      </div>
      {chain.source_nodes.length === 0 && (
        <p className="text-xs text-panel-muted">No source nodes resolved.</p>
      )}
      <div className="space-y-1.5">
        {chain.source_nodes.map((sn) => (
          <SourceCard key={sn.node_id} src={sn} />
        ))}
      </div>
    </div>
  );
}
