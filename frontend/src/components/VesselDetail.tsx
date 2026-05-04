// VesselDetail — pinned card in the BriefPanel when the analyst clicks a
// vessel marker. Shows MMSI, name, flag, length, AIS status, last
// position, and a small trajectory-info row (number of historical points).
//
// The actual trajectory polyline is rendered on the *map* by MapPanel —
// this component just surfaces the metadata + a "show trajectory" badge.

import { useQuery } from "@tanstack/react-query";
import { Anchor, X, Activity } from "lucide-react";
import { fetchVesselTrajectory, type VesselFeature } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

const AIS_COLOR: Record<string, string> = {
  broadcasting: "text-cyan-300",
  dark:         "text-rose-300",
  unknown:      "text-panel-muted",
};

export default function VesselDetail({ vessel }: { vessel: VesselFeature }) {
  const { t } = useT();
  const setActiveVessel = useDamocles((s) => s.setActiveVessel);
  const p = vessel.properties;

  // Pre-fetch the trajectory here too (StaleWhileRevalidate); the map uses
  // the same key so the data is shared and only fetched once.
  const { data: traj } = useQuery({
    queryKey: ["vessel-trajectory", vessel.id],
    queryFn: () => fetchVesselTrajectory(vessel.id),
    staleTime: 60_000,
    enabled: !!vessel.id,
  });
  const trajPoints = (() => {
    if (!traj?.features?.length) return 0;
    const f = traj.features[0];
    return (f.properties as { n_points?: number } | null)?.n_points ?? 0;
  })();

  const aisCls = AIS_COLOR[p.ais_status ?? "unknown"] ?? AIS_COLOR.unknown;
  const last = p.ts ? new Date(p.ts) : null;
  const [lon, lat] = vessel.geometry.coordinates;

  return (
    <div className="relative rounded-md border border-cyan-400/40 bg-cyan-400/5 p-3">
      <button
        type="button"
        onClick={() => setActiveVessel(null)}
        className="absolute right-2 top-2 rounded text-panel-muted hover:text-panel-text"
        title={t("evidence.close")}
      >
        <X size={13} />
      </button>

      <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider">
        <Anchor size={11} className="text-cyan-300" />
        <span className="text-panel-muted">{t("vessel.detail.label")}</span>
        <span className={"ml-auto rounded border border-panel-border px-1.5 py-0.5 font-mono text-[10px] " + aisCls}>
          {(p.ais_status ?? "unknown").toUpperCase()}
        </span>
      </div>

      <div className="font-serif text-base leading-tight text-panel-text">
        {p.vessel_name || p.label}
      </div>
      {p.mmsi && (
        <div className="mt-0.5 font-mono text-[11px] text-panel-muted">
          MMSI {p.mmsi}
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-panel-muted">
        {p.flag &&
          <Field k={t("vessel.flag")} v={p.flag} />}
        {typeof p.length_m === "number" &&
          <Field k={t("vessel.length")} v={`${p.length_m.toFixed(0)} m`} />}
        <Field k={t("vessel.coords")} v={`${lat.toFixed(3)}°, ${lon.toFixed(3)}°`} />
        {last && <Field k={t("vessel.last_seen")} v={last.toLocaleString()} />}
      </div>

      <div className="mt-3 flex items-center gap-2 border-t border-panel-border/40 pt-2">
        <Activity size={11} className="text-cyan-300" />
        <span className="font-mono text-[10px] uppercase tracking-wider text-panel-muted">
          {t("vessel.trajectory")}
        </span>
        <span className="ml-auto font-mono text-[10px] text-panel-text">
          {trajPoints > 0
            ? `${trajPoints} ${t("vessel.trajectory.points")}`
            : t("vessel.no_trajectory")}
        </span>
      </div>
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
