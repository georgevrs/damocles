// Standing-coverage badge — surfaces the Greece-wide scan freshness in the
// topbar. Click to trigger a manual scan (with confirmation).
//
// State semantics:
//   - scanning : a scan is in flight right now
//   - fresh    : last successful scan finished < 24h ago
//   - stale    : last success > 24h or partial/failed
//   - never    : no successful scan recorded yet
//
// Refreshes every 5s so the row count updates as the scan finishes.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, RefreshCw } from "lucide-react";
import {
  fetchStandingStatus, fetchStoreStats, triggerStandingScan,
} from "../api";
import { useT } from "../i18n/useT";

const STALE_HOURS = 24;

function relTime(iso: string | null, lang: "en" | "el"): string {
  if (!iso) return "";
  const dt = new Date(iso);
  const mins = Math.max(0, Math.floor((Date.now() - dt.getTime()) / 60_000));
  if (mins < 60) return lang === "el" ? `${mins} λ` : `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return lang === "el" ? `${hrs} ώ` : `${hrs}h`;
  const days = Math.floor(hrs / 24);
  return lang === "el" ? `${days} η` : `${days}d`;
}

export default function StandingCoverageBadge() {
  const { t, lang } = useT();
  const qc = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ["standing-status"],
    queryFn: fetchStandingStatus,
    refetchInterval: 5_000,
    staleTime: 4_000,
  });

  const { data: stats } = useQuery({
    queryKey: ["store-stats"],
    queryFn: fetchStoreStats,
    refetchInterval: 10_000,
  });

  const scan = useMutation({
    mutationFn: triggerStandingScan,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["standing-status"] });
      qc.invalidateQueries({ queryKey: ["store-stats"] });
    },
  });

  const inflight = !!status?.inflight_scan_id;
  const fresh = status?.freshest_ok ?? null;

  let kind: "scanning" | "fresh" | "stale" | "never" = "never";
  if (inflight) kind = "scanning";
  else if (fresh?.finished_at) {
    const age = (Date.now() - new Date(fresh.finished_at).getTime()) / 3_600_000;
    kind = age < STALE_HOURS ? "fresh" : "stale";
  }

  const dotColor =
    kind === "fresh"   ? "bg-emerald-400" :
    kind === "scanning" ? "bg-cyan-400 animate-pulse" :
    kind === "stale"   ? "bg-amber-400" :
                         "bg-rose-400";
  const labelText =
    kind === "fresh"   ? t("standing.fresh") :
    kind === "scanning" ? t("standing.scanning") :
    kind === "stale"   ? t("standing.stale") :
                         t("standing.never");

  // Aggregate row counts across all raw_* tables for the events tally.
  const eventCount =
    (stats?.raw_ais?.count ?? 0) +
    (stats?.raw_news?.count ?? 0) +
    (stats?.raw_social?.count ?? 0) +
    (stats?.raw_sar?.count ?? 0) +
    (stats?.raw_flight?.count ?? 0);

  const handleClick = () => {
    if (inflight) return;
    if (window.confirm(t("standing.scan.confirm"))) {
      scan.mutate();
    }
  };

  const ageText = fresh?.finished_at ? relTime(fresh.finished_at, lang) : "";

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={inflight}
      title={inflight ? t("standing.scanning") : t("standing.scan")}
      className={
        "flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[10px] " +
        "transition-colors disabled:cursor-progress " +
        (kind === "fresh"
          ? "border-emerald-400/40 text-emerald-300 hover:border-emerald-400/60"
          : kind === "scanning"
          ? "border-cyan-400/40 text-cyan-300"
          : kind === "stale"
          ? "border-amber-400/40 text-amber-300 hover:border-amber-400/60"
          : "border-rose-400/40 text-rose-300 hover:border-rose-400/60")
      }
    >
      {inflight
        ? <RefreshCw size={11} className="animate-spin" />
        : <Activity size={11} />}
      <span className="text-panel-text">{t("standing.label")}</span>
      <span>·</span>
      <span>{labelText}</span>
      {ageText && kind !== "scanning" && (
        <>
          <span className="text-panel-muted/60">·</span>
          <span className="text-panel-muted">{ageText}</span>
        </>
      )}
      {eventCount > 0 && (
        <>
          <span className="text-panel-muted/60">·</span>
          <span>{eventCount.toLocaleString()}</span>
        </>
      )}
      <span className={"ml-1 h-1.5 w-1.5 rounded-full " + dotColor} />
    </button>
  );
}
