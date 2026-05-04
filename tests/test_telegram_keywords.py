"""Telegram keyword matcher unit tests.

The matcher must handle:
  - English ASCII (trivial case)
  - Greek mixed-case + monotonic tonos (uppercase drops the accent)
  - Turkish I/ı/İ/i casefolding
  - empty / no-match / multi-keyword OR

No network — pure-string tests only. Telegram itself can't be tested without
a live session.
"""
from __future__ import annotations

import pytest

from backend.sensors.telegram_sensor import _matches_any_keyword, _normalize


# ───────────────────────────────────────────────────────────────────────────────
# _normalize
# ───────────────────────────────────────────────────────────────────────────────
def test_normalize_strips_greek_tonos():
    # Lowercase with tonos and uppercase without (monotonic Greek convention)
    # both normalize to the same string.
    assert _normalize("Αιγαίο") == _normalize("ΑΙΓΑΙΟ")


def test_normalize_handles_turkish_i():
    # Dotted vs dotless I
    assert _normalize("İSTANBUL") == _normalize("istanbul")
    assert _normalize("IHLAL") == _normalize("ihlal")


def test_normalize_idempotent():
    s = "frigate transit"
    assert _normalize(_normalize(s)) == _normalize(s)


# ───────────────────────────────────────────────────────────────────────────────
# _matches_any_keyword
# ───────────────────────────────────────────────────────────────────────────────
def test_match_english_simple():
    assert _matches_any_keyword("Greek frigate spotted in north Aegean", ["frigate"]) is True


def test_match_greek_uppercase_against_lowercase_with_tonos():
    """The bug that caught us during Day 6 smoke testing."""
    text = "ΑΙΓΑΙΟ κρίση σήμερα"
    keywords = ["Αιγαίο"]
    assert _matches_any_keyword(text, keywords) is True


def test_match_greek_lowercase_against_uppercase_keyword():
    text = "αιγαίο σήμερα"
    keywords = ["ΑΙΓΑΙΟ"]
    assert _matches_any_keyword(text, keywords) is True


def test_match_turkish_dotted_i():
    assert _matches_any_keyword("İHLAL tespit edildi", ["ihlal"]) is True
    assert _matches_any_keyword("ihlal tespit edildi", ["İHLAL"]) is True


def test_no_match():
    assert _matches_any_keyword("weather forecast for tomorrow", ["frigate", "navy"]) is False


def test_empty_text():
    assert _matches_any_keyword("", ["anything"]) is False


def test_empty_keywords():
    assert _matches_any_keyword("some text", []) is False


def test_multi_keyword_or_match_picks_any():
    keywords = ["aegean", "Αιγαίο", "Ege"]
    assert _matches_any_keyword("Major Ege incident reported", keywords) is True
    assert _matches_any_keyword("AEGEAN dispute", keywords) is True
    assert _matches_any_keyword("Αιγαίο σήμερα", keywords) is True
    assert _matches_any_keyword("unrelated content", keywords) is False


@pytest.mark.parametrize("text,keywords,expected", [
    ("ΕΛΛΗΝΙΚΌ ΠΟΛΕΜΙΚΌ ΠΛΟΊΟ", ["πολεμικό", "πλοίο"], True),     # Greek with tonos in keywords, none in text
    ("Türk savaş gemisi", ["savaş gemisi"], True),                # Turkish with cedilla
    ("Greek navy ship", ["frigate"], False),                       # legitimate negative
])
def test_realistic_aegean_phrases(text, keywords, expected):
    assert _matches_any_keyword(text, keywords) is expected
