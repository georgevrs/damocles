"""Application settings — read from environment via pydantic-settings.

Usage:
    from backend.config import settings
    settings.LLM_PROVIDER  # "gemini" | "ollama"
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ─── LLM ──────────────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["gemini", "ollama"] = "gemini"

    # Gemini (development)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Ollama (demo / production)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_DEVIL_MODEL: str = "qwen2.5:7b"

    # ─── Geospatial ──────────────────────────────────────────────────────────
    SENTINELHUB_CLIENT_ID: str = ""
    SENTINELHUB_CLIENT_SECRET: str = ""

    # ─── OSINT ────────────────────────────────────────────────────────────────
    TELEGRAM_API_ID: str = ""
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_PHONE: str = ""
    AISSTREAM_API_KEY: str = ""

    # ─── Graph ───────────────────────────────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""   # set via .env — empty default surfaces forgotten overrides

    # ─── Application ──────────────────────────────────────────────────────────
    DAMOCLES_ENV: Literal["development", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    DEMO_MODE: bool = True
    GCP_PROJECT_ID: str = ""

    # ─── Phase 2 — fact store + standing scan ────────────────────────────────
    DUCKDB_PATH: str = ""              # blank → data_dir/damocles.duckdb
    STANDING_SCAN_CRON: str = "0 4 * * *"  # daily 04:00 UTC; "" disables the scheduler
    STANDING_SCAN_DAYS: int = 7
    EOX_WMTS_URL: str = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{TileMatrix}/{TileRow}/{TileCol}.jpg"

    # Per-sensor cache TTLs (seconds). 0 disables caching for that sensor.
    CACHE_TTL_AIS: int = 300
    CACHE_TTL_GDELT: int = 1800
    CACHE_TTL_SAR: int = 21600
    CACHE_TTL_TELEGRAM: int = 600
    CACHE_TTL_OPENSKY: int = 300

    # ─── Paths (derived) ──────────────────────────────────────────────────────
    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parent.parent

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def cache_dir(self) -> Path:
        d = self.data_dir / "cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def audit_log_path(self) -> Path:
        return self.project_root / "audit_log.jsonl"

    @property
    def duckdb_path(self) -> Path:
        if self.DUCKDB_PATH:
            return Path(self.DUCKDB_PATH)
        d = self.data_dir
        d.mkdir(parents=True, exist_ok=True)
        return d / "damocles.duckdb"


settings = Settings()
