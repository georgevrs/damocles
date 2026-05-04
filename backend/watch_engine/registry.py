"""Quick-launch Watch templates — shown as chips above the analyst's text input.

Selecting a chip populates the input but the analyst can edit freely.
The Watch system is NOT limited to these — any free-text query is supported.
"""
from __future__ import annotations

WATCH_TEMPLATES: list[dict[str, str]] = [
    {
        "id": "aegean_maritime",
        "label": "Aegean Maritime",
        "query": "Aegean — last 7 days",
        "icon": "anchor",
    },
    {
        "id": "evros_border",
        "label": "Evros Border",
        "query": "Evros border activity — last 14 days",
        "icon": "map-pin",
    },
    {
        "id": "eastern_med_airspace",
        "label": "E. Med Airspace",
        "query": "Eastern Mediterranean airspace — last 72 hours",
        "icon": "plane",
    },
    {
        "id": "info_ops_greece",
        "label": "Information Ops",
        "query": "Information operations targeting Greece — last 30 days",
        "icon": "radio",
    },
    {
        "id": "custom",
        "label": "Custom Watch",
        "query": "",
        "icon": "search",
    },
]
