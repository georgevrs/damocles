"""Geospatial sensor: Sentinel-1 SAR acquisition + CFAR vessel detection.

Pipeline
--------
    bbox + time window
        ↓
    SentinelHubRequest → IW VV+VH GRD tile → numpy float32
        ↓
    CFAR (cfar.py) on dB-scaled VV → list[CFARDetection] in pixel space
        ↓
    pixel→geo conversion → list[Vessel] in lat/lon
        ↓
    cache PNG preview to data/cache/sar/<tile_id>.png for the evidence modal

The sensor uses the **Copernicus Data Space** endpoints, not the deprecated
SciHub. Authentication is OAuth2 client credentials (client_id + client_secret
from `.env`).

Free-tier budget: each ~50×50 km tile at 10 m/px costs ~10 processing units.
The full demo seed (March 14-20 2024 Aegean) consumes ~150 PU total —
comfortably inside the 30k/month free quota.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.config import settings
from backend.models.event import AISStatus, Vessel
from backend.store.cache import CachedSensorMixin

from .base import BaseSensor, BBox, SensorResult
from .cfar import CFARDetection, CFARParams, cfar_detect

log = logging.getLogger(__name__)

# Sentinel-1 IW VV+VH evalscript — returns dB-scaled VV in band 0, dB VH in band 1.
# We only use VV for CFAR; VH is captured for downstream agent reasoning
# (cross-pol ratio is a strong vessel-vs-rough-sea discriminator).
EVALSCRIPT_SAR = """\
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["VV", "VH"] }],
    output: { bands: 2, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(s) {
  // Convert linear backscatter to dB; clamp very small values to avoid log(0).
  var vv_db = 10 * Math.log10(Math.max(s.VV, 1e-6));
  var vh_db = 10 * Math.log10(Math.max(s.VH, 1e-6));
  return [vv_db, vh_db];
}
"""


def _pixel_to_lonlat(
    row: int,
    col: int,
    bbox: BBox,
    img_h: int,
    img_w: int,
) -> tuple[float, float]:
    """Convert a pixel (row, col) inside an image of shape (img_h, img_w)
    that spans ``bbox`` in WGS84 to (lon, lat).

    Sentinel Hub returns rasters with row 0 at the **top** = max latitude.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    # +0.5 to land on pixel centroid
    frac_x = (col + 0.5) / img_w
    frac_y = (row + 0.5) / img_h
    lon = min_lon + frac_x * (max_lon - min_lon)
    lat = max_lat - frac_y * (max_lat - min_lat)
    return lon, lat


def _detection_to_vessel(
    det: CFARDetection,
    bbox: BBox,
    img_h: int,
    img_w: int,
    timestamp: datetime,
    tile_id: str,
) -> Vessel:
    lon, lat = _pixel_to_lonlat(det.row, det.col, bbox, img_h, img_w)
    # Approximate vessel length from cluster bbox: longer side × 10 m/px.
    rmin, cmin, rmax, cmax = det.bbox_pixels
    length_px = max(rmax - rmin, cmax - cmin)
    length_m = float(length_px * 10.0)
    return Vessel(
        id=str(uuid.uuid4()),
        lat=lat,
        lon=lon,
        timestamp=timestamp,
        detection_source="SAR",
        ais_status=AISStatus.UNKNOWN,   # set later by AIS cross-reference
        confidence=det.confidence,
        sar_tile_id=tile_id,
        length_m=length_m,
    )


class GeospatialSensor(CachedSensorMixin, BaseSensor[Vessel]):
    name = "geospatial"
    cache_kind = "ais"  # SAR vessels are Vessel objects; mirrored to raw_sar by the mixin

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        cfar_params: CFARParams | None = None,
        resolution_m: int = 10,
        cache_dir: Path | None = None,
    ):
        self.client_id = client_id or settings.SENTINELHUB_CLIENT_ID
        self.client_secret = client_secret or settings.SENTINELHUB_CLIENT_SECRET
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "GeospatialSensor needs SENTINELHUB_CLIENT_ID and SENTINELHUB_CLIENT_SECRET. "
                "See docs/credentials.md §3."
            )
        self.cfar_params = cfar_params or CFARParams()
        self.resolution_m = resolution_m
        self.cache_dir = cache_dir or (settings.cache_dir / "sar")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sh_config = self._build_sh_config()
        self.cache_ttl_seconds = settings.CACHE_TTL_SAR

    # ─── Sentinel Hub config ─────────────────────────────────────────────────
    def _build_sh_config(self):
        from sentinelhub import SHConfig
        cfg = SHConfig()
        cfg.sh_client_id = self.client_id
        cfg.sh_client_secret = self.client_secret
        # Copernicus Data Space (the new home of Sentinel data, not the old SciHub)
        cfg.sh_token_url = (
            "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
        )
        cfg.sh_base_url = "https://sh.dataspace.copernicus.eu"
        return cfg

    # ─── Public API ──────────────────────────────────────────────────────────
    async def fetch(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        **kwargs: Any,
    ) -> SensorResult[Vessel]:
        return await self._run_with_cache(
            bbox=bbox,
            time_from=time_from,
            time_to=time_to,
            sensor_name=self.name,
            fetcher=lambda: self._fetch_live(bbox, time_from, time_to),
        )

    async def _fetch_live(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
    ) -> SensorResult[Vessel]:
        start = time.time()
        # Sentinel Hub library is sync; offload to a worker thread.
        sar, img_meta = await asyncio.to_thread(
            self._fetch_tile_sync, bbox, time_from, time_to
        )

        if sar is None:
            log.warning("No Sentinel-1 data available for bbox=%s window=%s..%s",
                        bbox, time_from, time_to)
            return SensorResult(
                sensor_name=self.name, events=[], bbox=bbox,
                time_from=time_from, time_to=time_to,
                metadata={"tiles": 0, "reason": "no_data"},
                duration_ms=(time.time() - start) * 1000,
            )

        # CFAR runs on VV (band 0). Off-load to a worker thread — it's
        # CPU-bound numpy that releases the GIL via SciPy under the hood.
        vv_db = sar[..., 0]
        detections = await asyncio.to_thread(cfar_detect, vv_db, self.cfar_params)
        h, w = vv_db.shape
        log.info("Geospatial sensor: %d detections on %dx%d tile (%.0f ms)",
                 len(detections), h, w, (time.time() - start) * 1000)

        # Use mid-window as detection timestamp (Sentinel Hub doesn't return per-tile
        # acquisition time directly through the simple Process API path). For the demo
        # this is acceptable — a finer client could query the catalog API for ISO timestamps.
        midpoint = time_from + (time_to - time_from) / 2

        vessels = [
            _detection_to_vessel(det, bbox, h, w, midpoint, img_meta["tile_id"])
            for det in detections
        ]

        # Persist a preview PNG so the evidence modal can show the raw SAR tile
        # with detection bounding boxes overlaid.
        preview_path = self.cache_dir / f"{img_meta['tile_id']}.png"
        await asyncio.to_thread(self._save_preview, vv_db, detections, preview_path)
        img_meta["preview_path"] = str(preview_path)

        return SensorResult(
            sensor_name=self.name,
            events=vessels,
            bbox=bbox,
            time_from=time_from,
            time_to=time_to,
            metadata={
                **img_meta,
                "tiles": 1,
                "detections": len(detections),
                "image_shape": (h, w),
                "cfar_params": self.cfar_params.__dict__,
            },
            duration_ms=(time.time() - start) * 1000,
        )

    # ─── Internals ───────────────────────────────────────────────────────────
    def _fetch_tile_sync(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
    ) -> tuple[np.ndarray | None, dict]:
        """Synchronous Sentinel Hub fetch. Returns (image, metadata).

        ``image`` is None when no data is available for the request window.
        """
        from sentinelhub import (
            BBox as SHBBox,
            CRS,
            DataCollection,
            MimeType,
            SentinelHubRequest,
            bbox_to_dimensions,
        )

        # Ensure timestamps are tz-aware UTC; Sentinel Hub expects ISO 8601.
        if time_from.tzinfo is None:
            time_from = time_from.replace(tzinfo=timezone.utc)
        if time_to.tzinfo is None:
            time_to = time_to.replace(tzinfo=timezone.utc)

        sh_bbox = SHBBox(bbox=list(bbox), crs=CRS.WGS84)
        size = bbox_to_dimensions(sh_bbox, resolution=self.resolution_m)
        # Cap dimensions to avoid blowing past the Process API per-request size limit.
        size = (min(size[0], 2500), min(size[1], 2500))

        request = SentinelHubRequest(
            evalscript=EVALSCRIPT_SAR,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL1_IW.define_from(
                        "s1iw_dataspace",
                        service_url=self._sh_config.sh_base_url,
                    ),
                    time_interval=(time_from.isoformat(), time_to.isoformat()),
                )
            ],
            responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
            bbox=sh_bbox,
            size=size,
            config=self._sh_config,
        )

        data = request.get_data()
        if not data:
            return None, {"tile_id": str(uuid.uuid4()), "size": size}

        arr = np.asarray(data[0], dtype=np.float32)
        # Some responses return all-zero on no-data; treat that as missing.
        if not np.any(np.isfinite(arr)) or arr.max() == 0.0:
            return None, {"tile_id": str(uuid.uuid4()), "size": size}

        meta = {
            "tile_id": str(uuid.uuid4()),
            "size": list(arr.shape),
            "bbox": list(bbox),
            "time_from": time_from.isoformat(),
            "time_to": time_to.isoformat(),
            "data_collection": "SENTINEL1_IW_VV_VH",
        }
        return arr, meta

    @staticmethod
    def _save_preview(vv_db: np.ndarray, detections: list[CFARDetection], path: Path) -> None:
        """Render an 8-bit PNG of the VV tile with red boxes around detections.

        Uses opencv-python (already a dependency). Stretching is min-max clipped to [-25, 0] dB
        which matches typical Sentinel-1 sea backscatter dynamic range.
        """
        import cv2

        # Replace NaN/inf with the floor so the uint8 cast is well-defined.
        safe = np.nan_to_num(vv_db, nan=-25.0, posinf=0.0, neginf=-25.0)
        clipped = np.clip(safe, -25.0, 0.0)
        norm = ((clipped + 25.0) / 25.0 * 255.0).astype(np.uint8)
        bgr = cv2.cvtColor(norm, cv2.COLOR_GRAY2BGR)
        for d in detections:
            rmin, cmin, rmax, cmax = d.bbox_pixels
            # Pad by 6 px so single-pixel hits render visibly.
            cv2.rectangle(bgr, (cmin - 6, rmin - 6), (cmax + 6, rmax + 6),
                          color=(0, 0, 255), thickness=1)
        cv2.imwrite(str(path), bgr)
