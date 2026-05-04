"""LinguistAgent.enrich() unit tests — deterministic geocoding only.

The LLM-summarization path is covered by ``test_agent_base.py`` (same
``BaseAgent.run`` lifecycle). Here we focus on what's unique to the
Linguist: turning free-text Telegram messages into ``SignalEnrichment``
records via the gazetteer.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.agents.linguist_agent import LinguistAgent, SignalEnrichment
from backend.models.event import SocialSignal


def _signal(text: str, sid: str = "s1") -> SocialSignal:
    return SocialSignal(
        id=sid,
        channel="@aegeanwatch",
        message_id="m1",
        text=text,
        timestamp=datetime(2024, 3, 17, 14, 0, tzinfo=timezone.utc),
        language="en",
        views=100,
    )


def _agent() -> LinguistAgent:
    # graph + llm aren't touched by enrich(); pass None.
    return LinguistAgent(llm=None, graph=None)   # type: ignore[arg-type]


def test_enrich_geocodes_known_place():
    sig = _signal("Greek frigate spotted off Lesvos")
    out = _agent().enrich([sig])
    assert len(out) == 1
    e: SignalEnrichment = out[0]
    assert e.signal_id == "s1"
    assert e.matched_place == "Lesvos"
    assert e.country == "GR"
    assert abs(e.lat - 39.10) < 0.05
    assert abs(e.lon - 26.55) < 0.05


def test_enrich_skips_non_geo_messages():
    sig = _signal("weather forecast says rain tomorrow")
    out = _agent().enrich([sig])
    assert out == []


def test_enrich_handles_greek_inflection():
    """Σάμο is the accusative form of Σάμος. Both must geocode."""
    sig_acc = _signal("Έλληνες ψαράδες σώθηκαν κοντά στη Σάμο", sid="acc")
    sig_nom = _signal("Σάμος συναγερμός", sid="nom")
    out = _agent().enrich([sig_acc, sig_nom])
    assert len(out) == 2
    assert all(e.matched_place == "Samos" for e in out)


def test_enrich_handles_turkish_diacritics():
    sig = _signal("Çanakkale Boğazı'nda yoğun trafik")
    out = _agent().enrich([sig])
    assert len(out) == 1
    assert out[0].matched_place in {"Canakkale", "Dardanelles"}


def test_enrich_first_place_in_text_wins():
    """Multi-place message: leftmost mention is the geocoding result."""
    sig = _signal("Cesme'den Chios'a ferry hattı")
    out = _agent().enrich([sig])
    assert len(out) == 1
    assert out[0].matched_place == "Cesme"


def test_enrich_processes_batch_and_preserves_signal_ids():
    sigs = [
        _signal("Lesvos coast guard report",       sid="a"),
        _signal("Piraeus port advisory",            sid="b"),
        _signal("nothing relevant here",            sid="c"),
        _signal("Activity near Kos and Rhodes",     sid="d"),
    ]
    out = _agent().enrich(sigs)
    by_id = {e.signal_id: e for e in out}
    assert set(by_id) == {"a", "b", "d"}        # "c" had no place name
    assert by_id["a"].matched_place == "Lesvos"
    assert by_id["b"].matched_place == "Piraeus"
    assert by_id["d"].matched_place == "Kos"     # leftmost wins
