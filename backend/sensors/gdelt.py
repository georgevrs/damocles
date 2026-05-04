"""GDELT 2.0 events sensor.

Fetches the public 15-minute event drops from
``http://data.gdeltproject.org/gdeltv2/``, filters by time window, country
codes, and CAMEO event codes, and emits ``NewsEvent`` objects ready for
graph ingestion.

GDELT 2.0 schema reminders
--------------------------
Each ``*.export.CSV.zip`` contains one TSV with **61 fields per row, no header**.
Field offsets used here (0-based):

    1   SQLDATE              YYYYMMDD
    7   Actor1CountryCode    CAMEO code, mostly ISO 3166-1 alpha-3 (Greece=GRC, Turkey=TUR)
    17  Actor2CountryCode    CAMEO code (same scheme)
    26  EventCode            CAMEO event code (4-digit)
    27  EventBaseCode        CAMEO base
    28  EventRootCode        CAMEO root (2-digit)
    30  GoldsteinScale       -10..+10, conflict intensity
    31  NumMentions
    33  NumArticles
    34  AvgTone
    51  ActionGeo_Type
    52  ActionGeo_FullName
    53  ActionGeo_CountryCode  FIPS 10-4 (Greece=GR, Turkey=TU) — different scheme to fields 7/17!
    54  ActionGeo_ADM1Code
    55  ActionGeo_ADM2Code     v2-only addition; off-by-one trap if you used v1 docs
    56  ActionGeo_Lat          float, may be empty
    57  ActionGeo_Long         float, may be empty
    58  ActionGeo_FeatureID
    59  DATEADDED              YYYYMMDDHHMMSS
    60  SOURCEURL

Master file format (``masterfilelist.txt``):

    <size> <sha1> <url>\\n

URLs come in three flavors per 15-min slot — ``*.export.CSV.zip`` (events),
``*.mentions.CSV.zip`` (mentions), ``*.gkg.csv.zip`` (knowledge graph).
We pull the events table only.

Caching
-------
The master file is ~123 MB and gains one line per 15 min. We cache it under
``data/cache/gdelt/masterfilelist.txt`` and re-fetch when the cached copy is
older than ``master_ttl_minutes`` (default 60).
"""
from __future__ import annotations

import io
import logging
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx

from backend.config import settings
from backend.models.event import NewsEvent
from backend.store.cache import CachedSensorMixin

from .base import BaseSensor, BBox, SensorResult

log = logging.getLogger(__name__)

MASTER_FILE_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"

# CAMEO root codes that are "interesting" by default (conflict / coercion / military).
# Full reference: http://data.gdeltproject.org/documentation/CAMEO.Manual.1.1b3.pdf
DEFAULT_THREAT_CAMEO_ROOTS: tuple[str, ...] = (
    "11",  # Disapprove
    "12",  # Reject
    "13",  # Threaten
    "14",  # Protest
    "15",  # Exhibit force posture
    "16",  # Reduce relations
    "17",  # Coerce (sanctions, blockades)
    "18",  # Assault
    "19",  # Fight
    "20",  # Use unconventional mass violence
)

# Country code matching is dual-scheme:
#   - Actor1/2CountryCode (fields 7, 17) use CAMEO codes — largely ISO 3166-1 alpha-3.
#   - ActionGeo_CountryCode (field 53) uses FIPS 10-4 (different).
# We accept either representation in a single set so the row passes if any of the
# three fields contains a country we care about.
DEFAULT_ACTOR_COUNTRIES: tuple[str, ...] = (
    "GRC", "TUR", "CYP",          # CAMEO / ISO alpha-3 — matches Actor1CountryCode / Actor2CountryCode
    "GR",  "TU",  "CY",           # FIPS 10-4 — matches ActionGeo_CountryCode
)


def _parse_int(s: str) -> int | None:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_float(s: str) -> float | None:
    s = s.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_sqldate(s: str) -> datetime | None:
    """SQLDATE is YYYYMMDD; DATEADDED is YYYYMMDDHHMMSS. Try both."""
    s = s.strip()
    if len(s) == 8:
        try:
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    if len(s) == 14:
        try:
            return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def parse_event_row(
    row: list[str],
    *,
    actor_countries: Iterable[str] | None = None,
    cameo_roots: Iterable[str] | None = None,
    bbox: BBox | None = None,
) -> NewsEvent | None:
    """Convert one TSV row to a NewsEvent, applying inline filters.

    Returns ``None`` when the row should be dropped (wrong country, wrong
    event class, no geocoding, malformed numerics).
    """
    if len(row) < 61:
        return None  # GDELT 2.0 events table has exactly 61 fields

    # Country filter — match either Actor1 or Actor2 country code (FIPS 10-4)
    if actor_countries:
        countries = set(actor_countries)
        a1 = (row[7] or "").strip().upper()
        a2 = (row[17] or "").strip().upper()
        ageo = (row[53] or "").strip().upper()
        if not (a1 in countries or a2 in countries or ageo in countries):
            return None

    # CAMEO root filter (event family)
    if cameo_roots:
        root = (row[28] or "").strip()
        if root not in set(cameo_roots):
            return None

    # Geo: skip events without lat/lon (GDELT 2.0 lat=field 56, long=field 57)
    lat = _parse_float(row[56])
    lon = _parse_float(row[57])
    if lat is None or lon is None:
        return None
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            return None

    # Use DATEADDED (more precise) when present, fall back to SQLDATE
    timestamp = _parse_sqldate(row[59]) or _parse_sqldate(row[1])
    if timestamp is None:
        return None

    event_id = (row[0] or "").strip()
    cameo_code = (row[26] or "").strip()
    goldstein = _parse_float(row[30]) or 0.0
    mentions = _parse_int(row[31]) or 1
    source_url = (row[60] or "").strip()
    headline = source_url.split("/")[-1] or source_url[:140]

    return NewsEvent(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, event_id or source_url or str(uuid.uuid4()))),
        source_url=source_url,
        source_name=_extract_source_name(source_url),
        headline=headline,
        timestamp=timestamp,
        lat=lat,
        lon=lon,
        goldstein_scale=goldstein,
        cameo_code=cameo_code,
        language="en",     # GDELT 2.0 events are extracted from English-translated articles
        mentions=mentions,
    )


def _extract_source_name(url: str) -> str:
    """Tiny domain extractor — avoids pulling in tldextract."""
    if not url:
        return "gdelt"
    s = url.split("//", 1)[-1]
    s = s.split("/", 1)[0]
    s = s.split(":", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s or "gdelt"


def parse_master_file(text: str, time_from: datetime, time_to: datetime) -> list[str]:
    """Return the .export.CSV.zip URLs whose 15-min slot lies in the window."""
    fmt_from = time_from.strftime("%Y%m%d%H%M%S")
    fmt_to = time_to.strftime("%Y%m%d%H%M%S")
    out: list[str] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        url = parts[2]
        if not url.endswith(".export.CSV.zip"):
            continue
        # The slot timestamp is the leaf filename's first 14 digits.
        leaf = url.rsplit("/", 1)[-1]
        slot = leaf[:14]
        if not slot.isdigit():
            continue
        if fmt_from <= slot <= fmt_to:
            out.append(url)
    return out


class GDELTSensor(CachedSensorMixin, BaseSensor[NewsEvent]):
    name = "gdelt"
    cache_kind = "news"

    def __init__(
        self,
        actor_countries: Iterable[str] | None = None,
        cameo_roots: Iterable[str] | None = None,
        cache_dir: Path | None = None,
        master_ttl_minutes: int = 60,
        max_slots: int = 96,           # cap fetches; 96 = one full day at 15-min cadence
        http_timeout_s: float = 30.0,
    ):
        self.actor_countries = tuple(actor_countries) if actor_countries else DEFAULT_ACTOR_COUNTRIES
        self.cameo_roots = tuple(cameo_roots) if cameo_roots else DEFAULT_THREAT_CAMEO_ROOTS
        self.cache_dir = cache_dir or (settings.cache_dir / "gdelt")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.master_ttl_minutes = master_ttl_minutes
        self.max_slots = max_slots
        self.http_timeout_s = http_timeout_s
        self.cache_ttl_seconds = settings.CACHE_TTL_GDELT

    async def fetch(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime,
        **kwargs,
    ) -> SensorResult[NewsEvent]:
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
    ) -> SensorResult[NewsEvent]:
        start = time.time()

        master_text = await self._get_master_file()
        slot_urls = parse_master_file(master_text, time_from, time_to)
        if len(slot_urls) > self.max_slots:
            log.info("GDELT: capping %d slots to %d most recent", len(slot_urls), self.max_slots)
            slot_urls = slot_urls[-self.max_slots:]

        log.info("GDELT: fetching %d 15-min slots", len(slot_urls))

        events: list[NewsEvent] = []
        bytes_downloaded = 0
        async with httpx.AsyncClient(timeout=self.http_timeout_s) as http:
            for url in slot_urls:
                try:
                    payload = await http.get(url)
                    if payload.status_code != 200:
                        log.debug("GDELT slot %s: HTTP %d", url, payload.status_code)
                        continue
                    bytes_downloaded += len(payload.content)
                    events.extend(self._parse_zip(payload.content, bbox))
                except httpx.HTTPError as exc:
                    log.warning("GDELT slot %s: %s", url, exc)
                    continue

        return SensorResult(
            sensor_name=self.name,
            events=events,
            bbox=bbox,
            time_from=time_from,
            time_to=time_to,
            metadata={
                "slots_fetched":     len(slot_urls),
                "bytes_downloaded":  bytes_downloaded,
                "actor_countries":   list(self.actor_countries),
                "cameo_roots":       list(self.cameo_roots),
            },
            duration_ms=(time.time() - start) * 1000,
        )

    # ─── internals ───────────────────────────────────────────────────────────
    async def _get_master_file(self) -> str:
        path = self.cache_dir / "masterfilelist.txt"
        if path.exists():
            age_min = (time.time() - path.stat().st_mtime) / 60
            if age_min < self.master_ttl_minutes:
                return path.read_text(encoding="utf-8", errors="replace")
        log.info("GDELT: refreshing master file index (~123 MB)")
        async with httpx.AsyncClient(timeout=120.0) as http:
            r = await http.get(MASTER_FILE_URL)
            r.raise_for_status()
            text = r.text
        path.write_text(text, encoding="utf-8")
        return text

    def _parse_zip(self, content: bytes, bbox: BBox | None) -> list[NewsEvent]:
        events: list[NewsEvent] = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            log.warning("GDELT slot returned non-ZIP payload")
            return []
        for name in zf.namelist():
            if not name.endswith(".CSV"):
                continue
            with zf.open(name) as fh:
                for raw in fh:
                    line = raw.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                    if not line:
                        continue
                    row = line.split("\t")
                    ev = parse_event_row(
                        row,
                        actor_countries=self.actor_countries,
                        cameo_roots=self.cameo_roots,
                        bbox=bbox,
                    )
                    if ev is not None:
                        events.append(ev)
        return events
