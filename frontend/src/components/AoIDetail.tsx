// Full AoI drill-down for the Brief panel.
//
// Layered as one panel-card with three sections:
//   1. Header — name + threat chip + close
//   2. Metadata grid — source, centroid, area, event count, scan, created
//   3. Member composites + source events, both expandable lists
//
// Member composites and sources are fetched via /api/aoi/{id}/explore in
// one round-trip. Clicking a composite or source row sets activeEvidence
// (Vessel / NewsEvent / SocialSignal payloads open the existing modal)
// or flies the map to the row's coordinates if no modal applies.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Anchor, ExternalLink, Globe, MessageSquare, Pencil, Sparkles, X, ChevronDown, ChevronRight } from "lucide-react";
import {
  fetchAoIExplore, fetchPreview,
  type AoICompositeRow, type AoIFeature, type AoISourceRow,
} from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

const GRADE_COLOR: Record<string, string> = {
  RED:   "border-rose-400/50 text-rose-300",
  AMBER: "border-amber-400/50 text-amber-300",
  GREEN: "border-emerald-400/50 text-emerald-300",
};

const GRADE_DOT: Record<string, string> = {
  RED:   "bg-rose-400",
  AMBER: "bg-amber-400",
  GREEN: "bg-emerald-400",
};

function polygonAreaKm2(geom: AoIFeature["geometry"]): number {
  const R_KM = 6371;
  const toRad = (d: number) => d * Math.PI / 180;
  const ringArea = (ring: number[][]): number => {
    if (ring.length < 3) return 0;
    let total = 0;
    for (let i = 0; i < ring.length; i++) {
      const [lon1, lat1] = ring[i];
      const [lon2, lat2] = ring[(i + 1) % ring.length];
      total += toRad(lon2 - lon1) * (2 + Math.sin(toRad(lat1)) + Math.sin(toRad(lat2)));
    }
    return Math.abs(total * R_KM * R_KM / 2);
  };
  const polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates];
  let area = 0;
  for (const poly of polys) area += ringArea(poly[0]);
  return area;
}

export default function AoIDetail({ aoi }: { aoi: AoIFeature }) {
  const { t, lang } = useT();
  const setActiveAoI = useDamocles((s) => s.setActiveAoI);
  const p = aoi.properties;
  const isUser = p.source === "user";
  const grade = p.threat_grade ?? "GREEN";
  const gradeCls = GRADE_COLOR[grade] ?? GRADE_COLOR.GREEN;
  const areaKm2 = polygonAreaKm2(aoi.geometry);
  const ts = p.created_at ? new Date(p.created_at) : null;

  // Language-aware name selection — in EN show name_en first; in EL show
  // name_el first. Always fall back to the other locale's name, then the id.
  const primaryName = (lang === "en" ? p.name_en || p.name_el : p.name_el || p.name_en)
    || aoi.id.slice(0, 12);
  const altName = lang === "en" ? p.name_el : p.name_en;

  const { data: explore, isLoading } = useQuery({
    queryKey: ["aoi-explore", aoi.id],
    queryFn: () => fetchAoIExplore(aoi.id),
    staleTime: 60_000,
  });

  return (
    <div
      className={
        "relative rounded-md border p-3 " +
        (grade === "RED"   ? "border-rose-400/40 bg-rose-400/5"   :
         grade === "AMBER" ? "border-amber-400/40 bg-amber-400/5" :
                             "border-emerald-400/30 bg-emerald-400/5")
      }
    >
      <button
        type="button"
        onClick={() => setActiveAoI(null)}
        className="absolute right-2 top-2 rounded text-panel-muted hover:text-panel-text"
        title={t("evidence.close")}
      >
        <X size={13} />
      </button>

      {/* Header */}
      <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider">
        {isUser
          ? <Pencil size={11} className="text-data-cyan" />
          : <Sparkles size={11} className="text-threat-amber" />}
        <span className="text-panel-muted">{t("aoi.detail.label")}</span>
        <span className={"ml-auto rounded border px-1.5 py-0.5 font-mono text-[10px] " + gradeCls}>
          {grade}
        </span>
      </div>

      <div className="font-serif text-lg leading-tight text-panel-text">
        {primaryName}
      </div>
      {altName && altName !== primaryName && (
        <div className="mt-0.5 text-xs italic text-panel-muted">{altName}</div>
      )}

      {p.description && (
        <p className="mt-2 text-xs leading-relaxed text-panel-text/85">{p.description}</p>
      )}

      {/* Metadata grid */}
      <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-panel-muted">
        <Field k={t("aoi.detail.source")} v={isUser ? t("aoi.detail.source.user") : t("aoi.detail.source.ai")} />
        <Field
          k={t("aoi.detail.centroid")}
          v={
            p.centroid_lat != null && p.centroid_lon != null
              ? `${p.centroid_lat.toFixed(3)}°, ${p.centroid_lon.toFixed(3)}°`
              : "—"
          }
        />
        <Field k={t("aoi.detail.area")} v={`${areaKm2.toFixed(0)} km²`} />
        <Field k={t("aoi.detail.events")} v={String(explore?.composites.length ?? p.citation_event_ids?.length ?? 0)} />
        {p.scan_id && <Field k={t("aoi.detail.scan")} v={p.scan_id.slice(0, 12)} />}
        {ts && <Field k={t("aoi.detail.created")} v={ts.toLocaleString()} />}
      </div>

      {p.threat_summary && (
        <div className="mt-3 border-t border-panel-border/40 pt-2 text-[11px] text-panel-text/85">
          <span className="font-mono text-[9px] uppercase tracking-wider text-panel-muted">
            {t("aoi.detail.summary")}
          </span>
          <p className="mt-1 leading-relaxed">{p.threat_summary}</p>
        </div>
      )}

      {/* Composites + sources lists */}
      {isLoading && (
        <div className="mt-3 px-1 py-2 text-center text-[11px] text-panel-muted">
          {t("aoi.detail.loading")}
        </div>
      )}
      {explore && explore.composites.length === 0 && (
        <div className="mt-3 px-1 py-2 text-center text-[11px] text-panel-muted">
          {t("aoi.detail.empty")}
        </div>
      )}
      {explore && explore.composites.length > 0 && (
        <div className="mt-3 border-t border-panel-border/40 pt-3">
          <CompositeList composites={explore.composites} sources={explore.sources} />
        </div>
      )}
    </div>
  );
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-panel-muted/70">{k}</span>
      <span className="truncate text-panel-text">{v}</span>
    </div>
  );
}

// ─── Composite + Source lists ─────────────────────────────────────────

function CompositeList({
  composites, sources,
}: { composites: AoICompositeRow[]; sources: AoISourceRow[] }) {
  const { t } = useT();
  const [open, setOpen] = useState<string | null>(composites[0]?.id ?? null);
  // Index sources by id for O(1) lookup from a composite row
  const srcMap = new Map(sources.map((s) => [s.id, s]));

  return (
    <div className="space-y-1.5">
      <div className="mb-1 flex items-center gap-2 text-[9px] uppercase tracking-widest text-panel-muted">
        <span>{t("aoi.detail.composites")} · {composites.length}</span>
      </div>
      {composites.map((c) => {
        const isOpen = open === c.id;
        return (
          <div key={c.id} className="rounded border border-panel-border/60 bg-panel-bg/40">
            <button
              type="button"
              onClick={() => setOpen(isOpen ? null : c.id)}
              className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-[11px] hover:bg-panel-surface/60"
            >
              {isOpen
                ? <ChevronDown size={11} className="text-panel-muted" />
                : <ChevronRight size={11} className="text-panel-muted" />}
              <span className={"h-1.5 w-1.5 rounded-full " + (GRADE_DOT[c.threat_grade] ?? GRADE_DOT.GREEN)} />
              <span className="font-mono text-[10px] text-panel-muted">
                {c.threat_grade}
              </span>
              <span className="flex-1 truncate text-panel-text">
                {c.summary || c.id.slice(0, 12)}
              </span>
              <span className="font-mono text-[9px] text-panel-muted">
                {c.source_node_ids.length} {t("aoi.composite.sources")}
              </span>
              {typeof c.confidence === "number" && (
                <span className="font-mono text-[9px] text-panel-muted">
                  {t("aoi.composite.confidence")} {(c.confidence * 100).toFixed(0)}%
                </span>
              )}
            </button>
            {isOpen && (
              <div className="border-t border-panel-border/40 px-2 py-1.5">
                <CompositeBody composite={c} sources={c.source_node_ids
                  .map((id) => srcMap.get(id))
                  .filter((s): s is AoISourceRow => !!s)} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CompositeBody({
  composite, sources,
}: { composite: AoICompositeRow; sources: AoISourceRow[] }) {
  const win = composite.time_window_start && composite.time_window_end
    ? `${new Date(composite.time_window_start).toLocaleString()} → ${new Date(composite.time_window_end).toLocaleString()}`
    : null;
  return (
    <div className="space-y-1.5 text-[10px]">
      {win && (
        <div className="font-mono text-panel-muted">
          {win}
        </div>
      )}
      {composite.centroid_lat != null && composite.centroid_lon != null && (
        <div className="font-mono text-panel-muted">
          {composite.centroid_lat.toFixed(3)}°, {composite.centroid_lon.toFixed(3)}°
        </div>
      )}
      {sources.length > 0 && (
        <ul className="mt-1 space-y-1">
          {sources.map((s) => <SourceRow key={s.id} source={s} />)}
        </ul>
      )}
    </div>
  );
}

function SourceRow({ source }: { source: AoISourceRow }) {
  const { t } = useT();
  if (source.type === "NewsEvent") return <NewsCard source={source} />;

  const typeMeta = source.type === "Vessel"
    ? { Icon: Anchor, color: "text-cyan-300", label: t("aoi.source.vessel") }
    : { Icon: MessageSquare, color: "text-fuchsia-300", label: t("aoi.source.social") };
  const Icon = typeMeta.Icon;
  const props = source.props as Record<string, unknown>;
  const sub = source.type === "Vessel"
    ? [props.mmsi, props.ais_status, props.length_m && `${props.length_m}m`].filter(Boolean).join(" · ")
    : [props.channel, props.language].filter(Boolean).join(" · ");

  return (
    <li className="flex items-center gap-2 rounded bg-panel-surface/40 px-2 py-1">
      <Icon size={11} className={typeMeta.color} />
      <span className={"font-mono text-[9px] uppercase tracking-wider " + typeMeta.color}>
        {typeMeta.label}
      </span>
      <span className="flex-1 truncate text-panel-text">{source.label}</span>
      {sub && <span className="hidden font-mono text-[9px] text-panel-muted lg:inline">{sub}</span>}
      {source.lat != null && source.lon != null && (
        <span className="font-mono text-[9px] text-panel-muted">
          {source.lat.toFixed(2)}°, {source.lon.toFixed(2)}°
        </span>
      )}
    </li>
  );
}

// Rich news card — pulls the article's og:image + og:title via /api/preview
// and renders a magazine-style row. Falls back gracefully when the host
// blocks the preview fetch.
function NewsCard({ source }: { source: AoISourceRow }) {
  const { t } = useT();
  const props = source.props as Record<string, unknown>;
  const sourceUrl = props.source_url as string | undefined;
  const sourceName = (props.source_name as string | undefined) || "news";
  const goldstein = props.goldstein_scale as number | undefined;
  const headline = source.label;

  const { data: preview } = useQuery({
    queryKey: ["preview", sourceUrl],
    queryFn: () => fetchPreview(sourceUrl as string),
    enabled: !!sourceUrl,
    staleTime: 24 * 3600 * 1000,
    retry: 1,
  });

  const title = (preview?.ok && preview.title) ? preview.title : headline;
  const image = preview?.ok ? preview.image : null;
  const desc  = preview?.ok ? preview.description : null;

  const card = (
    <li className="flex gap-2 rounded bg-panel-surface/40 p-2">
      {image
        ? (
          <img
            src={image}
            alt=""
            loading="lazy"
            referrerPolicy="no-referrer"
            className="h-14 w-20 flex-shrink-0 rounded object-cover"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        )
        : (
          <div className="flex h-14 w-20 flex-shrink-0 items-center justify-center rounded bg-panel-bg/60">
            <Globe size={18} className="text-amber-300/70" />
          </div>
        )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wider text-amber-300">
          <Globe size={10} />
          <span>{t("aoi.source.news")}</span>
          <span className="text-panel-muted/70">·</span>
          <span className="truncate text-panel-muted">{sourceName}</span>
          {typeof goldstein === "number" && (
            <>
              <span className="text-panel-muted/70">·</span>
              <span className="text-panel-muted">g={goldstein.toFixed(1)}</span>
            </>
          )}
        </div>
        <div className="mt-1 line-clamp-2 text-[11px] leading-snug text-panel-text">
          {title}
        </div>
        {desc && (
          <div className="mt-0.5 line-clamp-1 text-[10px] text-panel-muted">{desc}</div>
        )}
      </div>
      {sourceUrl && (
        <ExternalLink size={11} className="mt-1 flex-shrink-0 text-panel-muted/70" />
      )}
    </li>
  );

  return sourceUrl
    ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="block">{card}</a>
    : card;
}
