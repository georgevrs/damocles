"""Persistent fact store (DuckDB).

Phase 2 introduction. Every sensor fetch is mirrored here so re-running a
watch over a covered window does not re-hit upstream APIs. Trajectories,
hex aggregations, and AoI polygons live here too — Neo4j keeps the
relationships and the citation chain; DuckDB keeps the facts.
"""

from backend.store.client import DuckDBStore, get_store

__all__ = ["DuckDBStore", "get_store"]
