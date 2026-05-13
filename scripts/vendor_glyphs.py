"""W3-T3 — vendor MapLibre glyph PBFs so the demo doesn't depend on a CDN.

The map's only text layer is the AoI label (see ``MapPanel.tsx::aoiLabel``)
which uses fontstack ``Open Sans Regular,Arial Unicode MS Regular``. The
upstream PBFs live at::

    https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf

(The dark-matter ``style.json`` references that host directly, which is why
the upstream ``basemaps.cartocdn.com/gl/.../glyphs`` URL 404s — that path
never existed.)

Each ``range`` covers 256 Unicode codepoints (``0-255``, ``256-511``, …).
For the demo we only need:

  * 0-255      Latin Basic (English copy)
  * 256-511    Latin Extended-A (Greek transliterations)
  * 512-767    Latin Extended-B / IPA
  * 768-1023   Greek + Coptic (Νέα Σμύρνη, Σύνταγμα, Ηράκλειο, etc.)
  * 8192-8447  General Punctuation (em-dash, en-dash, ellipsis)

Output: ``frontend/public/maplibre-glyphs/Open Sans Regular,Arial Unicode MS Regular/{range}.pbf``

Run once. The pitch-day box gets the resulting ``public/maplibre-glyphs``
folder shipped in the Vite build, so wifi-dies is a non-event for labels.
"""
from __future__ import annotations

import gzip
import sys
import urllib.parse
import urllib.request
from pathlib import Path

FONTSTACK = "Open Sans Regular,Arial Unicode MS Regular"
RANGES = ["0-255", "256-511", "512-767", "768-1023", "8192-8447"]
UPSTREAM = "https://tiles.basemaps.cartocdn.com/fonts"

ROOT = Path(__file__).resolve().parent.parent
OUT  = ROOT / "frontend" / "public" / "maplibre-glyphs" / FONTSTACK


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    encoded_fontstack = urllib.parse.quote(FONTSTACK, safe=",")

    downloaded, skipped, failed = 0, 0, 0
    for rng in RANGES:
        dst = OUT / f"{rng}.pbf"
        if dst.exists() and dst.stat().st_size > 0:
            print(f"  skip   {rng}.pbf  ({dst.stat().st_size} bytes)")
            skipped += 1
            continue
        url = f"{UPSTREAM}/{encoded_fontstack}/{rng}.pbf"
        try:
            req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                encoding = r.headers.get("Content-Encoding", "")
            # CARTO sends pre-gzipped PBFs with Content-Encoding: gzip. urllib
            # does NOT auto-decompress, so writing the bytes verbatim leaves
            # a gzip-wrapped file on disk. The Vite static server then serves
            # it without a Content-Encoding header, and MapLibre's PBF parser
            # throws "Unimplemented type: 7" trying to read the gzip magic
            # as protobuf wire types. Decompress here so the on-disk file is
            # a real PBF that any static server can hand to the browser.
            if encoding == "gzip" or data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            dst.write_bytes(data)
            print(f"  saved  {rng}.pbf  ({len(data)} bytes)  <- {url}")
            downloaded += 1
        except Exception as exc:
            print(f"  FAIL   {rng}.pbf  {type(exc).__name__}: {exc}")
            failed += 1

    print()
    print(f"  downloaded={downloaded} skipped={skipped} failed={failed}")
    print(f"  -> {OUT.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
