"""Link preview endpoint.

GET /api/preview?url=...  → { url, title, image, description, source }

Fetches the target URL once, parses Open Graph tags, caches the result
(disk-keyed by url-hash so re-loads are instant). Used by news cards in
the BriefPanel AoI drill-down to show a thumbnail + title.

Sovereign caveat: the fetch *does* leave Greek infrastructure to hit the
news article's host. That's the whole point of GDELT — the events point
at remote articles. We honour the previously-stored `source_url`; we do
not invent URLs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query

from backend.config import settings

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preview", tags=["preview"])

CACHE_DIR = settings.cache_dir / "previews"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 1 day: news previews don't change often, but they DO get pulled / paywalled.
CACHE_TTL_S = 24 * 3600


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / f"{h}.json"


def _read_cache(url: str) -> dict[str, Any] | None:
    p = _cache_path(url)
    if not p.exists():
        return None
    try:
        import time
        if time.time() - p.stat().st_mtime > CACHE_TTL_S:
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_cache(url: str, data: dict[str, Any]) -> None:
    try:
        _cache_path(url).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("preview cache write failed: %s", exc)


# Tight regex pass over the head — full HTML parsing isn't worth pulling in
# BeautifulSoup for ~200 bytes of metadata.
_RE_OG = re.compile(
    r'<meta[^>]*?(?:property|name)=["\'](og:[a-z:]+|twitter:[a-z:]+|description)["\'][^>]*?content=["\']([^"\']{1,500})["\']',
    re.IGNORECASE,
)
_RE_TITLE = re.compile(r"<title[^>]*>([^<]{1,300})</title>", re.IGNORECASE | re.DOTALL)


def _parse_html_head(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    head_end = html.lower().find("</head>")
    head = html[: head_end + 7] if head_end > 0 else html[:8192]
    for m in _RE_OG.finditer(head):
        out[m.group(1).lower()] = m.group(2).strip()
    if "title" not in out:
        mt = _RE_TITLE.search(head)
        if mt:
            out["title"] = mt.group(1).strip()
    return out


@router.get("")
async def preview(url: str = Query(..., min_length=8, max_length=2048)) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="invalid url scheme")

    cached = _read_cache(url)
    if cached is not None:
        return cached

    headers = {
        "User-Agent": "DamoclesPreviewBot/1.0 (+https://damocles.gr)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(
            timeout=8.0, follow_redirects=True, headers=headers,
        ) as http:
            r = await http.get(url)
            ct = r.headers.get("content-type", "")
            if "html" not in ct:
                data = {"url": url, "title": None, "image": None, "description": None,
                        "source": parsed.netloc, "ok": False, "reason": f"content-type={ct}"}
                _write_cache(url, data)
                return data
            text = r.text[:65_536]
    except Exception as exc:
        data = {"url": url, "title": None, "image": None, "description": None,
                "source": parsed.netloc, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        _write_cache(url, data)
        return data

    head = _parse_html_head(text)
    title = head.get("og:title") or head.get("twitter:title") or head.get("title")
    image = head.get("og:image") or head.get("twitter:image")
    desc  = head.get("og:description") or head.get("twitter:description") or head.get("description")
    site  = head.get("og:site_name") or parsed.netloc

    # Resolve relative og:image
    if image and image.startswith("//"):
        image = parsed.scheme + ":" + image
    elif image and image.startswith("/"):
        image = f"{parsed.scheme}://{parsed.netloc}{image}"

    data = {
        "url":         url,
        "title":       (title or "").strip()[:240] or None,
        "image":       image,
        "description": (desc or "").strip()[:400] or None,
        "source":      site,
        "ok":          True,
    }
    _write_cache(url, data)
    return data
