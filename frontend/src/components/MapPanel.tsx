// MapPanel — Phase 2.
//
// Composes:
//   • CARTO Dark Matter basemap (default) ↔ ESA Sentinel-2 cloudless satellite
//   • Aegean operational AOI rectangle (legacy reference)
//   • AoI overlays — AI-inferred (amber) + user-drawn (cyan)
//   • Vessel trajectories (LineStrings) — toggleable
//   • News density H3 heatmap — toggleable
//   • Source point layers: vessels / news / composites
//   • Active-citation feature-state highlight + flyTo
//   • Layer panel (right-rail) and Draw-AoI control (top-right)

import { useEffect, useMemo, useRef, useState } from "react";
import Map, {
  type MapRef, NavigationControl, AttributionControl, Source, Layer,
} from "react-map-gl/maplibre";
import type {
  CircleLayer, FillLayer, LineLayer, SymbolLayer,
} from "react-map-gl/maplibre";
import type { Feature, FeatureCollection, Point, Polygon } from "geojson";
import { useQuery } from "@tanstack/react-query";
import {
  fetchAoI, fetchDisasters, fetchEarthquakes, fetchEonet,
  fetchFlights, fetchNewsHeatmap, fetchTrajectories, fetchVessels,
  fetchVesselTrajectory, fetchWatchGraph,
} from "../api";
import { useDamocles } from "../store/damocles";
import { useT } from "../i18n/useT";
import { GREECE_GEOJSON } from "../lib/geoGreece";
import type { GraphNode } from "../types";
import MapLayerPanel from "./MapLayerPanel";
import MapDrawControl from "./MapDrawControl";

const DARK_STYLE_URL = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// EOX Sentinel-2 cloudless WMTS — public, free, attribution-required.
// We use the CRS:84/WGS84 tile matrix which MapLibre serves as a raster source.
const S2_WMTS = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg";

// Minimal style with the satellite raster as the only basemap. Used when
// the analyst toggles satellite ON — replaces the dark-matter style entirely
// so no vector layers from CARTO sit between the raster and our overlays.
const SATELLITE_STYLE = {
  version: 8 as const,
  sources: {
    "satellite-base": {
      type: "raster" as const,
      tiles: [S2_WMTS],
      tileSize: 256,
      attribution: "© EOX::Maps · Sentinel-2 cloudless · ESA",
    },
  },
  layers: [
    { id: "satellite-base", type: "raster" as const, source: "satellite-base" },
  ],
  glyphs: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/glyphs/{fontstack}/{range}.pbf",
};

const AEGEAN_CENTER = { longitude: 25.5, latitude: 37.5 };
const AEGEAN_ZOOM = 5.6;

// Real Greek sovereign-territory outline (mainland + 73 islands), public-domain.
// Used as the operational AOI overlay — replaces the previous synthetic Aegean
// bbox rectangle so the analyst sees the actual jurisdiction we cover.
const GREECE_FC: FeatureCollection<Polygon> = {
  type: "FeatureCollection",
  features: (GREECE_GEOJSON.type === "MultiPolygon"
      ? (GREECE_GEOJSON.coordinates as number[][][][])
      : [GREECE_GEOJSON.coordinates as number[][][]]
    ).map((poly, i) => ({
      type: "Feature",
      properties: { name: `gr-${i}` },
      geometry: { type: "Polygon", coordinates: poly },
    })),
};

// ─── Source-point layers (kept from v1, with opacity now driven by store) ───

function vesselLayer(opacity: number): CircleLayer {
  return {
    id: "vessels", type: "circle", source: "vessels",
    paint: {
      "circle-radius": [
        "interpolate", ["linear"], ["coalesce", ["get", "length_m"], 0],
        0, 3, 50, 4, 150, 5.5, 300, 7,
      ],
      "circle-color": [
        "match", ["get", "ais_status"],
        "dark", "#ef4444",
        "broadcasting", "#22d3ee",
        "#94a3b8",
      ],
      "circle-stroke-color": "#0b0f17",
      "circle-stroke-width": 1,
      "circle-opacity": [
        "case",
        ["boolean", ["feature-state", "active"], false], 1.0,
        ["boolean", ["feature-state", "dimmed"], false], 0.18,
        opacity,
      ],
    },
  };
}

const VESSEL_PULSE: CircleLayer = {
  id: "vessel-pulse", type: "circle", source: "vessels",
  paint: {
    "circle-radius": 18,
    "circle-color": "transparent",
    "circle-stroke-color": "#fbbf24",
    "circle-stroke-width": 2,
    "circle-stroke-opacity": [
      "case",
      ["boolean", ["feature-state", "active"], false], 0.65,
      0,
    ],
  },
};

function newsLayer(opacity: number): CircleLayer {
  return {
    id: "news", type: "circle", source: "news",
    paint: {
      "circle-radius": [
        "interpolate", ["linear"], ["coalesce", ["get", "mentions"], 1],
        1, 3, 10, 4, 50, 5.5,
      ],
      "circle-color": [
        "interpolate", ["linear"], ["coalesce", ["get", "goldstein"], 0],
        -10, "#ef4444", -5, "#f59e0b", 0, "#94a3b8", 5, "#10b981",
      ],
      "circle-stroke-color": "#0b0f17",
      "circle-stroke-width": 0.8,
      "circle-opacity": [
        "case",
        ["boolean", ["feature-state", "active"], false], 1.0,
        ["boolean", ["feature-state", "dimmed"], false], 0.18,
        opacity,
      ],
    },
  };
}

function compositeLayer(opacity: number): SymbolLayer {
  return {
    id: "composites", type: "symbol", source: "composites",
    layout: {
      "icon-image": [
        "match", ["get", "threat_grade"],
        "RED", "icon-composite-red",
        "AMBER", "icon-composite-amber",
        "icon-composite-green",
      ],
      "icon-size": [
        "interpolate", ["linear"], ["coalesce", ["get", "corroboration_count"], 1],
        1, 0.7, 3, 1.1, 6, 1.4,
      ],
      "icon-allow-overlap": true,
    },
    paint: {
      "icon-opacity": [
        "case",
        ["boolean", ["feature-state", "active"], false], 1.0,
        ["boolean", ["feature-state", "dimmed"], false], 0.18,
        opacity,
      ],
    },
  };
}

// AoI fill + outline. Color is data-driven by threat_grade
// (GREEN / AMBER / RED) with a fallback to source colour when threat is null.
//
// User-drawn AoIs (source='user') without a threat read as cyan; AI-inferred
// AoIs default to amber when their threat is missing. Selection emphasises
// via `feature-state.selected` — opacity bump + thicker outline.
// Threat-grade-driven colour expression. Falls back to source-color when the
// AoI has no threat grade (user-drawn polygons usually start with no threat).
const AOI_COLOR_EXPR = [
  "case",
  ["==", ["get", "threat_grade"], "RED"],   "#ef4444",
  ["==", ["get", "threat_grade"], "AMBER"], "#f59e0b",
  ["==", ["get", "threat_grade"], "GREEN"], "#10b981",
  ["==", ["get", "source"], "user"],        "#22d3ee",
  "#f59e0b",
];

function aoiFill(layerId: string, source: string, opacity: number): FillLayer {
  return {
    id: layerId, type: "fill", source,
    paint: {
      "fill-color":   AOI_COLOR_EXPR as unknown as string,
      "fill-opacity": [
        "case",
        ["boolean", ["feature-state", "selected"], false], opacity * 0.55,
        opacity * 0.25,
      ] as unknown as number,
    },
  };
}
function aoiOutline(layerId: string, source: string, opacity: number): LineLayer {
  return {
    id: layerId, type: "line", source,
    paint: {
      "line-color":   AOI_COLOR_EXPR as unknown as string,
      "line-width": [
        "case",
        ["boolean", ["feature-state", "selected"], false], 2.5,
        1.2,
      ] as unknown as number,
      "line-opacity": opacity,
      "line-dasharray": [3, 2],
    },
  };
}
// RED-only "halo" outline whose width is animated via setPaintProperty in a
// useEffect below — gives RED AoIs a soft pulsing red ring that draws the
// analyst's eye to anything escalated by the standing scan.
function aoiPulseHalo(layerId: string, source: string): LineLayer {
  return {
    id: layerId, type: "line", source,
    filter: ["==", ["get", "threat_grade"], "RED"],
    paint: {
      "line-color":   "#ef4444",
      "line-width":   3,        // animated at runtime
      "line-opacity": 0.45,     // animated at runtime
      "line-blur":    2,
    },
  };
}

function aoiLabel(layerId: string, source: string): SymbolLayer {
  return {
    id: layerId, type: "symbol", source,
    layout: {
      "text-field": ["coalesce", ["get", "name_el"], ["get", "name_en"]],
      "text-size": 11,
      "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
      "text-anchor": "center",
      "text-allow-overlap": false,
    },
    paint: {
      "text-color":      AOI_COLOR_EXPR as unknown as string,
      "text-halo-color": "#0b0f17",
      "text-halo-width": 1.5,
    },
  };
}

// Vessel trajectories — line opacity decays toward the older end of the trail
function trajectoryLayer(opacity: number): LineLayer {
  return {
    id: "trajectories", type: "line", source: "trajectories",
    paint: {
      "line-color": "#22d3ee",
      "line-width": 1.4,
      "line-opacity": opacity,
    },
    layout: { "line-cap": "round", "line-join": "round" },
  };
}

// News H3 heatmap — fill colour by event count
function heatmapFill(opacity: number): FillLayer {
  return {
    id: "news-heatmap", type: "fill", source: "news_heatmap",
    paint: {
      "fill-color": [
        "interpolate", ["linear"], ["coalesce", ["get", "n_events"], 0],
        0,  "#1e293b",
        2,  "#fde68a",
        8,  "#f59e0b",
        20, "#ef4444",
      ],
      "fill-opacity": opacity * 0.55,
    },
  };
}

// ─── helpers: graph nodes → FeatureCollection ───────────────────────────────
function pointFeatures(nodes: GraphNode[]): FeatureCollection<Point> {
  const features: Feature<Point>[] = [];
  for (const n of nodes) {
    if (n.lat == null || n.lon == null) continue;
    const props = n.props ?? {};
    features.push({
      type: "Feature",
      id: n.id,
      properties: {
        node_id: n.id,
        node_type: n.type,
        label: n.label,
        ais_status: (props as Record<string, unknown>).ais_status ?? null,
        mmsi: (props as Record<string, unknown>).mmsi ?? null,
        length_m: (props as Record<string, unknown>).length_m ?? null,
        goldstein: (props as Record<string, unknown>).goldstein_scale ?? null,
        mentions: (props as Record<string, unknown>).mentions ?? null,
        threat_grade: (props as Record<string, unknown>).threat_grade ?? null,
        corroboration_count: (props as Record<string, unknown>).corroboration_count ?? null,
      },
      geometry: { type: "Point", coordinates: [n.lon, n.lat] },
    });
  }
  return { type: "FeatureCollection", features };
}
const EMPTY_PT: FeatureCollection<Point> = { type: "FeatureCollection", features: [] };
const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

// Composite icons (kept inline data URLs)
function diamondSvg(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14"><polygon points="7,1 13,7 7,13 1,7" fill="${color}" stroke="#0b0f17" stroke-width="1"/></svg>`;
  return "data:image/svg+xml;base64," + btoa(svg);
}
const COMPOSITE_ICON_URLS: Record<string, string> = {
  green: diamondSvg("#10b981"),
  amber: diamondSvg("#f59e0b"),
  red:   diamondSvg("#ef4444"),
};

// ─── Component ──────────────────────────────────────────────────────────────
export default function MapPanel({ className }: { className?: string }) {
  const { t } = useT();
  const mapRef = useRef<MapRef | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const activeWatch    = useDamocles((s) => s.activeWatch);
  const activeCitation = useDamocles((s) => s.activeCitation);
  const activeAoI      = useDamocles((s) => s.activeAoI);
  const setActiveAoI   = useDamocles((s) => s.setActiveAoI);
  const activeVessel   = useDamocles((s) => s.activeVessel);
  const setActiveVessel = useDamocles((s) => s.setActiveVessel);
  const layers         = useDamocles((s) => s.mapLayers);

  // Per-watch graph (vessels/news/composites markers)
  const { data: graph } = useQuery({
    queryKey: ["graph", activeWatch?.id],
    queryFn: () => activeWatch ? fetchWatchGraph(activeWatch.id, 800) : Promise.resolve(null),
    enabled: !!activeWatch,
    refetchInterval: 8000,
  });

  // AoIs — AI + user, both pulled together
  const { data: aoiData } = useQuery({
    queryKey: ["aoi"],
    queryFn: () => fetchAoI("all"),
    refetchInterval: 10_000,
  });
  const aoiAi = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: (aoiData?.features ?? []).filter((f) => f.properties?.source === "ai"),
  }), [aoiData]);
  const aoiUser = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection",
    features: (aoiData?.features ?? []).filter((f) => f.properties?.source === "user"),
  }), [aoiData]);

  // Trajectories (only fetched when the layer is on)
  const { data: trajectories } = useQuery({
    queryKey: ["trajectories"],
    queryFn: () => fetchTrajectories({ hours: 24 * 3, minPoints: 5, maxVessels: 200 }),
    enabled: layers.trajectories.visible,
    refetchInterval: 30_000,
  });

  // News heatmap (only fetched when the layer is on)
  const { data: heatmap } = useQuery({
    queryKey: ["news-heatmap"],
    queryFn: () => fetchNewsHeatmap({ hours: 24 * 7, h3Resolution: 5 }),
    enabled: layers.news_heatmap.visible,
    refetchInterval: 60_000,
  });

  // Always-on standing-scan vessels (DB-backed). Independent of activeWatch.
  const { data: standingVessels } = useQuery({
    queryKey: ["standing-vessels"],
    queryFn: () => fetchVessels({ hours: 24 * 14, limit: 2000 }),
    enabled: layers.vessels.visible,
    refetchInterval: 30_000,
  });

  // Live OpenSky flights — fetched only when the layer is on (rate limits).
  const { data: liveFlights } = useQuery({
    queryKey: ["flights"],
    queryFn: () => fetchFlights({ bbox: [19.0, 34.5, 29.7, 41.8] }),
    enabled: layers.flight.visible,
    refetchInterval: 20_000,
  });

  // External overlays — earthquakes, disasters, EONET. Cheap (10-min disk
  // cache backend-side) so we keep refetchInterval modest.
  const { data: earthquakesFc } = useQuery({
    queryKey: ["earthquakes"],
    queryFn: () => fetchEarthquakes(7, 3.5),
    enabled: layers.earthquakes.visible,
    refetchInterval: 10 * 60_000,
  });
  const { data: disastersFc } = useQuery({
    queryKey: ["disasters"],
    queryFn: () => fetchDisasters(),
    enabled: layers.disasters.visible,
    refetchInterval: 10 * 60_000,
  });
  const { data: eonetFc } = useQuery({
    queryKey: ["eonet"],
    queryFn: () => fetchEonet(14, "open"),
    enabled: layers.eonet.visible,
    refetchInterval: 10 * 60_000,
  });

  // Per-vessel trajectory polyline — fetched only when a vessel is selected.
  const { data: vesselTrajectory } = useQuery({
    queryKey: ["vessel-trajectory", activeVessel?.id],
    queryFn: () => activeVessel ? fetchVesselTrajectory(activeVessel.id) : null,
    enabled: !!activeVessel,
    staleTime: 60_000,
  });

  // Split graph by node kind
  const fcs = useMemo(() => {
    if (!graph) return { vessels: EMPTY_PT, news: EMPTY_PT, composites: EMPTY_PT };
    const vessels = graph.nodes.filter((n) => n.type === "Vessel");
    const news = graph.nodes.filter((n) => n.type === "NewsEvent");
    const composites = graph.nodes.filter((n) => n.type === "CompositeEvent");
    return {
      vessels: pointFeatures(vessels),
      news: pointFeatures(news),
      composites: pointFeatures(composites),
    };
  }, [graph]);

  // Citation highlight: feature-state on the three source layers + flyTo
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    for (const src of ["vessels", "news", "composites"] as const) {
      const fc = fcs[src];
      for (const f of fc.features) {
        if (f.id == null) continue;
        map.setFeatureState({ source: src, id: f.id as string }, { active: false, dimmed: false });
      }
    }
    if (!activeCitation) return;
    const citedIds = new Set(activeCitation.source_nodes.map((n) => n.node_id));
    for (const src of ["vessels", "news", "composites"] as const) {
      for (const f of fcs[src].features) {
        if (f.id == null) continue;
        const id = f.id as string;
        if (citedIds.has(id)) {
          map.setFeatureState({ source: src, id }, { active: true, dimmed: false });
        } else {
          map.setFeatureState({ source: src, id }, { active: false, dimmed: true });
        }
      }
    }
    const sn = activeCitation.source_nodes.find((n) => n.map_highlight);
    if (sn?.map_highlight) {
      map.flyTo({
        center: [sn.map_highlight.lon, sn.map_highlight.lat],
        zoom: 9.5, duration: 800, essential: true,
      });
    }
  }, [activeCitation, fcs]);

  // Composite icon registration (idempotent)
  useEffect(() => {
    const map = mapRef.current?.getMap();
    if (!map) return;
    const register = () => {
      for (const [grade, url] of Object.entries(COMPOSITE_ICON_URLS)) {
        const id = `icon-composite-${grade}`;
        if (map.hasImage(id)) continue;
        const img = new Image(14, 14);
        img.onload = () => { if (!map.hasImage(id)) map.addImage(id, img); };
        img.src = url;
      }
    };
    if (map.isStyleLoaded()) register();
    else map.once("style.load", register);
  }, []);

  // ── Click handlers — vessels first, then AoIs ────────────────────────
  // Vessel layers take priority over AoI layers because they sit visually
  // on top (smaller, rendered later) and a click on a vessel inside an
  // AoI should select the vessel, not the polygon underneath.
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    const vesselLayers = ["vessels", "standing-vessels-circle"];
    const aoiLayers    = ["aoi-ai-fill", "aoi-user-fill"];
    const allInteractive = [...vesselLayers, ...aoiLayers];

    type PointLike = { x: number; y: number };

    const onClick = (e: { point: PointLike }) => {
      // Vessels first
      const vesselHits = map.queryRenderedFeatures(e.point as never, { layers: vesselLayers });
      if (vesselHits.length > 0) {
        const f = vesselHits[0];
        const props = (f.properties ?? {}) as Record<string, unknown>;
        const geom = f.geometry as GeoJSON.Point;
        setActiveVessel({
          type: "Feature",
          id: String(f.id ?? props.node_id ?? ""),
          geometry: geom,
          properties: {
            node_id:     String(props.node_id ?? f.id ?? ""),
            node_type:   "Vessel",
            label:       String(props.label ?? props.node_id ?? ""),
            mmsi:        (props.mmsi as string | null) ?? null,
            ts:          (props.ts as string | null) ?? null,
            vessel_name: (props.vessel_name as string | null) ?? null,
            flag:        (props.flag as string | null) ?? null,
            length_m:    typeof props.length_m === "number" ? props.length_m : null,
            ais_status:  (props.ais_status as string | null) ?? null,
          },
        });
        return;
      }

      // Then AoIs
      const aoiHits = map.queryRenderedFeatures(e.point as never, { layers: aoiLayers });
      if (aoiHits.length === 0) {
        setActiveAoI(null);
        setActiveVessel(null);
        return;
      }
      const f = aoiHits[0];
      setActiveAoI({
        type: "Feature",
        id: String(f.id ?? (f.properties as { id?: string })?.id ?? ""),
        geometry: f.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon,
        properties: f.properties as never,
      });
    };

    const onMove = (e: { point: PointLike }) => {
      const hits = map.queryRenderedFeatures(e.point as never, { layers: allInteractive });
      map.getCanvas().style.cursor = hits.length > 0 ? "pointer" : "";
    };

    map.on("click", onClick);
    map.on("mousemove", onMove);

    return () => {
      map.off("click", onClick);
      map.off("mousemove", onMove);
    };
  }, [mapReady, setActiveAoI, setActiveVessel]);

  // Fly to the selected vessel's coordinates.
  useEffect(() => {
    if (!mapReady || !activeVessel) return;
    const map = mapRef.current?.getMap();
    if (!map) return;
    const [lon, lat] = activeVessel.geometry.coordinates;
    map.flyTo({ center: [lon, lat], zoom: 10, duration: 700, essential: true });
  }, [mapReady, activeVessel]);

  // ── activeAoI → flyTo + selection feature-state ──────────────────────
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current?.getMap();
    if (!map) return;

    // Clear previous selection on every AoI source
    for (const src of ["aoi-ai", "aoi-user"] as const) {
      const fc = src === "aoi-ai" ? aoiAi : aoiUser;
      for (const f of fc.features) {
        const id = (f as { id?: string | number }).id ?? (f.properties as { id?: string })?.id;
        if (id == null) continue;
        try { map.setFeatureState({ source: src, id }, { selected: false }); } catch { /* source not yet mounted */ }
      }
    }

    if (!activeAoI) return;

    const sourceId = activeAoI.properties.source === "user" ? "aoi-user" : "aoi-ai";
    try {
      map.setFeatureState({ source: sourceId, id: activeAoI.id }, { selected: true });
    } catch { /* feature not yet rendered, will retry on next data refresh */ }

    const lon = activeAoI.properties.centroid_lon;
    const lat = activeAoI.properties.centroid_lat;
    if (typeof lon === "number" && typeof lat === "number") {
      map.flyTo({ center: [lon, lat], zoom: 8.5, duration: 700, essential: true });
    }
  }, [mapReady, activeAoI, aoiAi, aoiUser]);

  // Pulse RED AoIs — line-width 3→7 and opacity 0.25→0.7 on a 1.6s sine wave.
  // Skips entirely when there are no RED features rendered (cheap idle).
  // Uses requestAnimationFrame + setPaintProperty so the animation is smooth
  // and pauses naturally when the tab is backgrounded.
  const hasRedAoI = useMemo(
    () => [...aoiAi.features, ...aoiUser.features].some(
      (f) => (f.properties as { threat_grade?: string } | null)?.threat_grade === "RED",
    ),
    [aoiAi, aoiUser],
  );
  useEffect(() => {
    if (!mapReady || !hasRedAoI) return;
    const map = mapRef.current?.getMap();
    if (!map) return;

    let raf = 0;
    const PERIOD_MS = 1600;
    const start = performance.now();

    const tick = () => {
      const elapsed = (performance.now() - start) % PERIOD_MS;
      const phase = elapsed / PERIOD_MS;            // 0..1
      const wave  = 0.5 - 0.5 * Math.cos(phase * 2 * Math.PI);   // 0..1
      const width   = 3 + 4 * wave;                 // 3..7 px
      const opacity = 0.25 + 0.45 * wave;           // 0.25..0.7
      for (const layerId of ["aoi-ai-pulse", "aoi-user-pulse"]) {
        if (!map.getLayer(layerId)) continue;
        try {
          map.setPaintProperty(layerId, "line-width", width);
          map.setPaintProperty(layerId, "line-opacity", opacity);
        } catch { /* layer torn down mid-frame */ }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [mapReady, hasRedAoI]);

  const stats = graph
    ? `${fcs.vessels.features.length}v · ${fcs.news.features.length}n · ${fcs.composites.features.length}c · ${aoiData?.features.length ?? 0} AoI`
    : "";

  return (
    <div className={"relative " + (className ?? "")}>
      <div className="pointer-events-none absolute left-2 top-2 z-20 flex items-center gap-2 rounded-md bg-panel-bg/80 px-2 py-1 text-xs text-panel-muted backdrop-blur-sm">
        <span className="h-2 w-2 rounded-full bg-threat-amber" />
        {t("panel.map")} · {layers.satellite_basemap.visible ? t("panel.map.satellite") : t("panel.map.label")}
        {stats && <span className="ml-2 font-mono text-[10px]">{stats}</span>}
      </div>

      <Map
        ref={mapRef}
        mapStyle={layers.satellite_basemap.visible ? SATELLITE_STYLE : DARK_STYLE_URL}
        initialViewState={{ ...AEGEAN_CENTER, zoom: AEGEAN_ZOOM }}
        minZoom={3}
        maxZoom={14}
        attributionControl={false}
        style={{ width: "100%", height: "100%" }}
        onLoad={() => setMapReady(true)}
        onStyleData={() => setMapReady(true)}
      >
        <NavigationControl position="bottom-right" showCompass={false} />
        <AttributionControl
          position="bottom-right"
          customAttribution={
            layers.satellite_basemap.visible
              ? "© EOX::Maps · Sentinel-2 cloudless · ESA"
              : "MapLibre + CARTO"
          }
        />

        {/* Satellite is now a true basemap — set via mapStyle above. No
            raster source/layer here, so every overlay below renders cleanly
            on top of the satellite tiles. */}

        {/* Greek sovereign-territory overlay (real coastlines, mainland + 73 islands) */}
        <Source id="greece-aoi" type="geojson" data={GREECE_FC}>
          <Layer
            id="greece-fill" type="fill" source="greece-aoi"
            paint={{ "fill-color": "#f59e0b", "fill-opacity": 0.05 }}
          />
          <Layer
            id="greece-outline" type="line" source="greece-aoi"
            paint={{ "line-color": "#f59e0b", "line-width": 1.0, "line-opacity": 0.55, "line-dasharray": [3, 2] }}
          />
        </Source>

        {/* AoI — AI inferred (color = threat_grade) */}
        {layers.aoi_ai.visible && (
          <Source id="aoi-ai" type="geojson" data={aoiAi} promoteId="id">
            <Layer {...aoiFill("aoi-ai-fill", "aoi-ai", layers.aoi_ai.opacity)} />
            <Layer {...aoiPulseHalo("aoi-ai-pulse", "aoi-ai")} />
            <Layer {...aoiOutline("aoi-ai-outline", "aoi-ai", layers.aoi_ai.opacity)} />
            <Layer {...aoiLabel("aoi-ai-label", "aoi-ai")} />
          </Source>
        )}

        {/* AoI — analyst drawn (cyan default, threat overrides) */}
        {layers.aoi_user.visible && (
          <Source id="aoi-user" type="geojson" data={aoiUser} promoteId="id">
            <Layer {...aoiFill("aoi-user-fill", "aoi-user", layers.aoi_user.opacity)} />
            <Layer {...aoiPulseHalo("aoi-user-pulse", "aoi-user")} />
            <Layer {...aoiOutline("aoi-user-outline", "aoi-user", layers.aoi_user.opacity)} />
            <Layer {...aoiLabel("aoi-user-label", "aoi-user")} />
          </Source>
        )}

        {/* News heatmap (H3 hex fill) */}
        {layers.news_heatmap.visible && (
          <Source id="news_heatmap" type="geojson" data={heatmap ?? EMPTY_FC}>
            <Layer {...heatmapFill(layers.news_heatmap.opacity)} />
          </Source>
        )}

        {/* Vessel trajectories — global layer */}
        {layers.trajectories.visible && (
          <Source id="trajectories" type="geojson" data={trajectories ?? EMPTY_FC}>
            <Layer {...trajectoryLayer(layers.trajectories.opacity)} />
          </Source>
        )}

        {/* Per-vessel trajectory — only the trajectory of the active vessel.
            Bright cyan, thicker, brought to the front. */}
        {activeVessel && vesselTrajectory && (
          <Source id="active-vessel-trajectory" type="geojson" data={vesselTrajectory as GeoJSON.FeatureCollection}>
            <Layer
              id="active-vessel-trajectory-line"
              type="line"
              source="active-vessel-trajectory"
              paint={{
                "line-color": "#22d3ee",
                "line-width": 2.5,
                "line-opacity": 0.9,
                "line-blur": 0.5,
              }}
              layout={{ "line-cap": "round", "line-join": "round" }}
            />
            <Layer
              id="active-vessel-trajectory-glow"
              type="line"
              source="active-vessel-trajectory"
              paint={{
                "line-color": "#22d3ee",
                "line-width": 8,
                "line-opacity": 0.18,
                "line-blur": 4,
              }}
            />
          </Source>
        )}

        {/* Source point layers */}
        {layers.composites.visible && (
          <Source id="composites" type="geojson" data={fcs.composites} promoteId="node_id">
            <Layer {...compositeLayer(layers.composites.opacity)} />
          </Source>
        )}
        {layers.news.visible && (
          <Source id="news" type="geojson" data={fcs.news} promoteId="node_id">
            <Layer {...newsLayer(layers.news.opacity)} />
          </Source>
        )}
        {layers.vessels.visible && (
          <Source id="vessels" type="geojson" data={fcs.vessels} promoteId="node_id">
            <Layer {...vesselLayer(layers.vessels.opacity)} />
            <Layer {...VESSEL_PULSE} />
          </Source>
        )}

        {/* Standing-scan vessels — independent of any active watch.
            Uses node_id as the promoted id so feature-state lookups don't
            collide with the per-watch vessels source above. */}
        {layers.vessels.visible && standingVessels && (
          <Source id="standing-vessels" type="geojson" data={standingVessels} promoteId="node_id">
            <Layer
              id="standing-vessels-circle" type="circle" source="standing-vessels"
              paint={{
                "circle-radius": [
                  "interpolate", ["linear"], ["coalesce", ["get", "length_m"], 0],
                  0, 2.5, 50, 3.5, 150, 5, 300, 6.5,
                ],
                "circle-color": [
                  "match", ["get", "ais_status"],
                  "dark",         "#ef4444",
                  "broadcasting", "#22d3ee",
                  "#94a3b8",
                ],
                "circle-stroke-color": "#0b0f17",
                "circle-stroke-width": 0.8,
                "circle-opacity": layers.vessels.opacity * 0.8,
              }}
            />
          </Source>
        )}

        {/* USGS Earthquakes — diamond markers sized by magnitude */}
        {layers.earthquakes.visible && earthquakesFc && (
          <Source id="earthquakes" type="geojson" data={earthquakesFc}>
            <Layer
              id="earthquakes-circle" type="circle" source="earthquakes"
              paint={{
                "circle-radius": [
                  "interpolate", ["linear"], ["coalesce", ["get", "magnitude"], 0],
                  3, 3, 5, 6, 7, 12,
                ],
                "circle-color": [
                  "match", ["get", "threat_grade"],
                  "RED", "#ef4444", "AMBER", "#f59e0b", "#94a3b8",
                ],
                "circle-stroke-color": "#0b0f17",
                "circle-stroke-width": 1,
                "circle-opacity":      layers.earthquakes.opacity * 0.85,
                "circle-stroke-opacity": layers.earthquakes.opacity,
              }}
            />
            <Layer
              id="earthquakes-label" type="symbol" source="earthquakes"
              minzoom={6}
              layout={{
                "text-field": ["concat", "M", ["to-string", ["coalesce", ["get", "magnitude"], 0]]],
                "text-size":   10,
                "text-offset": [0, 1.2],
                "text-anchor": "top",
                "text-allow-overlap": false,
              }}
              paint={{
                "text-color":      "#fbbf24",
                "text-halo-color": "#0b0f17",
                "text-halo-width": 1.2,
              }}
            />
          </Source>
        )}

        {/* GDACS disasters — square-style markers with category-based colour */}
        {layers.disasters.visible && disastersFc && (
          <Source id="disasters" type="geojson" data={disastersFc}>
            <Layer
              id="disasters-circle" type="circle" source="disasters"
              paint={{
                "circle-radius":     7,
                "circle-color": [
                  "match", ["get", "alert_level"],
                  "RED", "#ef4444", "ORANGE", "#f97316", "GREEN", "#22c55e", "#94a3b8",
                ],
                "circle-stroke-color": "#0b0f17",
                "circle-stroke-width": 1.5,
                "circle-opacity":      layers.disasters.opacity * 0.85,
                "circle-stroke-opacity": layers.disasters.opacity,
              }}
            />
          </Source>
        )}

        {/* NASA EONET — open natural events (wildfires/storms/volcanoes/etc.) */}
        {layers.eonet.visible && eonetFc && (
          <Source id="eonet" type="geojson" data={eonetFc}>
            <Layer
              id="eonet-circle" type="circle" source="eonet"
              paint={{
                "circle-radius": 5,
                "circle-color": [
                  "match", ["get", "category"],
                  "Wildfires",     "#f97316",
                  "Severe Storms", "#a78bfa",
                  "Volcanoes",     "#ef4444",
                  "Sea and Lake Ice", "#38bdf8",
                  "#94a3b8",
                ],
                "circle-stroke-color":   "#0b0f17",
                "circle-stroke-width":   1,
                "circle-opacity":        layers.eonet.opacity * 0.85,
                "circle-stroke-opacity": layers.eonet.opacity,
              }}
            />
          </Source>
        )}

        {/* Live OpenSky flights */}
        {layers.flight.visible && liveFlights && (
          <Source id="flights" type="geojson" data={liveFlights} promoteId="icao24">
            <Layer
              id="flights-circle" type="circle" source="flights"
              paint={{
                "circle-radius": [
                  "interpolate", ["linear"], ["coalesce", ["get", "altitude_m"], 0],
                  0, 2.5, 5000, 3.5, 12000, 4.5,
                ],
                "circle-color": [
                  "case",
                  ["==", ["get", "on_ground"], true], "#94a3b8",
                  "#a78bfa",
                ],
                "circle-stroke-color": "#0b0f17",
                "circle-stroke-width": 0.6,
                "circle-opacity": layers.flight.opacity,
              }}
            />
          </Source>
        )}
      </Map>

      {/* Right-rail layer panel + draw control */}
      <MapLayerPanel />
      <MapDrawControl getMap={() => mapRef.current?.getMap() ?? null} />

      {/* Legend */}
      <div className="pointer-events-none absolute right-2 bottom-8 z-20 space-y-0.5 rounded-md bg-panel-bg/85 px-2 py-1 text-[10px] backdrop-blur-sm">
        <Legend dot="#22d3ee" label={t("legend.vessel.broadcasting")} />
        <Legend dot="#ef4444" label={t("legend.vessel.dark")} />
        <Legend dot="#f59e0b" label={t("legend.news")} />
        <Legend dot="#10b981" label={t("legend.composite")} diamond />
        <Legend dot="#f59e0b" label={t("legend.aoi.ai")} outline />
        <Legend dot="#22d3ee" label={t("legend.aoi.user")} outline />
      </div>
    </div>
  );
}

function Legend({
  dot, label, diamond, outline,
}: { dot: string; label: string; diamond?: boolean; outline?: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-panel-muted">
      <span
        className={
          "inline-block h-2 w-2 " +
          (diamond ? "rotate-45 " : "rounded-full ") +
          (outline ? "border" : "")
        }
        style={
          outline
            ? { background: "transparent", borderColor: dot }
            : { background: dot }
        }
      />
      <span>{label}</span>
    </div>
  );
}
