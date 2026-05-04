// terra-draw integration on top of MapLibre.
// The control adds a "Draw AoI" button. Clicking it enters polygon mode;
// finishing the polygon (double-click) opens a small naming modal that
// POSTs the geometry to /api/aoi as a user-drawn AoI.

import { useEffect, useRef, useState } from "react";
import { Pencil, X, Check } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useQueryClient } from "@tanstack/react-query";
import { createAoI } from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";

type DrawInstance = {
  start(): void;
  stop(): void;
  setMode(name: string): void;
  on(event: string, cb: (e: { features: GeoJSON.Feature[] }) => void): void;
  getSnapshot(): GeoJSON.Feature[];
  clear?(): void;
};

interface Props {
  getMap: () => MapLibreMap | null;
}

export default function MapDrawControl({ getMap }: Props) {
  const { t } = useT();
  const drawRef = useRef<DrawInstance | null>(null);
  const drawingMode = useDamocles((s) => s.drawingMode);
  const setDrawingMode = useDamocles((s) => s.setDrawingMode);
  const [pendingFeature, setPendingFeature] = useState<GeoJSON.Feature | null>(null);
  const [nameEl, setNameEl] = useState("");
  const [nameEn, setNameEn] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const qc = useQueryClient();

  // Lazy-construct the terra-draw instance once the map is ready.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const map = getMap();
      if (!map || drawRef.current) return;
      try {
        const { TerraDraw, TerraDrawPolygonMode, TerraDrawRectangleMode } =
          await import("terra-draw");
        const { TerraDrawMapLibreGLAdapter } =
          await import("terra-draw-maplibre-gl-adapter");
        if (cancelled) return;
        const draw = new TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map }),
          modes: [
            new TerraDrawPolygonMode({
              styles: {
                fillColor: "#22d3ee",
                fillOpacity: 0.15,
                outlineColor: "#22d3ee",
                outlineWidth: 2,
              },
            }),
            new TerraDrawRectangleMode({
              styles: {
                fillColor: "#22d3ee",
                fillOpacity: 0.15,
                outlineColor: "#22d3ee",
                outlineWidth: 2,
              },
            }),
          ],
        }) as unknown as DrawInstance;

        draw.on("finish", () => {
          const feats = draw.getSnapshot();
          const last = feats[feats.length - 1];
          if (last) setPendingFeature(last);
        });
        drawRef.current = draw;
      } catch (e) {
        // terra-draw not installed in some build configurations; degrade.
        console.warn("terra-draw failed to initialise", e);
      }
    })();
    return () => { cancelled = true; };
  }, [getMap]);

  // Toggle drawing mode in/out of the active polygon mode.
  useEffect(() => {
    const draw = drawRef.current;
    if (!draw) return;
    if (drawingMode) {
      draw.start();
      draw.setMode("polygon");
    } else {
      try { draw.stop(); } catch { /* idempotent */ }
    }
  }, [drawingMode]);

  const cancelPending = () => {
    setPendingFeature(null);
    setNameEl(""); setNameEn(""); setDescription(""); setErr(null);
    drawRef.current?.clear?.();
  };

  const submit = async () => {
    if (!pendingFeature || !nameEl.trim()) return;
    setBusy(true); setErr(null);
    try {
      await createAoI({
        name_el: nameEl.trim(),
        name_en: nameEn.trim() || nameEl.trim(),
        description: description.trim() || undefined,
        geometry_geojson: pendingFeature.geometry as GeoJSON.Polygon,
      });
      qc.invalidateQueries({ queryKey: ["aoi"] });
      cancelPending();
      setDrawingMode(false);
    } catch (e) {
      setErr((e as Error).message ?? String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setDrawingMode(!drawingMode)}
        className={
          "absolute right-2 top-2 z-20 flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] backdrop-blur-sm " +
          (drawingMode
            ? "border-threat-amber/60 bg-threat-amber/15 text-threat-amber"
            : "border-panel-border bg-panel-bg/85 text-panel-muted hover:text-panel-text")
        }
        title={t("draw.cta.idle")}
      >
        <Pencil size={11} />
        {drawingMode ? t("draw.cta.active") : t("draw.cta.idle")}
      </button>

      {pendingFeature && (
        <div className="absolute left-1/2 top-1/2 z-30 w-80 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-panel-border bg-panel-bg p-4 shadow-2xl">
          <div className="mb-2 flex items-center justify-between">
            <div className="font-mono text-xs uppercase tracking-wider text-threat-amber">
              {t("draw.modal.title")}
            </div>
            <button onClick={cancelPending} className="text-panel-muted hover:text-panel-text">
              <X size={14} />
            </button>
          </div>
          <div className="space-y-2 text-xs">
            <input
              autoFocus
              value={nameEl}
              onChange={(e) => setNameEl(e.target.value)}
              placeholder={t("draw.field.name_el")}
              className="w-full rounded border border-panel-border bg-panel-surface px-2 py-1.5 text-panel-text outline-none focus:border-threat-amber/50"
            />
            <input
              value={nameEn}
              onChange={(e) => setNameEn(e.target.value)}
              placeholder={t("draw.field.name_en")}
              className="w-full rounded border border-panel-border bg-panel-surface px-2 py-1.5 text-panel-text outline-none focus:border-threat-amber/50"
            />
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("draw.field.desc")}
              rows={2}
              className="w-full resize-none rounded border border-panel-border bg-panel-surface px-2 py-1.5 text-panel-text outline-none focus:border-threat-amber/50"
            />
            {err && <div className="text-threat-red">{err}</div>}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={cancelPending}
              className="rounded border border-panel-border px-3 py-1 text-xs text-panel-muted hover:text-panel-text"
            >
              {t("draw.btn.cancel")}
            </button>
            <button
              onClick={() => void submit()}
              disabled={busy || !nameEl.trim()}
              className="flex items-center gap-1 rounded bg-threat-amber px-3 py-1 text-xs font-medium text-black hover:bg-threat-amber/90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Check size={12} />
              {busy ? t("draw.btn.saving") : t("draw.btn.save")}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
