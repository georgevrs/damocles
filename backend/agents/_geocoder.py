"""Lightweight gazetteer geocoder.

We deliberately did NOT pull spaCy NER into Day 9. For a curated AOI (the
Aegean / Eastern Med) a hardcoded gazetteer + diacritic-tolerant substring
matcher catches >85% of place mentions in OSINT messages, runs in <1 ms per
message, and produces zero false positives from misclassified entities.

When a Day 9+ message contains a place we don't know about (e.g., a small
Turkish village name), the geocoder returns ``None`` and the LinguistAgent
hands the message off to the LLM with a "geocode this if you can" prompt
fallback. That LLM step is also gazetteer-grounded — the model is told it
can ONLY return places from the same JSON list.

If we later want broader coverage, swap in spaCy NER without changing the
``Geocoder.geocode_text()`` signature.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.config import settings

log = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """NFD decompose -> strip combining marks -> casefold -> unify Greek sigma.

    Greek-specific gotcha: ``"Σάμος".casefold()`` keeps the final ``ς``,
    while ``"ΣΑΜΟΣ".casefold()`` produces the regular ``σ`` — so the two
    surface forms of "Samos" don't substring-match each other unless we
    unify the two sigma forms here.
    """
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.casefold()
    s = s.replace("ς", "σ")
    return s


def _alias_variants(name: str) -> tuple[str, ...]:
    """Generate matching variants for a single gazetteer alias.

    Greek nouns inflect across cases — ``Σάμος`` (nom.) becomes ``Σάμο``
    (acc.) by dropping the final sigma, ``Σάμου`` (gen.) by adding -υ.
    Adding the trailing-sigma-stripped variant catches the most common
    inflection pattern; full lemmatization would need a Greek stemmer.
    """
    base = _normalize(name)
    if not base:
        return ()
    out = [base]
    if base.endswith("σ"):
        out.append(base[:-1])
    return tuple(dict.fromkeys(out))   # de-dupe while preserving order


@dataclass(frozen=True)
class GeoMatch:
    canonical: str
    lat: float
    lon: float
    country: str
    matched_alias: str
    text_offset: int   # where the match landed in the original text


@lru_cache(maxsize=1)
def _gazetteer_path() -> Path:
    return settings.data_dir / "geojson" / "aegean_gazetteer.json"


@lru_cache(maxsize=1)
def _load_places() -> tuple[dict, ...]:
    """Read once, cache for the process lifetime."""
    raw = json.loads(_gazetteer_path().read_text(encoding="utf-8"))
    out = []
    for entry in raw["places"]:
        # Pre-compute every matching variant of every alias so matching is
        # a tight inner loop with no string ops on the hot path.
        variants: list[tuple[str, str]] = []   # (normalized_variant, canonical_alias)
        for alias in entry["names"]:
            for v in _alias_variants(alias):
                variants.append((v, alias))
        out.append({
            "canonical": entry["name"],
            "lat":       entry["lat"],
            "lon":       entry["lon"],
            "country":   entry["country"],
            "names":     entry["names"],
            "_variants": tuple(variants),
        })
    return tuple(out)


# Avoid 2-char alias fragments matching anywhere in unrelated words ("GR" in "Greece").
_MIN_ALIAS_LEN = 3


class Geocoder:
    """Hardcoded gazetteer matcher with diacritic-tolerant substring search.

    Designed for the Aegean AOI; ~46 places cover the demo scenario.

    Resolution order: leftmost match in the text wins, with longest alias
    as tie-breaker (so ``Ege Denizi`` beats ``Ege`` at the same offset).
    """

    def __init__(self, places: tuple[dict, ...] | None = None):
        self.places = places or _load_places()

    def geocode_text(self, text: str) -> GeoMatch | None:
        """Return the leftmost gazetteer match in ``text``.

        Returns ``None`` if no place is found. We don't return all matches —
        callers want a single (lat, lon) to attach to a SocialSignal.
        """
        all_matches = self._all_matches(text)
        return all_matches[0] if all_matches else None

    def geocode_all(self, text: str) -> list[GeoMatch]:
        """Find every distinct place in ``text`` (one per canonical name),
        ordered by appearance."""
        seen: set[str] = set()
        out: list[GeoMatch] = []
        for m in self._all_matches(text):
            if m.canonical in seen:
                continue
            seen.add(m.canonical)
            out.append(m)
        return out

    # ─── internals ───────────────────────────────────────────────────────────
    def _all_matches(self, text: str) -> list[GeoMatch]:
        """All alias hits in ``text``, sorted by (offset, -alias_length).

        Sorting by ``-alias_length`` as tie-breaker ensures the longest /
        most-specific alias wins when two aliases land at the same offset
        (e.g., ``Ege Denizi`` over ``Ege``).
        """
        if not text:
            return []
        haystack = _normalize(text)
        hits: list[tuple[int, int, GeoMatch]] = []
        for entry in self.places:
            for variant, canonical_alias in entry["_variants"]:
                if len(variant) < _MIN_ALIAS_LEN:
                    continue
                offset = haystack.find(variant)
                if offset >= 0:
                    hits.append((
                        offset,
                        -len(variant),
                        GeoMatch(
                            canonical=entry["canonical"],
                            lat=entry["lat"],
                            lon=entry["lon"],
                            country=entry["country"],
                            matched_alias=canonical_alias,
                            text_offset=offset,
                        ),
                    ))
        hits.sort(key=lambda t: (t[0], t[1]))
        return [h[2] for h in hits]
