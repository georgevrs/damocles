// Right-rail layer panel — toggle visibility + opacity per map layer.
// Compact and collapsible so it doesn't dominate the map surface.

import { useState } from "react";
import { ChevronLeft, ChevronRight, Eye, EyeOff, Layers } from "lucide-react";
import { useDamocles, type MapLayerKey } from "../store/damocles";
import { useT } from "../i18n/useT";

export default function MapLayerPanel() {
  const { t } = useT();
  // Default closed — open by default ate ~30% of the map (E2E §6).
  // The analyst's first impression should be the map, not a control panel.
  const [open, setOpen] = useState(false);
  const layers = useDamocles((s) => s.mapLayers);
  const setLayer = useDamocles((s) => s.setLayer);

  const LAYER_GROUPS: { title: string; layers: { key: MapLayerKey; label: string }[] }[] = [
    {
      title: t("layers.group.sources"),
      layers: [
        { key: "vessels",      label: t("layers.vessels") },
        { key: "news",         label: t("layers.news") },
        { key: "composites",   label: t("layers.composites") },
        { key: "sar",          label: t("layers.sar") },
        { key: "flight",       label: t("layers.flight") },
      ],
    },
    {
      title: t("layers.group.inferred"),
      layers: [
        { key: "aoi_ai",       label: t("layers.aoi_ai") },
        { key: "aoi_user",     label: t("layers.aoi_user") },
        { key: "trajectories", label: t("layers.trajectories") },
        { key: "news_heatmap", label: t("layers.news_heatmap") },
      ],
    },
    {
      title: t("layers.group.external"),
      layers: [
        { key: "earthquakes", label: t("layers.earthquakes") },
        { key: "disasters",   label: t("layers.disasters") },
        { key: "eonet",       label: t("layers.eonet") },
      ],
    },
    {
      title: t("layers.group.basemap"),
      layers: [
        { key: "satellite_basemap", label: t("layers.satellite_basemap") },
      ],
    },
  ];

  return (
    <div className="absolute right-2 top-12 z-20 flex">
      {open && (
        <div className="w-60 rounded-md border border-panel-border bg-panel-bg/85 p-3 text-[11px] text-panel-text shadow-lg backdrop-blur-sm">
          <div className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider text-panel-muted">
            <Layers size={11} /> {t("layers.title")}
          </div>
          <div className="space-y-3">
            {LAYER_GROUPS.map((g) => (
              <div key={g.title}>
                <div className="mb-1 text-[9px] uppercase tracking-wider text-panel-muted">{g.title}</div>
                <div className="space-y-1.5">
                  {g.layers.map(({ key, label }) => {
                    const ls = layers[key];
                    return (
                      <div key={key} className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setLayer(key, { visible: !ls.visible })}
                          className={
                            "shrink-0 rounded p-0.5 " +
                            (ls.visible ? "text-emerald-300" : "text-panel-muted/60 hover:text-panel-muted")
                          }
                          title={ls.visible ? t("layers.hide") : t("layers.show")}
                        >
                          {ls.visible ? <Eye size={11} /> : <EyeOff size={11} />}
                        </button>
                        <span className={"flex-1 truncate " + (ls.visible ? "" : "text-panel-muted/50")}>
                          {label}
                        </span>
                        <input
                          type="range"
                          min={0} max={1} step={0.05}
                          value={ls.opacity}
                          onChange={(e) => setLayer(key, { opacity: Number(e.target.value) })}
                          disabled={!ls.visible}
                          className="h-1 w-12 accent-threat-amber/80"
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="ml-1 self-start rounded-md border border-panel-border bg-panel-bg/85 p-1 text-panel-muted hover:text-panel-text"
        title={open ? "Collapse layers" : "Expand layers"}
      >
        {open ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </div>
  );
}
