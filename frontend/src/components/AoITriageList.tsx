// AoI Triage List — the analyst's morning view.
//
// Cold-open behaviour (no watch + no AoI + no vessel selected): list every
// Area of Interest the standing scan produced, sorted RED → AMBER → GREEN,
// AI-inferred above analyst-drawn within each grade. Filter segmented
// control above the list ("All · RED · AI · Mine") so a 70-row list is
// triagable in seconds.
//
// One click on a row sets activeAoI in the store, which (a) flies the map,
// (b) populates AoITabbed in this same panel (Brief / DNA / Detail tabs),
// (c) lights up the AoI subgraph in GraphPanel.
//
// Empty state offers an inline "Run Greece-wide scan" CTA — first-time
// users land here before the cron has fired and need a way to bootstrap.

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Layers, Pencil, Sparkles, AlertTriangle, Play, Loader2 } from "lucide-react";
import { fetchAoI, triggerStandingScan, type AoIFeature } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

const GRADE_RANK: Record<string, number> = { RED: 0, AMBER: 1, GREEN: 2 };

const GRADE_COLOR: Record<string, string> = {
  RED:   "border-rose-400/50 text-rose-300 bg-rose-400/5",
  AMBER: "border-amber-400/50 text-amber-300 bg-amber-400/5",
  GREEN: "border-emerald-400/50 text-emerald-300 bg-emerald-400/5",
};

const GRADE_DOT: Record<string, string> = {
  RED:   "bg-rose-400",
  AMBER: "bg-amber-400",
  GREEN: "bg-emerald-400",
};

type Filter = "all" | "red" | "ai" | "user";

function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1)   return "now";
  if (mins < 60)  return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24)   return `${hrs}h`;
  return `${Math.round(hrs / 24)}d`;
}

function pickName(p: AoIFeature["properties"], lang: "en" | "el"): string {
  if (lang === "en") return p.name_en || p.name_el || "—";
  return p.name_el || p.name_en || "—";
}

export default function AoITriageList() {
  const { t, lang } = useT();
  const setActiveAoI = useDamocles((s) => s.setActiveAoI);
  const activeAoIId  = useDamocles((s) => s.activeAoI?.id ?? null);
  const [filter, setFilter] = useState<Filter>("all");
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["aoi"],
    queryFn: () => fetchAoI("all"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const scanMutation = useMutation({
    mutationFn: () => triggerStandingScan(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["aoi"] }),
  });

  const sorted = useMemo(() => {
    const features = data?.features ?? [];
    const filtered = features.filter((f) => {
      if (filter === "red")  return f.properties.threat_grade === "RED";
      if (filter === "ai")   return f.properties.source === "ai";
      if (filter === "user") return f.properties.source === "user";
      return true;
    });
    return filtered.sort((a, b) => {
      const ga = GRADE_RANK[a.properties.threat_grade ?? "GREEN"] ?? 3;
      const gb = GRADE_RANK[b.properties.threat_grade ?? "GREEN"] ?? 3;
      if (ga !== gb) return ga - gb;
      if (a.properties.source !== b.properties.source) {
        return a.properties.source === "ai" ? -1 : 1;
      }
      const ea = a.properties.citation_event_ids?.length ?? 0;
      const eb = b.properties.citation_event_ids?.length ?? 0;
      return eb - ea;
    });
  }, [data, filter]);

  const counts = useMemo(() => {
    const fs = data?.features ?? [];
    const c = { total: fs.length, RED: 0, AMBER: 0, GREEN: 0, ai: 0, user: 0 };
    for (const f of fs) {
      const g = (f.properties.threat_grade ?? "GREEN") as "RED" | "AMBER" | "GREEN";
      if (g in c) (c as Record<string, number>)[g]++;
      if (f.properties.source === "ai") c.ai++;
      else c.user++;
    }
    return c;
  }, [data]);

  if (isLoading) {
    return (
      <div className="rounded-md border border-panel-border bg-panel-surface/40 p-3 text-[11px] text-panel-muted">
        {t("aoi.triage.loading")}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-md border border-rose-400/40 bg-rose-400/5 p-3 text-[11px] text-rose-200">
        <div className="flex items-center gap-2">
          <AlertTriangle size={12} />
          <span>{t("aoi.triage.error")}</span>
        </div>
      </div>
    );
  }

  if (counts.total === 0) {
    return (
      <div className="rounded-md border border-panel-border bg-panel-surface/40 p-4 text-center">
        <Layers size={20} className="mx-auto mb-2 text-amber-300/50" />
        <div className="text-[11px] leading-relaxed text-panel-muted">{t("aoi.triage.empty")}</div>
        <button
          type="button"
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="mx-auto mt-3 flex items-center gap-1.5 rounded-md border border-amber-400/50 bg-amber-400/15 px-3 py-1.5 font-mono text-[11px] text-amber-200 hover:bg-amber-400/25 disabled:opacity-60"
        >
          {scanMutation.isPending
            ? <><Loader2 size={11} className="animate-spin" />{t("standing.scanning")}</>
            : <><Play size={11} />{t("standing.scan")}</>}
        </button>
      </div>
    );
  }

  const filters: { id: Filter; label: string; n: number; cls: string }[] = [
    { id: "all",  label: t("aoi.triage.filter.all"),  n: counts.total, cls: "border-panel-border" },
    { id: "red",  label: "RED",                       n: counts.RED,   cls: "border-rose-400/50 text-rose-200" },
    { id: "ai",   label: t("aoi.triage.filter.ai"),   n: counts.ai,    cls: "border-amber-400/40 text-amber-200" },
    { id: "user", label: t("aoi.triage.filter.user"), n: counts.user,  cls: "border-cyan-400/40 text-cyan-200" },
  ];

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center gap-2 px-1">
        <Layers size={11} className="text-panel-muted" />
        <span className="text-[10px] uppercase tracking-wider text-panel-muted">
          {t("aoi.triage.title")}
        </span>
        <span className="font-mono text-[10px] text-panel-text">{counts.total}</span>
        <div className="ml-auto flex items-center gap-1 font-mono text-[9px]">
          {counts.RED > 0 && (
            <span className="rounded border border-rose-400/40 bg-rose-400/10 px-1 py-0.5 text-rose-200">
              {counts.RED} R
            </span>
          )}
          {counts.AMBER > 0 && (
            <span className="rounded border border-amber-400/40 bg-amber-400/10 px-1 py-0.5 text-amber-200">
              {counts.AMBER} A
            </span>
          )}
          {counts.GREEN > 0 && (
            <span className="rounded border border-emerald-400/40 bg-emerald-400/10 px-1 py-0.5 text-emerald-200">
              {counts.GREEN} G
            </span>
          )}
        </div>
      </div>

      {/* Filter chips */}
      <div className="flex gap-1 rounded-md border border-panel-border bg-panel-surface/30 p-1 text-[10px]">
        {filters.map((f) => {
          const active = filter === f.id;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={
                "flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1 transition-colors " +
                (active
                  ? "bg-amber-400/15 text-amber-200"
                  : "text-panel-muted hover:text-panel-text")
              }
            >
              <span className="font-mono uppercase tracking-wider">{f.label}</span>
              <span className="font-mono text-panel-muted/80">{f.n}</span>
            </button>
          );
        })}
      </div>

      {sorted.length === 0 ? (
        <div className="rounded border border-panel-border/40 bg-panel-surface/20 px-2 py-3 text-center text-[11px] text-panel-muted">
          {t("aoi.triage.no_match")}
        </div>
      ) : (
        <ul className="space-y-1.5">
          {sorted.map((aoi) => (
            <TriageRow
              key={aoi.id}
              aoi={aoi}
              lang={lang}
              isActive={aoi.id === activeAoIId}
              onClick={() => setActiveAoI(aoi)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function TriageRow({
  aoi, lang, isActive, onClick,
}: {
  aoi:      AoIFeature;
  lang:     "en" | "el";
  isActive: boolean;
  onClick:  () => void;
}) {
  const { t } = useT();
  const p = aoi.properties;
  const grade = p.threat_grade ?? "GREEN";
  const events = p.citation_event_ids?.length ?? 0;
  const isUser = p.source === "user";
  const accent = GRADE_COLOR[grade] ?? GRADE_COLOR.GREEN;
  const dot = GRADE_DOT[grade] ?? GRADE_DOT.GREEN;
  const ago = timeAgo(p.updated_at ?? p.created_at);
  const primaryName = pickName(p, lang);
  const altName = lang === "en" ? p.name_el : p.name_en;

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={
          "group w-full rounded-md border px-2.5 py-2 text-left transition-colors " +
          accent +
          (isActive ? " ring-1 ring-amber-300/60" : " hover:brightness-125")
        }
      >
        <div className="flex items-center gap-2">
          <span
            className={
              "h-2 w-2 flex-shrink-0 rounded-full " + dot +
              (grade === "RED" ? " animate-pulse" : "")
            }
          />
          {isUser
            ? <Pencil    size={11} className="flex-shrink-0 text-cyan-300" />
            : <Sparkles  size={11} className="flex-shrink-0 text-amber-300" />}
          <span className="flex-1 truncate font-serif text-[13px] leading-tight text-panel-text">
            {primaryName}
          </span>
          <span className="font-mono text-[9px] text-panel-muted">
            {events} {t("aoi.triage.events")}
          </span>
        </div>

        {altName && altName !== primaryName && (
          <div className="mt-0.5 ml-6 truncate text-[10px] italic text-panel-muted">
            {altName}
          </div>
        )}

        {p.threat_summary && (
          <div className="mt-1 ml-6 line-clamp-2 text-[10px] leading-snug text-panel-text/80">
            {p.threat_summary}
          </div>
        )}

        <div className="mt-1 ml-6 flex items-center gap-2 font-mono text-[9px] text-panel-muted/80">
          {p.centroid_lat != null && p.centroid_lon != null && (
            <span>
              {p.centroid_lat.toFixed(2)}°, {p.centroid_lon.toFixed(2)}°
            </span>
          )}
          {ago && <span className="ml-auto">{ago}</span>}
        </div>
      </button>
    </li>
  );
}
