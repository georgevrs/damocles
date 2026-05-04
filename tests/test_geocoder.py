"""Geocoder unit tests.

Verifies the Aegean gazetteer matcher across:
  - English place names (trivial)
  - Greek with monotonic tonos vs uppercase-no-tonos (the same diacritic
    issue we caught on Day 6 in the Telegram keyword matcher)
  - Turkish with cedilla / dotted I
  - Multi-place messages: longest alias wins for single-result, all are
    returned for ``geocode_all``
  - No-match returns ``None``
  - Short-fragment guard prevents 2-char prefixes matching unrelated words
"""
from __future__ import annotations

import pytest

from backend.agents._geocoder import Geocoder, _normalize


# ───────────────────────────────────────────────────────────────────────────────
# _normalize sanity (mirrors test_telegram_keywords)
# ───────────────────────────────────────────────────────────────────────────────
def test_normalize_strips_greek_tonos():
    assert _normalize("Σαντορίνη") == _normalize("ΣΑΝΤΟΡΙΝΗ")


def test_normalize_handles_turkish_cedilla():
    assert _normalize("Çeşme") == _normalize("CESME")


# ───────────────────────────────────────────────────────────────────────────────
# Geocoder.geocode_text — single hit
# ───────────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def gc() -> Geocoder:
    return Geocoder()


def test_english_match(gc):
    m = gc.geocode_text("Greek frigate spotted off Lesvos coast")
    assert m is not None
    assert m.canonical == "Lesvos"
    assert abs(m.lat - 39.10) < 0.05


def test_greek_uppercase_no_tonos_matches_lowercase_with_tonos(gc):
    """The exact pattern that broke our Telegram keyword matcher."""
    m = gc.geocode_text("ΣΑΝΤΟΡΙΝΗ συναγερμός")   # uppercase, no tonos
    assert m is not None
    assert m.canonical == "Santorini"


def test_turkish_cedilla(gc):
    m = gc.geocode_text("Çanakkale Boğazı'nda gemi geçişi")
    assert m is not None
    assert m.canonical in {"Canakkale", "Dardanelles"}


def test_alternate_transliteration(gc):
    # Lesbos (older spelling) and Mytilene (city/island synonym)
    assert gc.geocode_text("incident at Lesbos").canonical == "Lesvos"
    assert gc.geocode_text("Mytilene port").canonical == "Lesvos"


def test_no_match_returns_none(gc):
    assert gc.geocode_text("just a weather forecast for tomorrow") is None
    assert gc.geocode_text("") is None


def test_short_fragment_guard():
    """A 2-char alias like 'GR' must not match inside unrelated words."""
    tiny_places = ({
        "canonical": "FakePlace",
        "lat": 0.0, "lon": 0.0, "country": "XX",
        "names": ["GR"],
        "_variants": ((_normalize("GR"), "GR"),),
    },)
    g = Geocoder(places=tiny_places)
    # "Greece" and "Aegean" both contain "gr" but should NOT match
    assert g.geocode_text("Greece is great") is None
    assert g.geocode_text("Aegean grocery list") is None


# ───────────────────────────────────────────────────────────────────────────────
# Longest-alias-wins (avoid Ege clipping Ege Denizi)
# ───────────────────────────────────────────────────────────────────────────────
def test_longest_alias_wins(gc):
    """'Ege Denizi' (Turkish for Aegean Sea) should NOT clip to a generic
    Aegean Sea match before the more specific aliases get a chance — both
    happen to be the same canonical entry here, so we just confirm it
    resolves to Aegean Sea, not something weirder."""
    m = gc.geocode_text("Türk savaş gemisi Ege Denizi'nde tespit edildi")
    assert m is not None
    assert m.canonical == "Aegean Sea"


# ───────────────────────────────────────────────────────────────────────────────
# geocode_all
# ───────────────────────────────────────────────────────────────────────────────
def test_geocode_all_returns_distinct_places_in_order(gc):
    text = "Reports of activity off Lesvos and ferries delayed at Piraeus port"
    matches = gc.geocode_all(text)
    canonicals = [m.canonical for m in matches]
    assert "Lesvos" in canonicals
    assert "Piraeus" in canonicals
    # Ordered by appearance in the text
    assert canonicals.index("Lesvos") < canonicals.index("Piraeus")


def test_geocode_all_dedupes_canonicals(gc):
    text = "Athens summit ends; Athens analysts react; Athens, Greece sources"
    matches = gc.geocode_all(text)
    canonicals = [m.canonical for m in matches]
    assert canonicals.count("Athens") == 1


def test_geocode_all_empty():
    g = Geocoder()
    assert g.geocode_all("") == []
    assert g.geocode_all("nothing relevant here") == []


# ───────────────────────────────────────────────────────────────────────────────
# Sanity: realistic Aegean OSINT phrase set
# ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("Έλληνες ψαράδες σώθηκαν κοντά στη Σάμο",                 "Samos"),
    ("Turkish navy spokesperson denied incursion off Kos",      "Kos"),
    ("Boğaz'da yoğun trafik var",                                "Bosphorus"),
    ("Évros sınırında olay",                                     "Evros"),
    ("Pireus seaport crowd updates this evening",                "Piraeus"),
    ("Cesme'den Chios'a ferry hattı",                            "Cesme"),  # first match wins
    ("Cyprus Limassol port advisory",                            "Limassol"),
])
def test_realistic_aegean_phrases(gc, text, expected):
    m = gc.geocode_text(text)
    assert m is not None, f"no match for {text!r}"
    assert m.canonical == expected, f"{text!r} -> {m.canonical} (expected {expected})"
