"""GDELT TSV parser unit tests.

Covers field parsing, country/CAMEO/bbox/geo filters, malformed rows, and the
master-file slot-range filter. No network — synthetic strings only.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.sensors.gdelt import (
    DEFAULT_ACTOR_COUNTRIES,
    DEFAULT_THREAT_CAMEO_ROOTS,
    parse_event_row,
    parse_master_file,
)


def _build_row(**overrides: str) -> list[str]:
    """Build a 61-field GDELT 2.0 row with sensible Greece-Turkey defaults.

    Field offsets reference GDELT 2.0 events schema (61 fields). ActionGeo
    Lat/Long are at 56/57, NOT 55/56 — v2 added ADM2Code fields throughout
    the geography blocks.
    """
    row = [""] * 61
    row[0] = "1"                      # GLOBALEVENTID
    row[1] = "20240317"               # SQLDATE
    row[7] = "GR"                     # Actor1CountryCode (test uses FIPS; real data is ISO alpha-3)
    row[17] = "TU"                    # Actor2CountryCode
    row[26] = "1822"                  # EventCode (CAMEO)
    row[28] = "18"                    # EventRootCode (Assault root)
    row[30] = "-7.5"                  # GoldsteinScale
    row[31] = "8"                     # NumMentions
    row[53] = "GR"                    # ActionGeo_CountryCode (FIPS)
    row[56] = "37.5"                  # ActionGeo_Lat   (v2 offset)
    row[57] = "25.5"                  # ActionGeo_Long  (v2 offset)
    row[59] = "20240317143000"        # DATEADDED
    row[60] = "https://example.gr/news/aegean-incident"
    for k, v in overrides.items():
        row[int(k)] = v               # type: ignore[index]
    return row


# ───────────────────────────────────────────────────────────────────────────────
# Happy path
# ───────────────────────────────────────────────────────────────────────────────
def test_parses_complete_row():
    row = _build_row()
    ev = parse_event_row(row, actor_countries=DEFAULT_ACTOR_COUNTRIES,
                         cameo_roots=DEFAULT_THREAT_CAMEO_ROOTS)

    assert ev is not None
    assert ev.lat == 37.5
    assert ev.lon == 25.5
    assert ev.cameo_code == "1822"
    assert ev.goldstein_scale == -7.5
    assert ev.mentions == 8
    assert ev.source_name == "example.gr"
    assert ev.timestamp == datetime(2024, 3, 17, 14, 30, 0, tzinfo=timezone.utc)


def test_falls_back_to_sqldate_when_dateadded_missing():
    row = _build_row()
    row[59] = ""   # DATEADDED missing
    ev = parse_event_row(row, actor_countries=DEFAULT_ACTOR_COUNTRIES,
                         cameo_roots=DEFAULT_THREAT_CAMEO_ROOTS)
    assert ev is not None
    assert ev.timestamp == datetime(2024, 3, 17, tzinfo=timezone.utc)


# ───────────────────────────────────────────────────────────────────────────────
# Filters
# ───────────────────────────────────────────────────────────────────────────────
def test_country_filter_drops_unrelated_actors():
    row = _build_row()
    row[7] = "RS"   # Russia
    row[17] = "US"
    row[53] = "RS"
    assert parse_event_row(row, actor_countries={"GR", "TU"}) is None


def test_country_filter_passes_when_either_actor_matches():
    row = _build_row()
    row[7] = "GM"   # Germany
    row[17] = "TU"  # Turkey — should match
    row[53] = "GM"
    ev = parse_event_row(row, actor_countries={"GR", "TU"})
    assert ev is not None


def test_cameo_root_filter():
    row = _build_row()
    row[28] = "01"   # "Make public statement" — not a threat root
    assert parse_event_row(row, cameo_roots=DEFAULT_THREAT_CAMEO_ROOTS) is None


def test_bbox_filter_drops_outside_geo():
    row = _build_row()
    row[56] = "60.0"   # ActionGeo_Lat — well north of Aegean
    row[57] = "30.0"   # ActionGeo_Long
    aegean = (22.0, 35.0, 28.0, 42.0)
    assert parse_event_row(row, bbox=aegean) is None


def test_bbox_filter_passes_inside_geo():
    row = _build_row()
    aegean = (22.0, 35.0, 28.0, 42.0)
    ev = parse_event_row(row, bbox=aegean)
    assert ev is not None
    assert ev.lat == 37.5


# ───────────────────────────────────────────────────────────────────────────────
# Defensive parsing
# ───────────────────────────────────────────────────────────────────────────────
def test_drops_row_without_geocoding():
    row = _build_row()
    row[56] = ""   # lat blank
    row[57] = ""   # long blank
    assert parse_event_row(row) is None


def test_drops_malformed_short_row():
    short_row = ["", "", ""]   # only 3 fields
    assert parse_event_row(short_row) is None


def test_handles_empty_numeric_fields():
    row = _build_row()
    row[30] = ""    # GoldsteinScale missing
    row[31] = ""    # mentions missing
    ev = parse_event_row(row)
    assert ev is not None
    assert ev.goldstein_scale == 0.0
    assert ev.mentions == 1


def test_dedupes_event_id_via_uuid5():
    row1 = _build_row()
    row2 = _build_row()
    e1 = parse_event_row(row1)
    e2 = parse_event_row(row2)
    assert e1 is not None and e2 is not None
    assert e1.id == e2.id    # deterministic ID for same source URL/event ID


# ───────────────────────────────────────────────────────────────────────────────
# Master-file slot filter
# ───────────────────────────────────────────────────────────────────────────────
def test_master_file_filter_includes_only_window():
    text = (
        "1234 abc http://data.gdeltproject.org/gdeltv2/20240317120000.export.CSV.zip\n"
        "1234 abc http://data.gdeltproject.org/gdeltv2/20240317121500.export.CSV.zip\n"
        "1234 abc http://data.gdeltproject.org/gdeltv2/20240317123000.export.CSV.zip\n"
        "1234 abc http://data.gdeltproject.org/gdeltv2/20240317120000.mentions.CSV.zip\n"  # wrong type
        "1234 abc http://data.gdeltproject.org/gdeltv2/20240315000000.export.CSV.zip\n"     # before window
        "1234 abc http://data.gdeltproject.org/gdeltv2/20240319000000.export.CSV.zip\n"     # after window
    )
    t_from = datetime(2024, 3, 17, 12, 15, tzinfo=timezone.utc)
    t_to   = datetime(2024, 3, 17, 12, 30, tzinfo=timezone.utc)
    urls = parse_master_file(text, t_from, t_to)
    assert len(urls) == 2
    assert all(".export.CSV.zip" in u for u in urls)
    assert all("20240317" in u for u in urls)
