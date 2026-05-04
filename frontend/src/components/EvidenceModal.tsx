// EvidenceModal — the demo's [2:00] payoff.
//
// Opens when a source card in CitationExpansion is clicked. Renders the
// raw artifact behind the cited claim:
//   - Vessel       : SAR tile preview PNG (fetched from /static/sar/<tile_id>.png)
//                    + AIS status, MMSI, length, dark-vessel score
//   - NewsEvent    : article URL + headline + Goldstein scale + mention count
//                    + open-in-new-tab link (we don't iframe; many outlets
//                    set X-Frame-Options: deny)
//   - SocialSignal : raw message text + channel + lang + views/forwards
//   - CompositeEvent: summary + threat grade + corroboration count
//
// Close behaviour: Escape key, X button, or click on the backdrop.

import { useEffect } from "react";
import {
  Anchor, Newspaper, MessageSquare, GitBranch, X, ExternalLink,
  type LucideIcon,
} from "lucide-react";
import { useDamocles } from "../store/damocles";
import type { SourceNode, SourceNodeType } from "../types";

const ICONS: Record<SourceNodeType, LucideIcon> = {
  Vessel:         Anchor,
  NewsEvent:      Newspaper,
  SocialSignal:   MessageSquare,
  CompositeEvent: GitBranch,
};

const ACCENTS: Record<SourceNodeType, string> = {
  Vessel:         "text-cyan-300 border-cyan-400/40",
  NewsEvent:      "text-amber-300 border-amber-400/40",
  SocialSignal:   "text-fuchsia-300 border-fuchsia-400/40",
  CompositeEvent: "text-slate-300 border-slate-400/40",
};


export default function EvidenceModal() {
  const evidence     = useDamocles((s) => s.activeEvidence);
  const closeEvidence = useDamocles((s) => s.closeEvidence);

  // Close on Escape
  useEffect(() => {
    if (!evidence) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") closeEvidence(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [evidence, closeEvidence]);

  if (!evidence) return null;

  const Icon = ICONS[evidence.node_type] ?? GitBranch;
  const accent = ACCENTS[evidence.node_type] ?? ACCENTS.CompositeEvent;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={closeEvidence}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={"flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border bg-panel-bg shadow-2xl " + accent}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center gap-3 border-b border-panel-border px-4 py-3">
          <Icon size={18} />
          <div className="min-w-0 flex-1">
            <div className="text-[10px] uppercase tracking-wider text-panel-muted">
              Evidence · {evidence.node_type}
            </div>
            <div className="font-mono text-[11px] text-panel-muted truncate">
              {evidence.node_id}
            </div>
          </div>
          <button
            onClick={closeEvidence}
            className="rounded p-1 text-panel-muted hover:bg-panel-border hover:text-panel-text"
            title="close (Esc)"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4">
          {evidence.node_type === "Vessel"         && <VesselEvidence src={evidence} />}
          {evidence.node_type === "NewsEvent"      && <NewsEvidence   src={evidence} />}
          {evidence.node_type === "SocialSignal"   && <SocialEvidence src={evidence} />}
          {evidence.node_type === "CompositeEvent" && <CompositeEvidence src={evidence} />}
        </div>
      </div>
    </div>
  );
}

// ─── Per-node-type renderers ────────────────────────────────────────────────
function MetaGrid({ rows }: { rows: Array<[string, React.ReactNode]> }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-panel-muted">{k}</dt>
          <dd className="font-mono text-panel-text">{v ?? <span className="text-panel-muted">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

function VesselEvidence({ src }: { src: SourceNode }) {
  const p = src.properties as Record<string, unknown>;
  const tileId = (p.sar_tile_id as string | undefined) ?? (src.raw_evidence.tile_id as string | undefined);
  const sarUrl = tileId ? `/static/sar/${tileId}.png` : null;
  const lat = p.lat as number | undefined;
  const lon = p.lon as number | undefined;
  const ais = p.ais_status as string | undefined;
  const dark = p.dark_vessel_score as number | undefined;
  const isDark = ais === "dark";

  return (
    <div className="space-y-3">
      {sarUrl && (
        <div className="overflow-hidden rounded-md border border-panel-border bg-black">
          <img
            src={sarUrl}
            alt="SAR tile preview with detection bounding box"
            className="block max-h-[60vh] w-full object-contain"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
          />
        </div>
      )}
      {!sarUrl && (
        <div className="rounded-md border border-dashed border-panel-border p-3 text-xs text-panel-muted">
          No SAR tile cached for this vessel. (AIS-only detection or pre-cache run.)
        </div>
      )}
      <MetaGrid rows={[
        ["lat / lon",      lat !== undefined && lon !== undefined ? `${lat.toFixed(4)}, ${lon.toFixed(4)}` : null],
        ["MMSI",           (p.mmsi as string)        ?? null],
        ["Vessel name",    (p.vessel_name as string) ?? null],
        ["Flag",           (p.flag as string)        ?? null],
        ["Length (m)",     p.length_m !== undefined && p.length_m !== null ? `${(p.length_m as number).toFixed(0)}` : null],
        ["AIS status",     ais ? (
            <span className={isDark ? "rounded bg-rose-500/20 px-1.5 text-rose-200" : "rounded bg-emerald-500/20 px-1.5 text-emerald-200"}>
              {ais}
            </span>
          ) : null],
        ["Dark-vessel score", dark !== undefined && dark !== null ? `${(dark * 100).toFixed(0)}%` : null],
        ["CFAR confidence",   p.confidence !== undefined && p.confidence !== null ? `${((p.confidence as number) * 100).toFixed(0)}%` : null],
        ["Detected at",       (p.timestamp as string) ?? null],
      ]} />
    </div>
  );
}

function NewsEvidence({ src }: { src: SourceNode }) {
  const p = src.properties as Record<string, unknown>;
  const url = (p.source_url as string) || (src.raw_evidence.url as string | undefined);
  const headline = (p.headline as string) || "(no headline)";
  const goldstein = p.goldstein_scale as number | undefined;
  const mentions = p.mentions as number | undefined;
  const cameo = p.cameo_code as string | undefined;

  // Goldstein bar: -10 (most conflictual) → +10 (most cooperative)
  const gPct = goldstein !== undefined ? Math.max(0, Math.min(100, ((goldstein + 10) / 20) * 100)) : null;

  return (
    <div className="space-y-3">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-panel-muted">Headline</div>
        <h3 className="mt-1 text-base text-panel-text">{headline}</h3>
      </div>

      {url && (
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded border border-amber-400/40 bg-amber-400/10 px-3 py-1.5 text-xs text-amber-200 hover:bg-amber-400/20"
        >
          <ExternalLink size={12} />
          Open original article
        </a>
      )}

      {goldstein !== undefined && (
        <div>
          <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-panel-muted">
            <span>Goldstein scale</span>
            <span className="font-mono">{goldstein.toFixed(1)}</span>
          </div>
          <div className="relative h-1.5 overflow-hidden rounded-full bg-panel-border">
            <div
              className={"absolute top-0 h-full rounded-full transition-all " +
                (goldstein <= -5 ? "bg-rose-400" : goldstein <= 0 ? "bg-amber-400" : "bg-emerald-400")}
              style={{ width: `${gPct ?? 0}%` }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[9px] text-panel-muted">
            <span>conflictual −10</span>
            <span>cooperative +10</span>
          </div>
        </div>
      )}

      <MetaGrid rows={[
        ["Source",      (p.source_name as string) ?? "—"],
        ["CAMEO code",  cameo ?? null],
        ["Mentions",    mentions !== undefined ? String(mentions) : null],
        ["Language",    (p.language as string) ?? null],
        ["Reported at", (p.timestamp as string) ?? null],
        ["lat / lon",   p.lat !== undefined && p.lon !== undefined ? `${(p.lat as number).toFixed(4)}, ${(p.lon as number).toFixed(4)}` : null],
      ]} />
    </div>
  );
}

function SocialEvidence({ src }: { src: SourceNode }) {
  const p = src.properties as Record<string, unknown>;
  const text = (p.text as string) || "(no text)";

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-fuchsia-400/30 bg-fuchsia-400/5 p-3">
        <div className="text-[10px] uppercase tracking-wider text-fuchsia-300/80">
          Telegram message
        </div>
        <p className="mt-2 whitespace-pre-wrap text-sm text-panel-text">{text}</p>
      </div>
      <MetaGrid rows={[
        ["Channel",        (p.channel as string) ?? null],
        ["Verified",       (p.channel_verified as boolean) ? "yes" : "no"],
        ["Language",       (p.language as string) ?? null],
        ["Posted at",      (p.timestamp as string) ?? null],
        ["Views",          p.views !== undefined ? String(p.views) : null],
        ["Forwards",       p.forwards !== undefined ? String(p.forwards) : null],
        ["Matched place",  (p.matched_place as string) ?? null],
        ["lat / lon",      p.lat !== undefined && p.lon !== undefined ? `${(p.lat as number).toFixed(4)}, ${(p.lon as number).toFixed(4)}` : null],
      ]} />
    </div>
  );
}

function CompositeEvidence({ src }: { src: SourceNode }) {
  const p = src.properties as Record<string, unknown>;
  const grade = p.threat_grade as string | undefined;
  const conf  = p.confidence   as number | undefined;
  const corr  = p.corroboration_count as number | undefined;

  const gradeColor =
    grade === "RED"   ? "bg-rose-500/30 text-rose-100" :
    grade === "AMBER" ? "bg-amber-500/30 text-amber-100" :
                        "bg-emerald-500/30 text-emerald-100";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <span className={"rounded border px-2 py-0.5 text-xs font-bold " + gradeColor}>
          {grade ?? "—"}
        </span>
        <span className="font-mono text-xs text-panel-muted">
          conf {(conf ?? 0).toFixed(2)} · {corr ?? 0} sensor{corr === 1 ? "" : "s"}
        </span>
      </div>
      <p className="text-sm text-panel-text">{(p.summary as string) ?? "—"}</p>
      <MetaGrid rows={[
        ["Centroid", p.centroid_lat !== undefined && p.centroid_lon !== undefined
          ? `${(p.centroid_lat as number).toFixed(4)}, ${(p.centroid_lon as number).toFixed(4)}`
          : null],
        ["Created at", (p.created_at as string) ?? null],
      ]} />
    </div>
  );
}
