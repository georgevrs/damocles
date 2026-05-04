"""Neo4j async driver wrapper.

Single entry point for every Cypher query in the app. Owns the driver
lifecycle and applies the schema on startup.
"""
from __future__ import annotations

import logging
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from backend.config import settings

from .schema import SCHEMA_CONSTRAINTS

log = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        if self._driver is not None:
            return
        self._driver = AsyncGraphDatabase.driver(self.uri, auth=(self.user, self.password))
        await self._driver.verify_connectivity()
        log.info("Neo4j connected: %s", self.uri)

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4jClient.connect() must be called before use")
        return self._driver

    async def apply_schema(self) -> None:
        """Idempotent — safe to call on every startup."""
        for stmt in SCHEMA_CONSTRAINTS:
            await self.run(stmt)
        log.info("Neo4j schema applied (%d statements)", len(SCHEMA_CONSTRAINTS))

    async def run(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        """Run a Cypher statement and materialize all rows."""
        async with self.driver.session() as session:
            result = await session.run(cypher, **params)
            return [record.data() async for record in result]

    async def health_check(self) -> bool:
        try:
            rows = await self.run("RETURN 1 AS ok")
            return bool(rows and rows[0].get("ok") == 1)
        except Exception:
            return False


# Module-level singleton — wired into FastAPI lifespan in main.py
graph_client = Neo4jClient()
