// VesselDetail — rich vessel detail card rendered in BriefPanel when the
// analyst clicks a vessel marker on the map.
//
// Fetches extended provenance fields (dark-vessel score, SAR confidence,
// AIS match distance, SAR tile ID, per-MMSI trajectory) from the new
// GET /api/map/vessels/{event_id} endpoint. Falls back gracefully when
// any field is absent (AIS-only detections have no SAR data).

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Anchor, X, Activity, MapPin, Shield, AlertTriangle,
  Navigation, ChevronDown, ChevronUp,
} from "lucide-react";
import {
  fetchVesselDetail, fetchVesselTrajectory,
  type VesselFeature, type VesselDetailData, type VesselTrajectoryPoint,
} from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";
import type { SourceNode } from "../types";

// ── AIS status appearance config ──────────────────────────────────────────────
const AIS_CONFIG: Record<string, {
  border: string; dot: string; text: string;
  label_key: string; tooltip_key: string;
}> = {
  broadcasting: {
    border: "border-emerald-400/40", dot: "bg-emerald-400", text: "text-emerald-300",
    label_key:   "vessel.ais.broadcasting",
    tooltip_key: "vessel.ais.tooltip.broadcasting",
  },
  dark: {
    border: "border-rose-400/40", dot: "bg-rose-400", text: "text-rose-300",
    label_key:   "vessel.ais.dark",
    tooltip_key: "vessel.ais.tooltip.dark",
  },
  unknown: {
    border: "border-slate-500/40", dot: "bg-slate-400", text: "text-slate-400",
    label_key:   "vessel.ais.unknown",
    tooltip_key: "vessel.ais.tooltip.unknown",
  },
};

// ── Main component ─────────────────────────────────────────────────────────────
export default function VesselDetail({ vessel }: { vessel: VesselFeature }) {
  const { t } = useT();
  const setActiveVessel = useDamocles((s) => s.setActiveVessel);
  const openEvidence    = useDamocles((s) => s.openEvidence);
  const [showTraj, setShowTraj] = useState(false);

  const p = vessel.properties;
  const [lon, lat] = vessel.geometry.coordinates;
  const aisKey  = p.ais_status ?? "unknown";
  const aisConf = AIS_CONFIG[aisKey] ?? AIS_CONFIG.unknown;
  const last    = p.ts ? new Date(p.ts) : null;

  // Rich detail fetch (stale-while-revalidate, cached per event_id)
  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ["vessel-detail", vessel.id],
    queryFn:  () => fetchVesselDetail(vessel.id, 20),
    staleTime: 60_000,
    enabled:   !!vessel.id,
  });

  // Trajectory GeoJSON (shared key with MapPanel — zero extra network round-trip)
  const { data: trajGeo } = useQuery({
    queryKey: ["vessel-trajectory", vessel.id],
    queryFn:  () => fetchVesselTrajectory(vessel.id),
    staleTime: 60_000,
    enabled:   !!vessel.id,
  });
  const trajPtCount = (() => {
    if (!trajGeo?.features?.length) return 0;
    return (trajGeo.features[0].properties as { n_points?: number } | null)?.n_points ?? 0;
  })();

  // Build a SourceNode for EvidenceModal (SAR tile + metadata)
  function openSarEvidence() {
    if (!detail?.sar_tile_id) return;
    const src: SourceNode = {
      node_id:   vessel.id,
      node_type: "Vessel",
      cites_via: null,
      properties: {
        node_id:          vessel.id,
        mmsi:             detail.mmsi,
        vessel_name:      detail.vessel_name,
        flag:             detail.flag,
        length_m:         detail.length_m,
        ais_status:       detail.ais_status,
        lat:              detail.lat,
        lon:              detail.lon,
        dark_vessel_score: detail.dark_vessel_score,
        confidence:       detail.confidence,
        sar_tile_id:      detail.sar_tile_id,
        timestamp:        detail.ts,
      },
      raw_evidence: { type: "SAR_TILE", tile_id: detail.sar_tile_id },
      map_highlight: { lat: detail.lat, lon: detail.lon, radius_km: 1 },
      graph_highlight: { node_id: vessel.id },
    };
    openEvidence(src);
  }

  // Re-trigger MapPanel's fly-to by replacing activeVessel with a new object
  // (same data, new reference → useEffect fires again)
  function recenterMap() {
    setActiveVessel({ ...vessel });
  }

  const displayPoints = detail?.n_trajectory_points ?? trajPtCount;

  return (
    <div
      className="relative rounded-md border border-cyan-400/40 bg-cyan-400/5 p-3"
      role="region"
      aria-label="Vessel detail"
    >
      {/* Close */}
      <button
        type="button"
        onClick={() => setActiveVessel(null)}
        aria-label={t("evidence.close")}
        className="absolute right-2 top-2 rounded text-panel-muted hover:text-panel-text"
      >
        <X size={13} />
      </button>

      {/* ── Header ── */}
      <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider">
        <Anchor size={11} className="text-cyan-300" aria-hidden="true" />
        <span className="text-panel-muted">{t("vessel.detail.label")}</span>

        {/* AIS status badge */}
        <div
          role="status"
          aria-label={`AIS: ${t(aisConf.label_key)}`}
          title={t(aisConf.tooltip_key)}
          className={
            "ml-auto flex items-center gap-1.5 rounded border px-1.5 py-0.5 font-mono text-[10px] " +
            aisConf.border + " " + aisConf.text
          }
        >
          <span
            className={"inline-block h-1.5 w-1.5 rounded-full " + aisConf.dot}
            aria-hidden="true"
          />
          {t(aisConf.label_key)}
        </div>
      </div>

      {/* ── Vessel name + MMSI ── */}
      <div className="font-serif text-base leading-tight text-panel-text">
        {p.vessel_name || p.label}
      </div>
      {p.mmsi && (
        <div className="mt-0.5 font-mono text-[11px] text-panel-muted">
          MMSI {p.mmsi}
        </div>
      )}

      {/* ── Core metadata ── */}
      <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-panel-muted">
        {p.flag && <Field k={t("vessel.flag")} v={p.flag} />}
        {typeof p.length_m === "number" && (
          <Field k={t("vessel.length")} v={`${p.length_m.toFixed(0)} m`} />
        )}
        {/* Clickable coordinates → re-center map */}
        <button
          type="button"
          onClick={recenterMap}
          title={t("vessel.center_map")}
          aria-label={`${t("vessel.center_map")}: ${lat.toFixed(3)}°, ${lon.toFixed(3)}°`}
          className="col-span-2 flex items-center justify-between gap-2 rounded px-0.5 -mx-0.5 hover:bg-white/5 transition-colors"
        >
          <span className="flex items-center gap-1 text-panel-muted/70">
            <MapPin size={9} aria-hidden="true" />
            {t("vessel.coords")}
          </span>
          <span className="truncate text-panel-text">
            {lat.toFixed(3)}°, {lon.toFixed(3)}°
          </span>
        </button>
        {last && <Field k={t("vessel.last_seen")} v={last.toLocaleString()} />}
      </div>

      {/* ── Extended detection section (lazy fetch) ── */}
      {isLoading && <DetailSkeleton />}
      {isError && (
        <p className="mt-2 text-[10px] text-rose-400/80">{t("vessel.error")}</p>
      )}
      {detail && !isLoading && (
        <DetectionSection detail={detail} t={t} />
      )}

      {/* ── Trajectory toggle ── */}
      <div className="mt-3 border-t border-panel-border/40 pt-2">
        <button
          type="button"
          onClick={() => setShowTraj((v) => !v)}
          aria-expanded={showTraj}
          aria-controls="vessel-traj-preview"
          className="flex w-full items-center gap-2"
        >
          <Activity size={11} className="text-cyan-300" aria-hidden="true" />
          <span className="font-mono text-[10px] uppercase tracking-wider text-panel-muted">
            {t("vessel.trajectory")}
          </span>
          <span className="ml-auto font-mono text-[10px] text-panel-text">
            {displayPoints > 0
              ? `${displayPoints} ${t("vessel.trajectory.points")}`
              : t("vessel.no_trajectory")}
          </span>
          {showTraj
            ? <ChevronUp  size={11} className="text-panel-muted" aria-hidden="true" />
            : <ChevronDown size={11} className="text-panel-muted" aria-hidden="true" />
          }
        </button>

        {showTraj && detail && detail.trajectory_points.length > 0 && (
          <div id="vessel-traj-preview">
            <TrajectoryPreview points={detail.trajectory_points} t={t} />
          </div>
        )}
        {showTraj && detail && detail.trajectory_points.length === 0 && (
          <p className="mt-1 font-mono text-[10px] text-panel-muted">{t("vessel.no_trajectory")}</p>
        )}
      </div>

      {/* ── SAR evidence button ── */}
      {detail?.sar_tile_id && (
        <div className="mt-2 border-t border-panel-border/40 pt-2">
          <button
            type="button"
            onClick={openSarEvidence}
            aria-label={t("vessel.sar_evidence")}
            className="flex w-full items-center justify-center gap-2 rounded border border-cyan-400/30 bg-cyan-400/10 px-2 py-1.5 font-mono text-[10px] text-cyan-200 transition hover:bg-cyan-400/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-cyan-400"
          >
            <Shield size={11} aria-hidden="true" />
            {t("vessel.sar_evidence")}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Skeleton pulse while fetching detail ──────────────────────────────────────
function DetailSkeleton() {
  return (
    <div className="mt-3 space-y-1.5 animate-pulse" aria-busy="true" aria-label="Loading vessel data">
      {[70, 55, 80].map((w, i) => (
        <div key={i} className="h-2 rounded bg-panel-border/60" style={{ width: `${w}%` }} />
      ))}
    </div>
  );
}

// ── Detection / provenance section ────────────────────────────────────────────
function DetectionSection({
  detail,
  t,
}: {
  detail: VesselDetailData;
  t: (k: string) => string;
}) {
  const hasSpeed = detail.speed_kn !== null && detail.speed_kn !== undefined;
  const hasDist  = detail.ais_match_distance_km !== null && detail.ais_match_distance_km !== undefined;
  const hasConf  = detail.confidence !== null && detail.confidence !== undefined;
  const hasDark  = detail.dark_vessel_score !== null && detail.dark_vessel_score !== undefined;

  if (!hasSpeed && !hasDist && !hasConf && !hasDark) return null;

  return (
    <div className="mt-3 space-y-2 border-t border-panel-border/40 pt-2">
      {hasSpeed && (
        <MetaRow>
          <span className="flex items-center gap-1 text-panel-muted/70">
            <Navigation size={9} aria-hidden="true" />
            {t("vessel.speed")}
          </span>
          <span className="text-panel-text">{detail.speed_kn!.toFixed(1)} kn</span>
        </MetaRow>
      )}
      {hasDist && (
        <MetaRow>
          <span className="text-panel-muted/70">{t("vessel.ais_match_dist")}</span>
          <span className="text-panel-text">{detail.ais_match_distance_km!.toFixed(2)} km</span>
        </MetaRow>
      )}
      {hasConf && (
        <BarRow
          label={t("vessel.confidence")}
          value={detail.confidence!}
          barCls="bg-cyan-400/70"
          textCls="text-cyan-300"
        />
      )}
      {hasDark && (
        <DarkScoreRow
          label={t("vessel.dark_score")}
          tooltip={t("vessel.dark_score.tooltip")}
          value={detail.dark_vessel_score!}
        />
      )}
    </div>
  );
}

// ── Trajectory point list (last 10, scrollable) ───────────────────────────────
function TrajectoryPreview({
  points,
  t,
}: {
  points: VesselTrajectoryPoint[];
  t: (k: string) => string;
}) {
  const slice = points.slice(0, 10);
  return (
    <div className="mt-2 max-h-36 overflow-y-auto rounded border border-panel-border/40">
      <table className="w-full font-mono text-[9px]" aria-label="Trajectory points">
        <thead className="sticky top-0 bg-panel-bg text-panel-muted/60">
          <tr>
            <th className="py-0.5 px-1.5 text-left font-normal">UTC</th>
            <th className="py-0.5 px-1.5 text-right font-normal">Lat</th>
            <th className="py-0.5 px-1.5 text-right font-normal">Lon</th>
            <th className="py-0.5 px-1.5 text-right font-normal">{t("vessel.trajectory.speed")}</th>
          </tr>
        </thead>
        <tbody className="text-panel-muted">
          {slice.map((pt, i) => {
            const d  = new Date(pt.ts);
            const hm = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
            return (
              <tr key={i} className="border-t border-panel-border/20">
                <td className="py-0.5 px-1.5 text-left">{hm}</td>
                <td className="py-0.5 px-1.5 text-right text-panel-text">{pt.lat.toFixed(3)}</td>
                <td className="py-0.5 px-1.5 text-right text-panel-text">{pt.lon.toFixed(3)}</td>
                <td className="py-0.5 px-1.5 text-right">
                  {pt.speed_kn !== null && pt.speed_kn !== undefined
                    ? pt.speed_kn.toFixed(1)
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Utility sub-components ────────────────────────────────────────────────────
function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-panel-muted/70">{k}</span>
      <span className="truncate text-panel-text">{v}</span>
    </div>
  );
}

function MetaRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between font-mono text-[10px]">
      {children}
    </div>
  );
}

function BarRow({
  label, value, barCls, textCls,
}: {
  label: string; value: number; barCls: string; textCls: string;
}) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between font-mono text-[10px]">
        <span className="text-panel-muted/70">{label}</span>
        <span className={textCls}>{pct}%</span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-panel-border/60" role="meter" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        <div className={`h-full rounded-full transition-all ${barCls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DarkScoreRow({
  label, value, tooltip,
}: {
  label: string; value: number; tooltip: string;
}) {
  const pct      = Math.round(Math.min(1, Math.max(0, value)) * 100);
  const barCls   = pct >= 85 ? "bg-rose-400/80"  : pct >= 50 ? "bg-amber-400/80"  : "bg-emerald-400/80";
  const textCls  = pct >= 85 ? "text-rose-300"   : pct >= 50 ? "text-amber-300"   : "text-emerald-300";
  return (
    <div title={tooltip}>
      <div className="mb-0.5 flex items-center justify-between font-mono text-[10px]">
        <span className="flex items-center gap-1 text-panel-muted/70">
          <AlertTriangle size={9} aria-hidden="true" />
          {label}
        </span>
        <span className={textCls}>{pct}%</span>
      </div>
      <div
        className="h-1 overflow-hidden rounded-full bg-panel-border/60"
        role="meter"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`h-full rounded-full transition-all ${barCls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
