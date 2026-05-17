"""Download real satellite images into data/satellite_intel/<source>/images/

Three sources — all free, no API key:

  Sentinel-2 optical  →  AWS S3 public COGs (thumbnail JPG + windowed TCI crop PNG)
  Sentinel-1 SAR      →  Microsoft Planetary Computer rendered PNG
  Landsat-9           →  Microsoft Planetary Computer rendered PNG (RGB + thermal)

Usage:
    .venv/bin/python scripts/download_satellite_images.py
"""
from __future__ import annotations

import json
import os
import struct
import zlib
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
import numpy as np

BASE     = Path("data/satellite_intel")
UA       = "Damocles/1.0 (sovereign-intel-hackathon)"
TIMEOUT  = 60

BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
AMBER = "\033[93m"
RED   = "\033[91m"
RESET = "\033[0m"


# ── tiny PNG writer (no Pillow / opencv needed) ───────────────────────────────

def _write_png(path: Path, rgb: np.ndarray) -> None:
    """Write an (H, W, 3) uint8 array as a valid PNG file without Pillow."""
    h, w = rgb.shape[:2]

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    rows = b""
    for row in rgb:
        rows += b"\x00" + row.tobytes()

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


# ── generic download ──────────────────────────────────────────────────────────

def download_binary(url: str, dest: Path, label: str) -> bool:
    """Download URL to dest. Returns True on success."""
    try:
        with httpx.stream("GET", url, headers={"User-Agent": UA},
                          follow_redirects=True, timeout=TIMEOUT) as r:
            r.raise_for_status()
            content_type = r.headers.get("content-type", "")
            if "text/html" in content_type:
                print(f"    {AMBER}[SKIP]{RESET} {label} — auth wall")
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        size_kb = dest.stat().st_size // 1024
        print(f"    {GREEN}✓{RESET} {label} ({size_kb} KB) → {dest.name}")
        return True
    except Exception as exc:
        print(f"    {AMBER}[WARN]{RESET} {label} — {exc}")
        return False


# ── windowed COG crop (Sentinel-2 TCI) ───────────────────────────────────────

def download_s2_cog_crop(
    tci_url: str,
    dest: Path,
    label: str,
    bbox: tuple[float, float, float, float] = (22.0, 36.0, 28.0, 41.0),
) -> bool:
    """
    Read a windowed portion of a Cloud-Optimized GeoTIFF hosted on S3.
    Uses rasterio (already in pyproject.toml) — no full-file download needed.
    Crops to bbox and saves as PNG.
    """
    try:
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.windows import from_bounds as window_from_bounds

        with rasterio.open(tci_url) as src:
            win = window_from_bounds(*bbox, transform=src.transform)
            # Clamp to actual image bounds
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            if win.width < 10 or win.height < 10:
                print(f"    {AMBER}[SKIP]{RESET} {label} — bbox outside scene footprint")
                return False

            # Read at reduced resolution to keep file size sane (~512px wide)
            out_w = min(int(win.width), 512)
            out_h = int(win.height * out_w / win.width)
            data = src.read([1, 2, 3], window=win, out_shape=(3, out_h, out_w))

        # data shape: (3, H, W) — already uint8 for TCI
        rgb = np.moveaxis(data, 0, -1)
        if rgb.dtype != np.uint8:
            rgb = np.clip(rgb / rgb.max() * 255, 0, 255).astype(np.uint8)

        dest.parent.mkdir(parents=True, exist_ok=True)
        _write_png(dest, rgb)
        size_kb = dest.stat().st_size // 1024
        print(f"    {GREEN}✓{RESET} {label} crop ({out_w}×{out_h}px, {size_kb} KB) → {dest.name}")
        return True

    except ImportError:
        print(f"    {AMBER}[SKIP]{RESET} rasterio not available for COG crop")
        return False
    except Exception as exc:
        print(f"    {AMBER}[WARN]{RESET} {label} COG crop — {exc}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 01  SENTINEL-2 OPTICAL
# ══════════════════════════════════════════════════════════════════════════════

def download_sentinel2(max_scenes: int = 5) -> None:
    print(f"\n{CYAN}{BOLD}━━━  01 · Sentinel-2 Optical  ━━━{RESET}")
    data = json.load(open(BASE / "01_sentinel2_optical/aegean_scenes.json"))
    items: list[dict] = data["items"]

    # Pick scenes with lowest cloud cover
    items_sorted = sorted(items, key=lambda x: x.get("cloud_cover_%", 100))
    selected = items_sorted[:max_scenes]
    print(f"  Downloading {len(selected)} clearest scenes (of {len(items)} total)")

    img_dir = BASE / "01_sentinel2_optical/images"
    manifest: list[dict] = []

    for item in selected:
        scene_id   = item["id"]
        date       = (item.get("datetime") or "")[:10]
        cloud      = item.get("cloud_cover_%", "?")
        thumb_url  = item.get("thumbnail_url")
        tci_url    = item.get("true_color_url")

        print(f"\n  [{date}] {scene_id}  cloud={cloud}%")

        record: dict[str, Any] = {"id": scene_id, "date": date,
                                   "cloud_cover_%": cloud, "files": {}}

        # 1. Thumbnail JPG (fast, ~11 KB)
        if thumb_url:
            dest = img_dir / f"{scene_id}_thumbnail.jpg"
            if not dest.exists():
                ok = download_binary(thumb_url, dest, "thumbnail JPG")
            else:
                print(f"    {GREEN}✓{RESET} thumbnail already exists → {dest.name}")
                ok = True
            if ok:
                record["files"]["thumbnail_jpg"] = str(dest)

        # 2. TCI True Colour COG crop — windowed read (no full download)
        if tci_url:
            dest_png = img_dir / f"{scene_id}_TCI_aegean_crop.png"
            if not dest_png.exists():
                ok = download_s2_cog_crop(tci_url, dest_png, "TCI crop")
            else:
                print(f"    {GREEN}✓{RESET} TCI crop already exists → {dest_png.name}")
                ok = True
            if ok:
                record["files"]["tci_crop_png"] = str(dest_png)

        manifest.append(record)

    # Save manifest
    manifest_path = BASE / "01_sentinel2_optical/images/manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"total_downloaded": len(manifest), "scenes": manifest},
                  f, indent=2, default=str)
    print(f"\n  Manifest → {manifest_path}")


# ══════════════════════════════════════════════════════════════════════════════
# 02  SENTINEL-1 SAR
# ══════════════════════════════════════════════════════════════════════════════

def download_sentinel1(max_scenes: int = 5) -> None:
    print(f"\n{CYAN}{BOLD}━━━  02 · Sentinel-1 SAR  ━━━{RESET}")
    data = json.load(open(BASE / "02_sentinel1_sar/aegean_sar_scenes.json"))

    img_dir = BASE / "02_sentinel1_sar/images"
    manifest: list[dict] = []

    for collection_key, label in [("rtc_items", "RTC"), ("grd_items", "GRD")]:
        items = data.get(collection_key, [])[:max_scenes]
        print(f"\n  {label} — downloading {len(items)} scenes")

        for item in items:
            scene_id    = item["id"]
            date        = (item.get("datetime") or "")[:10]
            orbit       = item.get("orbit_state", "")
            preview_url = item.get("preview_url")

            print(f"\n  [{date}] {scene_id[:50]}  orbit={orbit}")

            record: dict[str, Any] = {"id": scene_id, "date": date,
                                       "orbit": orbit, "type": label, "files": {}}

            if preview_url:
                safe_id = scene_id.replace("/", "_")[:80]
                dest = img_dir / f"{safe_id}_{label}_preview.png"
                if not dest.exists():
                    ok = download_binary(preview_url, dest, f"SAR {label} preview PNG")
                else:
                    print(f"    {GREEN}✓{RESET} already exists → {dest.name}")
                    ok = True
                if ok:
                    record["files"]["sar_preview_png"] = str(dest)

            manifest.append(record)

    manifest_path = BASE / "02_sentinel1_sar/images/manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"total_downloaded": len(manifest), "scenes": manifest},
                  f, indent=2, default=str)
    print(f"\n  Manifest → {manifest_path}")


# ══════════════════════════════════════════════════════════════════════════════
# 03  LANDSAT-9
# ══════════════════════════════════════════════════════════════════════════════

def _build_landsat_preview_url(scene_id: str) -> str | None:
    """Build Planetary Computer rendered_preview URL for a Landsat scene."""
    # Re-query PC for the item to get the actual preview URL
    try:
        r = httpx.get(
            f"https://planetarycomputer.microsoft.com/api/stac/v1"
            f"/collections/landsat-c2-l2/items/{scene_id}",
            headers={"User-Agent": UA}, timeout=15,
        )
        if r.status_code == 200:
            assets = r.json().get("assets", {})
            return assets.get("rendered_preview", {}).get("href")
    except Exception:
        pass
    return None


def download_landsat(max_scenes: int = 5) -> None:
    print(f"\n{CYAN}{BOLD}━━━  03 · Landsat-9  ━━━{RESET}")
    data = json.load(open(BASE / "03_landsat9/greece_scenes.json"))
    items = sorted(data["items"], key=lambda x: x.get("cloud_cover_%", 100))[:max_scenes]
    print(f"  Downloading {len(items)} clearest scenes")

    img_dir = BASE / "03_landsat9/images"
    manifest: list[dict] = []

    # Also get scenes from Planetary Computer (they have thermal previews)
    pc_items_raw = httpx.get(
        "https://planetarycomputer.microsoft.com/api/stac/v1/collections/landsat-c2-l2/items",
        params={"bbox": "22.0,37.0,28.0,42.0", "limit": max_scenes,
                "datetime": "2026-04-01T00:00:00Z/2026-05-12T23:59:59Z"},
        headers={"User-Agent": UA}, timeout=20,
    ).json().get("features", [])

    print(f"  Found {len(pc_items_raw)} PC Landsat items")

    for f in pc_items_raw[:max_scenes]:
        scene_id   = f["id"]
        props      = f["properties"]
        date       = (props.get("datetime") or "")[:10]
        cloud      = round(props.get("eo:cloud_cover", 0), 1)
        assets     = f.get("assets", {})
        preview_url = assets.get("rendered_preview", {}).get("href")

        print(f"\n  [{date}] {scene_id}  cloud={cloud}%")
        record: dict[str, Any] = {"id": scene_id, "date": date,
                                   "cloud_cover_%": cloud, "files": {}}

        if preview_url:
            dest_rgb = img_dir / f"{scene_id}_RGB_preview.png"
            if not dest_rgb.exists():
                ok = download_binary(preview_url, dest_rgb, "Landsat RGB preview")
            else:
                print(f"    {GREEN}✓{RESET} RGB preview already exists → {dest_rgb.name}")
                ok = True
            if ok:
                record["files"]["rgb_preview_png"] = str(dest_rgb)

        # Thermal band preview — rebuild URL with lwir11 band
        if preview_url:
            thermal_url = (
                f"https://planetarycomputer.microsoft.com/api/data/v1/item/preview.png"
                f"?collection=landsat-c2-l2&item={scene_id}"
                f"&assets=lwir11&colormap_name=hot&rescale=200,350&format=png"
            )
            dest_tir = img_dir / f"{scene_id}_thermal_preview.png"
            if not dest_tir.exists():
                ok = download_binary(thermal_url, dest_tir, "Landsat thermal (TIRS) preview")
            else:
                print(f"    {GREEN}✓{RESET} thermal already exists → {dest_tir.name}")
                ok = True
            if ok:
                record["files"]["thermal_tirs_png"] = str(dest_tir)

        manifest.append(record)

    manifest_path = BASE / "03_landsat9/images/manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({"total_downloaded": len(manifest), "scenes": manifest},
                  f, indent=2, default=str)
    print(f"\n  Manifest → {manifest_path}")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

def print_summary() -> None:
    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  Downloaded images summary{RESET}")
    print(f"{BOLD}{'═'*65}{RESET}")

    total_files = 0
    total_bytes = 0

    for folder in ["01_sentinel2_optical", "02_sentinel1_sar", "03_landsat9"]:
        img_dir = BASE / folder / "images"
        if not img_dir.exists():
            continue
        files = list(img_dir.glob("*"))
        files = [f for f in files if f.suffix in (".jpg", ".jpeg", ".png", ".tif")]
        size  = sum(f.stat().st_size for f in files)
        total_files += len(files)
        total_bytes += size
        print(f"  {folder}/images/  →  {len(files)} images  ({size//1024} KB)")
        for img in sorted(files):
            print(f"    {img.name}")

    print(f"\n  Total: {total_files} images, {total_bytes//1024} KB")
    print(f"\n  {GREEN}{BOLD}All images ready for Damocles demo.{RESET}")
    print(f"  Open any PNG/JPG directly to view real satellite imagery.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  DAMOCLES — Satellite Image Downloader{RESET}")
    print(f"{BOLD}{'═'*65}{RESET}")
    print(f"  Output : {BASE.resolve()}/*/images/")

    download_sentinel2(max_scenes=5)
    download_sentinel1(max_scenes=3)
    download_landsat(max_scenes=5)
    print_summary()


if __name__ == "__main__":
    main()
