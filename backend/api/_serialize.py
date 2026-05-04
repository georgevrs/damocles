"""Coerce neo4j-native types to JSON-friendly Python primitives.

The neo4j driver returns ``neo4j.time.DateTime`` for datetime properties
(and ``neo4j.time.Date``, ``Time``, ``Duration`` for the other temporal
types). Pydantic's serializer doesn't know about them, so any endpoint
that surfaces a raw Node will 500 with ``PydanticSerializationError``.

Use ``jsonable(obj)`` at the boundary of every endpoint that touches the
graph. It walks dicts/lists/Nodes recursively and converts neo4j temporal
types to ISO 8601 strings.
"""
from __future__ import annotations

from typing import Any

try:
    from neo4j.time import Date, DateTime, Duration, Time
except ImportError:   # pragma: no cover — driver always present in the wheel
    Date = DateTime = Duration = Time = ()   # type: ignore[assignment,misc]

# neo4j Node has a ._properties dict and behaves like a Mapping.
try:
    from neo4j.graph import Node as _Neo4jNode
except ImportError:   # pragma: no cover
    _Neo4jNode = ()   # type: ignore[assignment,misc]


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if _Neo4jNode and isinstance(value, _Neo4jNode):
        return jsonable(dict(value))
    if isinstance(value, (DateTime, Date, Time)):
        return value.iso_format()
    if isinstance(value, Duration):
        return str(value)
    return value
