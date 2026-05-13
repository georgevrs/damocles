// FlightDetail — pinned card in the BriefPanel when the analyst clicks
// a live OpenSky flight. Mirrors VesselDetail in look and structure so
// the right rail behaves consistently no matter what the analyst picks
// off the map.
//
// The flight is a live OpenSky position fix — there's no archived track
// history, so unlike vessels we don't render a polyline; the card is
// the entire detail surface.

import { Plane, X, ArrowUpRight } from "lucide-react";
import type { FlightFeature } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

export default function FlightDetail({ flight }: { flight: FlightFeature }) {
  const { t } = useT();
  const setActiveFlight = useDamocles((s) => s.setActiveFlight);
  const p = flight.properties;
  const [lon, lat] = flight.geometry.coordinates;
  const last = p.ts ? new Date(p.ts * 1000) : null;

  const speedKn = p.velocity_ms != null ? p.velocity_ms * 1.94384 : null;
  const altFt   = p.altitude_m != null ? p.altitude_m * 3.28084 : null;

  return (
    <div className="relative rounded-md border border-violet-400/40 bg-violet-400/5 p-3">
      <button
        type="button"
        onClick={() => setActiveFlight(null)}
        className="absolute right-2 top-2 rounded text-panel-muted hover:text-panel-text"
        title={t("evidence.close")}
      >
        <X size={13} />
      </button>

      <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-wider">
        <Plane size={11} className="text-violet-300" />
        <span className="text-panel-muted">{t("flight.detail.label")}</span>
        <span className={
          "ml-auto rounded border border-panel-border px-1.5 py-0.5 font-mono text-[10px] " +
          (p.on_ground ? "text-panel-muted" : "text-violet-300")
        }>
          {p.on_ground ? "ON GROUND" : "AIRBORNE"}
        </span>
      </div>

      <div className="font-serif text-base leading-tight text-panel-text">
        {p.callsign?.trim() || p.icao24.toUpperCase()}
      </div>
      <div className="mt-0.5 font-mono text-[11px] text-panel-muted">
        ICAO24 {p.icao24}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-panel-muted">
        <Field k={t("flight.origin")}  v={p.origin_country || "—"} />
        {altFt   != null && <Field k={t("flight.altitude")} v={`${Math.round(altFt).toLocaleString()} ft`} />}
        {speedKn != null && <Field k={t("flight.speed")}    v={`${Math.round(speedKn)} kn`} />}
        {p.heading != null && <Field k={t("flight.heading")} v={`${Math.round(p.heading)}°`} />}
        <Field k={t("vessel.coords")} v={`${lat.toFixed(3)}°, ${lon.toFixed(3)}°`} />
        {last && <Field k={t("vessel.last_seen")} v={last.toLocaleString()} />}
      </div>

      {p.vertical_rate != null && (
        <div className="mt-3 flex items-center gap-2 border-t border-panel-border/40 pt-2">
          <ArrowUpRight
            size={11}
            className={p.vertical_rate > 0 ? "text-emerald-300"
                     : p.vertical_rate < 0 ? "text-rose-300"
                     : "text-panel-muted"}
          />
          <span className="font-mono text-[10px] uppercase tracking-wider text-panel-muted">
            {t("flight.vrate")}
          </span>
          <span className="ml-auto font-mono text-[10px] text-panel-text">
            {(p.vertical_rate >= 0 ? "+" : "") + (p.vertical_rate * 196.85).toFixed(0)} fpm
          </span>
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
