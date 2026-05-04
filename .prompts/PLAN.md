# DAMOCLES — Full Engineering Build Plan
## Sovereign Intelligence Analysis Platform — EYP National Security Innovation Challenge 2026

---

## CONTEXT FOR THE AGENT

You are the lead architect and principal engineer for **Damocles**, a sovereign intelligence-analysis platform being built for the EYP (Greek National Intelligence Service) National Security Innovation Challenge 2026. You are operating inside a VSCode workspace with Claude Code. You have full tool access: file creation, terminal execution, web search, and browser control.

**Your mission:** Build a working, demo-ready PoC in 3 weeks that wins the gold medal at the June 2026 final pitch. The application must be live, not a mockup. Every component must actually run. The primary demo scenario is *"Aegean — last 7 days"* but the Watch system must support arbitrary natural-language queries across all domains and regions — the analyst is not limited to preset options.

**Non-negotiable constraints:**
- All data sources are free and public
- **LLM backend is abstracted behind a provider interface.** During development use Google Gemini API (fast, cheap, no local GPU required). Before the final demo, swap to local Ollama with zero code changes — only an env var changes. This is the correct engineering approach and the sovereignty argument holds for the demo.
- Every claim in every output traces to a source node in the knowledge graph
- A Devil's Advocate agent challenges every alert before it reaches the analyst
- **Development environment is Windows (Windows 11).** All scripts must be PowerShell-compatible. All paths use forward slashes in Python (pathlib handles this). No bash-only commands. Docker Desktop for Windows is available and acceptable for Neo4j only.
- **Deployment target is GCP Linux (Debian/Ubuntu).** The codebase must be platform-agnostic. No Windows-specific code in the application layer — only in dev scripts.
- No complex startup — it must start with one command on both Windows (PowerShell) and Linux (bash)

**LLM provider abstraction — implement this from day one:**
The entire agent layer must call `LLMProvider.complete()` — never call Gemini or Ollama directly from agent code. The provider is selected by the `LLM_PROVIDER` env var: `gemini` during development, `ollama` for demo and production. This single architectural decision allows the demo sovereignty narrative ("no data leaves Greek infrastructure") to be true while letting you develop fast on Gemini.

**The gold-medal differentiator:** The citation chain. A judge clicks any sentence in the brief → the map highlights the source location → the knowledge graph highlights the source node → the raw evidence (SAR tile / news article / Telegram message) opens. No competitor will have this.

---

## REPOSITORY STRUCTURE

Initialize the following structure before writing any code:

```
damocles/
├── README.md
├── .env.example
├── pyproject.toml
├── start.ps1                   # Windows PowerShell startup script
├── start.sh                    # Linux/GCP startup script
├── Makefile                    # Cross-platform convenience commands
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Settings via pydantic-settings
│   ├── models/
│   │   ├── __init__.py
│   │   ├── watch.py            # Watch object — supports arbitrary queries
│   │   ├── event.py            # Fused event (vessel / news / social / flight)
│   │   ├── brief.py            # Intelligence brief with citation nodes
│   │   └── audit.py            # Audit log entry with Merkle hash
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py             # LLMProvider ABC — the abstraction boundary
│   │   ├── gemini.py           # Google Gemini implementation (dev)
│   │   ├── ollama.py           # Ollama implementation (demo/prod)
│   │   └── factory.py          # get_provider() — reads LLM_PROVIDER env var
│   ├── sensors/
│   │   ├── __init__.py
│   │   ├── base.py             # BaseSensor ABC
│   │   ├── geospatial.py       # Sentinel-1/2 + vessel detection
│   │   ├── osint.py            # GDELT + Telegram + OpenSky
│   │   └── fusion.py           # Temporal/spatial correlation engine
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── client.py           # Neo4j driver wrapper
│   │   ├── schema.py           # Node/edge type definitions
│   │   ├── queries.py          # Cypher query library
│   │   └── ingestion.py        # Sensor output → graph nodes
│   ├── watch_engine/
│   │   ├── __init__.py
│   │   ├── parser.py           # NL query → WatchSpec (uses LLMProvider)
│   │   ├── registry.py         # Predefined watch templates + custom
│   │   └── executor.py         # Runs a Watch through all sensors
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py             # BaseAgent ABC — calls LLMProvider
│   │   ├── geospatial_agent.py
│   │   ├── osint_agent.py
│   │   ├── linguist_agent.py
│   │   ├── devils_advocate.py
│   │   ├── supervisor.py
│   │   └── prompts/
│   │       ├── geospatial.txt
│   │       ├── osint.txt
│   │       ├── linguist.txt
│   │       ├── devils_advocate.txt
│   │       └── supervisor.txt
│   ├── audit/
│   │   ├── __init__.py
│   │   └── logger.py           # Merkle-chained audit log
│   └── api/
│       ├── __init__.py
│       ├── watches.py          # POST/GET watch endpoints
│       ├── briefs.py           # GET brief, GET citation chain
│       ├── graph.py            # GET graph data for visualization
│       ├── audit.py            # GET audit log
│       └── ws.py               # WebSocket for real-time progress
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── WatchInput.tsx      # Free-text input + suggestion chips
│   │   │   ├── WatchSuggestions.tsx # Quick-launch preset scenarios
│   │   │   ├── MapPanel.tsx
│   │   │   ├── BriefPanel.tsx
│   │   │   ├── GraphPanel.tsx
│   │   │   ├── AuditLog.tsx
│   │   │   ├── CitationTooltip.tsx
│   │   │   ├── ProgressStream.tsx
│   │   │   └── EvidenceModal.tsx
│   │   ├── hooks/
│   │   │   ├── useWatch.ts
│   │   │   ├── useCitation.ts
│   │   │   └── useAudit.ts
│   │   ├── store/
│   │   │   └── damocles.ts
│   │   └── types/
│   │       └── index.ts
├── docker/
│   └── neo4j/
│       └── docker-compose.yml  # Neo4j only — Windows dev convenience
├── models/
│   └── README.md               # Instructions to download Ollama models
├── data/
│   ├── geojson/
│   │   ├── greek_eez.geojson
│   │   ├── aegean_sea.geojson
│   │   ├── evros_border.geojson
│   │   └── eastern_med.geojson
│   └── sample/
│       └── README.md
├── scripts/
│   ├── setup_windows.ps1       # One-time Windows dev environment setup
│   ├── setup_linux.sh          # One-time GCP/Linux setup
│   ├── download_models.ps1     # Pull Ollama models (Windows)
│   ├── download_models.sh      # Pull Ollama models (Linux)
│   ├── seed_neo4j.py           # Pre-load demo scenario data
│   └── verify_sources.py       # Test all free API connections
└── tests/
    ├── test_llm_provider.py    # Tests both Gemini and Ollama via same interface
    ├── test_watch_parser.py    # Tests arbitrary query parsing
    ├── test_sensors.py
    ├── test_graph.py
    ├── test_agents.py
    └── test_citation_chain.py  # The gold-medal test
```

---

## TECHNOLOGY STACK — EXACT VERSIONS

### Backend
```toml
# pyproject.toml — use uv for dependency management (faster than pip)
[project]
name = "damocles"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Web framework
    "fastapi==0.115.0",
    "uvicorn[standard]==0.30.6",
    "websockets==13.0",

    # Data validation
    "pydantic==2.8.2",
    "pydantic-settings==2.4.0",

    # Graph database
    "neo4j==5.24.0",

    # Geospatial
    "sentinelhub==3.10.4",      # Copernicus / Sentinel data
    "rasterio==1.3.10",         # SAR tile processing
    "shapely==2.0.6",           # Geometry operations
    "pyproj==3.6.1",            # Coordinate transforms
    "numpy==1.26.4",
    "opencv-python==4.10.0.84", # Image processing for SAR

    # OSINT
    "gdelt==0.1.10",            # GDELT Python client
    "telethon==1.36.0",         # Telegram MTProto client
    "opensky-api==1.3",         # OpenSky Network

    # NLP
    "spacy==3.7.6",             # Greek NER (el_core_news_lg)
    "langdetect==1.0.9",

    # LLM — provider abstraction layer
    # Both are installed; which one runs is controlled by LLM_PROVIDER env var
    "google-generativeai==0.8.3",   # Gemini (development)
    "ollama==0.3.3",                # Ollama (demo / production)

    # Agent orchestration — provider-agnostic
    "langchain==0.3.1",
    "langchain-google-genai==2.0.4",  # Gemini LangChain integration
    "langchain-ollama==0.2.0",        # Ollama LangChain integration
    "langchain-community==0.3.1",

    # Knowledge graph tools
    "networkx==3.3",            # In-memory graph for fusion

    # Async
    "httpx==0.27.2",
    "aiofiles==24.1.0",

    # Utilities
    "python-dotenv==1.0.1",
    "structlog==24.4.0",        # Structured logging
    "rich==13.8.1",             # Terminal output
    "pathlib2==2.3.7",          # Explicit cross-platform paths
]
```

### Frontend
```json
{
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.2",
    "leaflet": "^1.9.4",
    "react-leaflet": "^4.2.1",
    "cytoscape": "^3.30.1",
    "zustand": "^4.5.5",
    "tailwindcss": "^3.4.10",
    "@tanstack/react-query": "^5.56.2",
    "axios": "^1.7.7",
    "lucide-react": "^0.439.0",
    "date-fns": "^3.6.0"
  }
}
```

### Infrastructure

**Windows development machine:**
- **Neo4j** — run via Docker Desktop: `docker compose -f docker/neo4j/docker-compose.yml up -d`
  - This is the simplest approach on Windows. Neo4j Desktop is an alternative but Docker is more reproducible.
  - `docker/neo4j/docker-compose.yml` should mount a local volume so data persists across container restarts.
- **Ollama** — download Windows installer from https://ollama.ai/download/windows (only needed when switching to local LLM for demo prep)
- **Python** — use `uv` (install via `pip install uv` or the standalone Windows installer). Much faster than pip on Windows.
- **Node.js** — install via https://nodejs.org (LTS, v20+)
- **Models to pull (only when switching to Ollama):**
  - `ollama pull llama3.1:8b`
  - `ollama pull qwen2.5:7b`
  - `python -m spacy download el_core_news_lg`

**GCP deployment (Linux/Debian):**
- Instance type: `e2-standard-4` (4 vCPU, 16GB RAM) — sufficient for the demo, ~€100/month
- Neo4j: systemd service, not Docker, for better GCP integration
- Ollama: installed via shell script, runs as systemd service
- Nginx reverse proxy in front of FastAPI and Vite static build
- All secrets via GCP Secret Manager, not `.env` files

**`docker/neo4j/docker-compose.yml`:**
```yaml
version: "3.8"
services:
  neo4j:
    image: neo4j:5.24-community
    ports:
      - "7474:7474"   # Browser
      - "7687:7687"   # Bolt
    environment:
      NEO4J_AUTH: neo4j/CHANGE_ME_neo4j_password
      NEO4J_PLUGINS: '["apoc"]'
      NEO4J_dbms_memory_heap_max__size: 2G
    volumes:
      - ./neo4j_data:/data
      - ./neo4j_logs:/logs
    restart: unless-stopped
```

---

## COMPONENT 1: THE WATCH OBJECT

**File:** `backend/models/watch.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import uuid

class WatchDomain(str, Enum):
    MARITIME = "maritime"
    BORDER = "border"
    AIRSPACE = "airspace"
    INFORMATION = "information"

class WatchRegion(str, Enum):
    AEGEAN = "aegean"
    IONIAN = "ionian"
    EVROS = "evros"
    EASTERN_MED = "eastern_med"

class Watch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str                              # Raw analyst input: "Aegean — last 7 days"
    region: WatchRegion
    domain: WatchDomain
    time_window_days: int = 7
    created_at: datetime = Field(default_factory=datetime.utcnow)
    region_geojson: Optional[dict] = None  # Loaded from greek_eez.geojson
    status: str = "pending"                # pending | processing | complete | error
```

**Parse the analyst's natural-language query into a Watch object using a small LLMProvider call with a strict JSON output schema. Do not use regex for parsing — use the LLM for robustness.**

---

## COMPONENT 1b: THE LLM PROVIDER ABSTRACTION

**This is the most important architectural decision in the codebase. Implement it before writing a single agent.**

**File:** `backend/llm/base.py`

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any

class LLMMessage(BaseModel):
    role: str   # "system" | "user" | "assistant"
    content: str

class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: float

class LLMProvider(ABC):
    """
    The single abstraction boundary between agent logic and LLM backends.
    All agents call this interface. Never import Gemini or Ollama in agent code.
    
    The provider is selected at startup via the LLM_PROVIDER env var.
    Swapping providers requires zero code changes — only a .env edit.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        json_mode: bool = False,    # When True, provider enforces JSON output
    ) -> LLMResponse:
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Called at startup to verify the provider is reachable."""
        ...
```

**File:** `backend/llm/gemini.py`

```python
import google.generativeai as genai
import time
from .base import LLMProvider, LLMMessage, LLMResponse

class GeminiProvider(LLMProvider):
    """
    Google Gemini provider for development.
    
    Model: gemini-2.0-flash (fast, cheap, excellent at structured JSON)
    Free tier: 15 RPM, 1M tokens/day — more than sufficient for development.
    Paid tier: ~$0.075/1M input tokens — negligible cost.
    
    IMPORTANT: Gemini is ONLY used during development on the Windows machine.
    The demo runs Ollama. The sovereignty claim is valid because the demo
    runs on a local server with no external API calls.
    """
    MODEL = "gemini-2.0-flash"

    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.client = genai.GenerativeModel(self.MODEL)

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.time()

        # Convert LLMMessage format to Gemini format
        # Gemini uses a different message structure — handle the system message
        system_instruction = None
        history = []
        last_user_message = ""

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            elif msg.role == "user":
                last_user_message = msg.content
                if history:
                    history.append({"role": "user", "parts": [msg.content]})
            elif msg.role == "assistant":
                history.append({"role": "model", "parts": [msg.content]})

        # Rebuild with system instruction if present
        model = genai.GenerativeModel(
            self.MODEL,
            system_instruction=system_instruction,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else "text/plain",
            )
        )

        response = model.generate_content(
            history + [{"role": "user", "parts": [last_user_message]}]
        )

        latency = (time.time() - start) * 1000
        return LLMResponse(
            content=response.text,
            model=self.MODEL,
            provider="gemini",
            input_tokens=response.usage_metadata.prompt_token_count,
            output_tokens=response.usage_metadata.candidates_token_count,
            latency_ms=latency,
        )

    def get_model_name(self) -> str:
        return self.MODEL

    async def health_check(self) -> bool:
        try:
            r = await self.complete(
                [LLMMessage(role="user", content="Say OK")],
                max_tokens=5
            )
            return "OK" in r.content
        except Exception:
            return False
```

**File:** `backend/llm/ollama.py`

```python
import ollama as _ollama
import time
from .base import LLMProvider, LLMMessage, LLMResponse

class OllamaProvider(LLMProvider):
    """
    Ollama local LLM provider for demo and production.
    
    Runs entirely on-prem. No data leaves the machine.
    This is what runs during the EYP demo.
    
    Recommended models:
    - Primary reasoning: llama3.1:8b (4.7GB, ~10 tokens/sec on M3/A100)
    - Devil's Advocate: qwen2.5:7b (4.4GB, slightly more creative)
    - Fast parsing: llama3.2:3b (2.0GB, for Watch query parsing only)
    
    Hardware requirement for smooth demo:
    - GPU: 8GB VRAM minimum (RTX 3070 / M2 Pro / A10G on GCP)
    - RAM: 16GB minimum
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1:8b"):
        self.base_url = base_url
        self.model = model
        self._client = _ollama.AsyncClient(host=base_url)

    async def complete(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        start = time.time()

        ollama_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

        response = await self._client.chat(
            model=self.model,
            messages=ollama_messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            format="json" if json_mode else "",
        )

        latency = (time.time() - start) * 1000
        return LLMResponse(
            content=response["message"]["content"],
            model=self.model,
            provider="ollama",
            input_tokens=response.get("prompt_eval_count", 0),
            output_tokens=response.get("eval_count", 0),
            latency_ms=latency,
        )

    def get_model_name(self) -> str:
        return self.model

    async def health_check(self) -> bool:
        try:
            models = await self._client.list()
            return self.model in [m["name"] for m in models.get("models", [])]
        except Exception:
            return False
```

**File:** `backend/llm/factory.py`

```python
from .base import LLMProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from backend.config import settings

def get_provider() -> LLMProvider:
    """
    Returns the configured LLM provider.
    Called once at startup and injected via FastAPI dependency.
    
    LLM_PROVIDER=gemini  → GeminiProvider (development on Windows)
    LLM_PROVIDER=ollama  → OllamaProvider (demo and GCP deployment)
    
    SWITCHING FROM GEMINI TO OLLAMA:
    1. Change LLM_PROVIDER=ollama in .env
    2. Ensure Ollama is running: `ollama serve`
    3. Ensure model is pulled: `ollama pull llama3.1:8b`
    4. Restart the backend
    Zero code changes required.
    """
    if settings.LLM_PROVIDER == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set")
        return GeminiProvider(api_key=settings.GEMINI_API_KEY)

    elif settings.LLM_PROVIDER == "ollama":
        return OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
        )

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.LLM_PROVIDER}")
```

**Update `BaseAgent` to use the provider:**

```python
# backend/agents/base.py — the ONLY correct way agents call the LLM
class BaseAgent:
    def __init__(self, graph_client, audit_logger, llm_provider: LLMProvider):
        self.graph = graph_client
        self.audit = audit_logger
        self.llm = llm_provider   # Injected — never instantiated inside an agent
```

---

## COMPONENT 1c: THE WATCH ENGINE — ARBITRARY QUERY SUPPORT

**File:** `backend/watch_engine/parser.py`

```python
from backend.llm.base import LLMProvider, LLMMessage
from backend.models.watch import Watch, WatchSpec
import json

WATCH_PARSE_SYSTEM_PROMPT = """
You are a query parser for Damocles, a sovereign intelligence platform.
The analyst has typed a free-text query. Parse it into a structured WatchSpec JSON.

The analyst may type anything. Examples of valid queries:
- "Aegean — last 7 days"
- "Turkish military activity near Rhodes last 2 weeks"
- "Information operations targeting Greek elections last month"
- "Unusual flights over Thrace past 3 days"
- "Evros border activity since Monday"
- "Maritime incidents Eastern Mediterranean Q1 2024"
- "Coordinated social media campaigns about Cyprus dispute"
- "Port of Piraeus vessel anomalies last 48 hours"

Output ONLY valid JSON. No preamble.
{
  "region": "aegean|ionian|evros|eastern_med|custom",
  "custom_bbox": [float, float, float, float] | null,
  "domain": "maritime|border|airspace|information|multi",
  "time_window_days": int,
  "keywords": [str],
  "threat_indicators": [str],
  "confidence": float,
  "parse_notes": str
}
"""

class WatchParser:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def parse(self, raw_query: str) -> WatchSpec:
        response = await self.llm.complete(
            messages=[
                LLMMessage(role="system", content=WATCH_PARSE_SYSTEM_PROMPT),
                LLMMessage(role="user", content=f'Parse this query: "{raw_query}"'),
            ],
            temperature=0.0,
            max_tokens=512,
            json_mode=True,
        )
        return WatchSpec(**json.loads(response.content))
```

**File:** `backend/watch_engine/registry.py`

```python
WATCH_TEMPLATES = [
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
# Shown as clickable chips above the text input in WatchInput.tsx
# Selecting a chip populates the input but the analyst can edit freely
```

Updated `Watch` model:

```python
# backend/models/watch.py

class WatchSpec(BaseModel):
    region: str
    custom_bbox: Optional[list[float]] = None
    domain: WatchDomain
    time_window_days: int = 7
    keywords: list[str] = []
    threat_indicators: list[str] = []
    confidence: float = 1.0
    parse_notes: Optional[str] = None

    def get_bbox(self) -> tuple[float, float, float, float]:
        REGION_BBOXES = {
            "aegean":      (22.0, 35.0, 28.0, 42.0),
            "ionian":      (19.0, 36.0, 23.5, 41.0),
            "evros":       (25.8, 40.8, 26.8, 42.2),
            "eastern_med": (20.0, 30.0, 37.0, 38.0),
        }
        if self.region == "custom" and self.custom_bbox:
            return tuple(self.custom_bbox)
        return REGION_BBOXES.get(self.region, REGION_BBOXES["aegean"])

class Watch(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_query: str
    spec: WatchSpec
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"
    brief_id: Optional[str] = None
```

---

## COMPONENT 2: THE GEOSPATIAL SENSOR

**File:** `backend/sensors/geospatial.py`

### 2a — Sentinel-1 SAR data acquisition

```python
import sentinelhub
from sentinelhub import (
    SHConfig, BBox, CRS, DataCollection,
    SentinelHubRequest, MimeType, bbox_to_dimensions
)

# Authentication: register free account at dataspace.copernicus.eu
# Client ID and Secret go in .env — FREE tier gives 30,000 processing units/month
# The demo will use ~200 processing units total. Well within free tier.

EVALSCRIPT_SAR_VESSEL = """
//VERSION=3
// Sentinel-1 SAR vessel detection evalscript
// Returns VV polarization calibrated backscatter
function setup() {
  return {
    input: [{ bands: ["VV", "VH"] }],
    output: { bands: 1, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  // High backscatter = potential vessel
  return [10 * Math.log10(sample.VV)];
}
"""

class GeospatialSensor:
    def __init__(self, config: SHConfig):
        self.config = config

    async def fetch_sar_tiles(
        self,
        bbox: BBox,
        time_from: datetime,
        time_to: datetime
    ) -> list[dict]:
        """
        Returns list of SAR observations with:
        - tile_id: str
        - timestamp: datetime
        - image_array: np.ndarray
        - bbox: BBox
        Each tile is ~50MB for Aegean coverage at 10m resolution.
        Cache tiles locally to avoid re-fetching during demo.
        """
        ...
```

### 2b — Vessel detection on SAR tiles

**Do not attempt to train a model. Use one of these pre-trained approaches, in priority order:**

**Option A (recommended):** Use the **CFAR (Constant False Alarm Rate)** algorithm for ship detection — this is the standard operational algorithm used by coast guards worldwide, implemented in `pyradar` or manually in numpy. It works on raw SAR backscatter, requires no GPU, runs in seconds. False positive rate is manageable for a demo.

```python
import numpy as np
from scipy import ndimage

def cfar_vessel_detection(
    sar_array: np.ndarray,
    guard_cells: int = 2,
    training_cells: int = 4,
    false_alarm_rate: float = 1e-4
) -> list[dict]:
    """
    CFAR detector for SAR vessel detection.
    Returns list of detections: {row, col, confidence, bbox_pixels}
    """
    # Implementation: sliding window, compute local threshold,
    # flag pixels exceeding threshold as vessel candidates,
    # cluster adjacent flagged pixels into vessel bounding boxes.
    # Convert pixel coordinates to lat/lon using rasterio transform.
    ...
```

**Option B (GPU available):** Download pre-trained YOLO weights from the **SAR-Ship dataset** (public, free, hosted on GitHub: `github.com/CAESAR-Radi/SAR-Ship-Dataset`). This gives you better accuracy at the cost of requiring CUDA.

### 2c — AIS cross-reference for dark vessel detection

```python
import aiohttp
import asyncio

class AISStreamClient:
    """
    AISStream.io — free WebSocket API for real-time AIS.
    For historical AIS (last 7 days), use MarineTraffic free tier
    or cache live AIS during development.
    
    Free tier limits: 1 connection, ~1000 messages/min — sufficient.
    """
    WS_URL = "wss://stream.aisstream.io/v0/stream"

    async def get_vessels_in_bbox(
        self,
        bbox: tuple[float, float, float, float],  # (min_lon, min_lat, max_lon, max_lat)
        time_from: datetime,
        time_to: datetime
    ) -> list[dict]:
        """
        Returns list of AIS records:
        {
            mmsi: str,
            vessel_name: str,
            lat: float,
            lon: float,
            timestamp: datetime,
            vessel_type: str,
            flag: str
        }
        """
        ...

def detect_dark_vessels(
    sar_detections: list[dict],
    ais_vessels: list[dict],
    time_tolerance_minutes: int = 30,
    spatial_tolerance_km: float = 2.0
) -> list[dict]:
    """
    For each SAR detection, check if any AIS vessel was within
    spatial_tolerance_km at approximately the same time.
    
    If no AIS match: flag as AIS_DARK with confidence score.
    Confidence formula:
        base = 0.7
        + 0.1 if vessel size > 100m (from SAR bounding box)
        + 0.1 if in contested area (EEZ boundary polygon check)
        + 0.1 if time is 00:00-06:00 UTC (nighttime evasion pattern)
    
    Returns: list of dark vessel events with confidence scores.
    """
    ...
```

---

## COMPONENT 3: THE OSINT SENSOR

**File:** `backend/sensors/osint.py`

### 3a — GDELT

```python
from gdelt import gdelt as GDELT
import pandas as pd

class GDELTSensor:
    """
    GDELT 2.0 Events database.
    Free. No API key. Updated every 15 minutes.
    Query via Google BigQuery free tier (1TB/month) or direct CSV download.
    
    For the demo: use direct CSV download for simplicity.
    GDELT publishes a master file index at:
    http://data.gdeltproject.org/gdeltv2/masterfilelist.txt
    """

    RELEVANT_CAMEO_CODES = [
        "172",  # Appeal for military cooperation
        "173",  # Appeal for military action
        "190",  # Use unconventional mass violence
        "195",  # Provide military aid
    ]
    
    GREECE_FIPS = "GR"
    TURKEY_FIPS = "TU"

    async def fetch_events(
        self,
        time_from: datetime,
        time_to: datetime,
        actor_countries: list[str] = ["GR", "TU"],
        keywords: list[str] = ["vessel", "maritime", "aegean", "EEZ",
                                "territorial", "σκάφος", "Αιγαίο"]
    ) -> list[dict]:
        """
        Returns structured events:
        {
            event_id: str,
            date: datetime,
            actor1: str,
            actor2: str,
            event_type: str,
            cameo_code: str,
            lat: float,
            lon: float,
            source_url: str,
            source_name: str,
            goldstein_scale: float,  # -10 to +10, conflict intensity
            mentions: int             # How many articles mention this event
        }
        """
        ...
```

### 3b — Telegram monitoring

```python
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest

# Telegram API credentials: register at my.telegram.org — FREE
# APP_ID and APP_HASH go in .env

# Pre-curated list of public channels relevant to Greek/Aegean monitoring
# These are all publicly visible channels — no privacy implications
MONITORED_CHANNELS = [
    "@aegeanwatch",          # Maritime activity monitoring
    "@greekmilitary",        # Greek military news
    "@turkishnavy_news",     # Turkish naval activity (public)
    "@southeasteurope",      # Regional geopolitics
    # Add more during development based on discovery
]

class TelegramSensor:
    async def fetch_messages(
        self,
        channels: list[str],
        time_from: datetime,
        time_to: datetime,
        keywords: list[str]
    ) -> list[dict]:
        """
        Returns:
        {
            message_id: str,
            channel: str,
            channel_verified: bool,
            text: str,
            language: str,      # detected via langdetect
            timestamp: datetime,
            views: int,
            forwards: int,
            has_media: bool,
            entities_extracted: list[dict]  # filled by linguist agent
        }
        IMPORTANT: Store raw messages. NER runs in the linguist agent,
        not here. Sensors collect. Agents reason.
        """
        ...
```

### 3c — OpenSky Network

```python
from opensky_api import OpenSkyApi

class AirspaceSensor:
    """
    OpenSky Network — free REST API for ADS-B flight data.
    Historical data requires free account registration.
    State vectors (current positions) require no auth.
    """

    SUSPICIOUS_PATTERNS = [
        "no_callsign",           # Military often suppress callsign
        "track_change_>45deg",   # Rapid heading change
        "altitude_drop_>5000ft", # Rapid descent (potential surveillance)
        "orbit_pattern",         # Circular flight = ISR/surveillance
    ]

    async def fetch_flights(
        self,
        bbox: tuple,
        time_from: datetime,
        time_to: datetime
    ) -> list[dict]:
        ...
```

---

## COMPONENT 4: THE FUSION ENGINE

**File:** `backend/sensors/fusion.py`

This is the most critical engineering component. It converts raw sensor outputs into correlated events in the knowledge graph.

```python
from shapely.geometry import Point
from datetime import timedelta
import networkx as nx

class FusionEngine:
    """
    Spatiotemporal correlation engine.
    
    Algorithm:
    1. For each sensor event, create a spatiotemporal "bubble":
       - Geospatial events: radius=5km, window=±2h
       - GDELT events: radius=50km (news is less precise), window=±12h
       - Telegram events: radius=100km (social is least precise), window=±24h
    
    2. For each pair of events from different sensors, compute
       a correlation score:
         spatial_score = 1 - (distance / max_radius)
         temporal_score = 1 - (time_diff / max_window)
         corr_score = (spatial_score * 0.6) + (temporal_score * 0.4)
    
    3. Events with corr_score > 0.5 get a CORROBORATES edge in the graph.
    
    4. Cluster corroborated events into "Composite Events" — these
       are what the agents reason over.
    
    5. Each Composite Event has:
       - source_nodes: list of constituent events
       - corroboration_count: int (how many independent sources)
       - confidence: float (based on source diversity + corr_scores)
       - threat_grade: AMBER | RED | GREEN
    
    Threat grade assignment:
       GREEN: single source, low goldstein_scale
       AMBER: 2+ sources OR high goldstein_scale
       RED: 3+ sources AND AIS-dark vessel AND high goldstein_scale
    """
    
    SPATIAL_TOLERANCES = {
        "geospatial": 5.0,   # km
        "gdelt": 50.0,
        "telegram": 100.0,
        "airspace": 10.0
    }
    
    TEMPORAL_TOLERANCES = {
        "geospatial": 2,     # hours
        "gdelt": 12,
        "telegram": 24,
        "airspace": 1
    }

    def fuse(
        self,
        geospatial_events: list[dict],
        osint_events: list[dict],
        airspace_events: list[dict]
    ) -> list[CompositeEvent]:
        ...
```

---

## COMPONENT 5: THE KNOWLEDGE GRAPH

**File:** `backend/graph/schema.py`

### Node types and their mandatory properties

```
(:Watch {
    id: string,
    query: string,
    region: string,
    created_at: datetime
})

(:Vessel {
    id: string,           # Generated or MMSI if AIS-matched
    lat: float,
    lon: float,
    timestamp: datetime,
    detection_source: string,   # "SAR" | "AIS" | "both"
    ais_status: string,         # "broadcasting" | "dark" | "unknown"
    confidence: float,
    sar_tile_id: string,        # FK to evidence
    mmsi: string,               # nullable — if AIS-matched
    vessel_name: string,        # nullable
    flag: string                # nullable
})

(:NewsEvent {
    id: string,
    source_url: string,
    source_name: string,
    headline: string,
    timestamp: datetime,
    lat: float,               # GDELT geolocation
    lon: float,
    goldstein_scale: float,
    cameo_code: string,
    language: string
})

(:SocialSignal {
    id: string,
    channel: string,
    message_id: string,
    text: string,
    timestamp: datetime,
    language: string,
    views: int,
    forwards: int
})

(:CompositeEvent {
    id: string,
    threat_grade: string,       # GREEN | AMBER | RED
    confidence: float,
    corroboration_count: int,
    summary: string,            # One sentence, generated by supervisor
    created_at: datetime
})

(:BriefSection {
    id: string,
    section_type: string,       # BLUF | KEY_JUDGMENT | SUPPORTING | DEVILS_ADVOCATE | RECOMMENDATION
    text: string,
    citation_node_ids: list[string],  # THE KEY FIELD — maps to source nodes
    confidence: float,
    agent_source: string        # Which agent produced this
})

(:AuditEntry {
    id: string,
    timestamp: datetime,
    action_type: string,
    actor: string,              # "geospatial_agent" | "osint_agent" | analyst email
    input_hash: string,
    output_hash: string,
    previous_hash: string,      # Merkle chain
    chain_valid: bool
})
```

### Edge types

```
(Watch)-[:TRIGGERED {at: datetime}]->(CompositeEvent)
(CompositeEvent)-[:COMPOSED_OF {corr_score: float}]->(Vessel)
(CompositeEvent)-[:COMPOSED_OF {corr_score: float}]->(NewsEvent)
(CompositeEvent)-[:COMPOSED_OF {corr_score: float}]->(SocialSignal)
(Vessel)-[:CORROBORATES {score: float}]->(NewsEvent)
(NewsEvent)-[:CORROBORATES {score: float}]->(SocialSignal)
(BriefSection)-[:CITES {node_type: string}]->(Vessel)
(BriefSection)-[:CITES {node_type: string}]->(NewsEvent)
(BriefSection)-[:CITES {node_type: string}]->(SocialSignal)
(BriefSection)-[:CITES {node_type: string}]->(CompositeEvent)
```

### Critical Cypher queries — implement all of these

```cypher
-- Get full citation chain for a brief section (THE DEMO MOMENT)
MATCH (bs:BriefSection {id: $section_id})-[:CITES]->(source)
OPTIONAL MATCH (source)-[:COMPOSED_OF*0..2]-(evidence)
RETURN bs, source, collect(evidence) as evidence_chain

-- Get all events for a Watch
MATCH (w:Watch {id: $watch_id})-[:TRIGGERED]->(ce:CompositeEvent)
-[:COMPOSED_OF]->(source)
RETURN ce, collect(source) as sources
ORDER BY ce.confidence DESC

-- Get corroboration network for map visualization
MATCH (ce:CompositeEvent {id: $event_id})-[:COMPOSED_OF]->(source)
RETURN ce, source, source.lat, source.lon, source.detection_source

-- Audit chain verification
MATCH (a:AuditEntry)
WHERE a.timestamp >= datetime($from)
RETURN a ORDER BY a.timestamp
-- Then verify hash chain in Python
```

---

## COMPONENT 6: THE MULTI-AGENT REASONING LAYER

**File:** `backend/agents/`

### Architecture: Sequential with adversarial review

```
Watch → GeospatialAgent → OSINTAgent → LinguistAgent
                                              ↓
                                    DevilsAdvocateAgent
                                              ↓
                                      SupervisorAgent → Brief
```

**All agents use Ollama with tool calling.** Each agent has:
1. A system prompt (in `prompts/`)
2. A set of tools (Cypher queries via `graph/queries.py`)
3. A structured output schema (Pydantic model)
4. A maximum token budget (enforce this — prevents runaway generation)

### Base agent pattern

```python
from langchain_ollama import ChatOllama
from langchain.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel
import json

class AgentOutput(BaseModel):
    analysis: str
    key_findings: list[str]
    confidence: float
    citation_node_ids: list[str]   # MANDATORY — no orphan claims
    uncertainty_flags: list[str]   # What the agent is NOT sure about

class BaseAgent:
    MODEL = "llama3.1:8b"
    MAX_TOKENS = 1024
    TEMPERATURE = 0.1    # Low temperature for factual analysis

    def __init__(self, graph_client, audit_logger):
        self.graph = graph_client
        self.audit = audit_logger
        self.llm = ChatOllama(
            model=self.MODEL,
            temperature=self.TEMPERATURE,
            num_predict=self.MAX_TOKENS
        )

    def get_tools(self) -> list:
        raise NotImplementedError

    def get_system_prompt(self) -> str:
        raise NotImplementedError

    async def run(self, composite_event: CompositeEvent) -> AgentOutput:
        # 1. Fetch relevant graph data using tools
        # 2. Run LLM with system prompt + graph data
        # 3. Parse output into AgentOutput
        # 4. VALIDATE: every claim in key_findings must have
        #    at least one citation_node_id
        # 5. Log to audit trail
        # 6. Return AgentOutput
        ...
```

### Geospatial Agent system prompt

```
You are a maritime intelligence analyst specializing in Aegean Sea 
vessel activity. You have access to satellite SAR detection data and 
AIS vessel records via tools.

Your task: analyze the vessel detections and AIS data for the given 
composite event. Produce a structured assessment.

MANDATORY RULES:
1. Every statement you make must cite a specific node ID from the 
   knowledge graph. Format: [NODE:vessel_id_123]
2. Do not speculate beyond what the data shows.
3. Express confidence as a float 0.0-1.0, not words.
4. Flag explicitly what data is MISSING that would change your assessment.
5. Output ONLY valid JSON matching the AgentOutput schema.

Available tools:
- get_vessel_details(vessel_id): Full vessel record + SAR tile metadata
- get_ais_history(mmsi, bbox, time_range): AIS track for a vessel
- get_area_baseline(bbox, days_back): Historical vessel density for 
  this area (to detect anomalies vs baseline)
- check_vessel_registry(mmsi): Cross-reference against known vessel DB
```

### Devil's Advocate Agent system prompt

```
You are a skeptical analyst whose ONLY job is to challenge the 
assessments produced by other agents. You are not trying to be 
right — you are trying to find every reason the other analysts 
might be wrong.

You will receive the outputs of the Geospatial Agent and OSINT Agent.
Your task: produce the strongest possible counter-assessment.

For each key finding, you must attempt to provide:
1. An alternative innocent explanation
2. A data quality challenge (could the source be wrong?)
3. A methodological challenge (could the correlation be spurious?)

You are REQUIRED to find at least one challenge per key finding.
If you genuinely cannot challenge something, say so explicitly and 
explain why — do not manufacture false challenges.

MANDATORY RULES:
- Same citation requirements as all other agents
- Output must include a field: "devil_confidence" — your confidence 
  that the primary assessment is WRONG (not right)
- This field will be shown to the analyst as a "counter-signal"
```

### Supervisor Agent system prompt

```
You are the senior intelligence officer who produces the final 
intelligence brief. You receive the outputs of all specialist agents.

Your output format is STRICT. Produce a JSON object with these 
exact sections:

{
  "bluf": {
    "text": "One sentence. Bottom Line Up Front.",
    "citation_node_ids": [...],
    "confidence": 0.0-1.0
  },
  "key_judgments": [
    {
      "text": "One judgment per item. Maximum 2 sentences.",
      "citation_node_ids": [...],
      "confidence": 0.0-1.0,
      "agent_source": "geospatial|osint|fused"
    }
  ],
  "supporting_evidence": [
    {
      "text": "Supporting detail.",
      "citation_node_ids": [...],
      "source_type": "SAR|AIS|GDELT|TELEGRAM|OPENSKY"
    }
  ],
  "devils_advocate": {
    "text": "Strongest counter-case. Do not soften this.",
    "devil_confidence": 0.0-1.0,
    "citation_node_ids": [...]
  },
  "recommended_action": {
    "text": "One concrete action for the analyst.",
    "urgency": "ROUTINE|PRIORITY|IMMEDIATE"
  },
  "metadata": {
    "sources_count": int,
    "time_range": {...},
    "processing_duration_seconds": float,
    "agents_consulted": [...]
  }
}

CRITICAL: Every "text" field that makes a factual claim MUST have 
at least one entry in citation_node_ids. An uncited claim is an 
invalid output. If you cannot cite it, do not say it.
```

---

## COMPONENT 7: THE AUDIT LOGGER

**File:** `backend/audit/logger.py`

```python
import hashlib
import json
from datetime import datetime
from pydantic import BaseModel

class AuditEntry(BaseModel):
    id: str
    timestamp: datetime
    action_type: str
    actor: str
    payload_hash: str
    previous_hash: str
    chain_hash: str     # hash(payload_hash + previous_hash)

class MerkleAuditLogger:
    """
    Append-only audit log with Merkle chain.
    Every entry hashes its own content + the previous entry's hash.
    This means:
    - You cannot modify a past entry without breaking all subsequent hashes
    - The chain can be verified in O(n) by any third party
    - Satisfies EU AI Act Article 12 (record-keeping for high-risk AI)
    - Satisfies EYP brief requirement for ιχνηλασιμότητα
    
    Storage: Write to Neo4j AuditEntry nodes AND to a local JSONL file.
    Two independent stores makes tampering harder.
    """

    def __init__(self, graph_client, log_file_path: str):
        self.graph = graph_client
        self.log_file = log_file_path
        self._last_hash = "GENESIS"  # Loaded from DB on startup

    async def log(
        self,
        action_type: str,
        actor: str,
        payload: dict
    ) -> AuditEntry:
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        chain_hash = hashlib.sha256(
            (payload_hash + self._last_hash).encode()
        ).hexdigest()

        entry = AuditEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            action_type=action_type,
            actor=actor,
            payload_hash=payload_hash,
            previous_hash=self._last_hash,
            chain_hash=chain_hash
        )

        # Write to both stores atomically (best effort)
        await self._write_neo4j(entry)
        await self._write_file(entry)
        self._last_hash = chain_hash
        return entry

    def verify_chain(self, entries: list[AuditEntry]) -> bool:
        """Call this during demo — proves integrity to judges."""
        ...
```

---

## COMPONENT 8: THE API LAYER

**File:** `backend/api/`

### WebSocket for real-time progress during processing

```python
# backend/api/ws.py
# This is critical for the demo — judges see the pipeline running live

@router.websocket("/ws/watch/{watch_id}")
async def watch_progress(websocket: WebSocket, watch_id: str):
    """
    Streams processing events to the frontend as Server-Sent Events.
    Messages:
    {
        "stage": "geospatial_sensor|osint_sensor|fusion|graph_ingestion|
                  geospatial_agent|osint_agent|linguist_agent|
                  devils_advocate|supervisor|complete",
        "status": "started|progress|complete|error",
        "detail": "string",
        "progress_pct": 0-100
    }
    """
```

### Citation chain endpoint (the gold-medal API)

```python
# backend/api/briefs.py

@router.get("/briefs/{brief_id}/citation/{section_id}")
async def get_citation_chain(brief_id: str, section_id: str):
    """
    Returns the full provenance chain for a brief section.
    This is what fires when a judge clicks a sentence.
    
    Response:
    {
        "section": BriefSection,
        "source_nodes": [
            {
                "node_id": str,
                "node_type": "Vessel|NewsEvent|SocialSignal",
                "properties": dict,
                "raw_evidence": {
                    "type": "SAR_TILE|ARTICLE_URL|TELEGRAM_MESSAGE",
                    "content": str | bytes,  # Base64 for images
                    "metadata": dict
                },
                "map_highlight": {
                    "lat": float,
                    "lon": float,
                    "radius_km": float
                },
                "graph_highlight": {
                    "node_id": str,
                    "connected_node_ids": list[str]
                }
            }
        ],
        "corroboration_chain": [...],   # The full evidence path
        "confidence_breakdown": {...}   # How confidence was computed
    }
    """
```

---

## COMPONENT 9: THE FRONTEND

### The three-panel layout

```tsx
// src/App.tsx
// Layout: full viewport, no scrolling
// Left 30%: MapPanel
// Center 40%: BriefPanel
// Right 30%: GraphPanel
// Bottom strip: AuditLog + ProgressStream

const App = () => {
  const { activeCitation, setActiveCitation } = useDamoclesStore();

  return (
    <div className="h-screen w-screen flex flex-col bg-gray-950">
      {/* Top: Watch input */}
      <WatchInput />

      {/* Main three-panel area */}
      <div className="flex-1 flex overflow-hidden">
        <MapPanel
          className="w-[30%]"
          highlightedFeature={activeCitation?.map_highlight}
        />
        <BriefPanel
          className="w-[40%]"
          onCitationClick={setActiveCitation}
        />
        <GraphPanel
          className="w-[30%]"
          highlightedNodes={activeCitation?.graph_highlight}
        />
      </div>

      {/* Bottom: Audit + Progress */}
      <div className="h-32 flex border-t border-gray-800">
        <ProgressStream className="w-1/2" />
        <AuditLog className="w-1/2" />
      </div>
    </div>
  );
};
```

### The citation click handler — implement this perfectly

```tsx
// src/components/BriefPanel.tsx
// This is the demo moment. It must be instant, obvious, and beautiful.

const CitableText: React.FC<{
  text: string;
  citationNodeIds: string[];
  sectionId: string;
  confidence: number;
}> = ({ text, citationNodeIds, sectionId, confidence }) => {
  const { setActiveCitation } = useDamoclesStore();

  const handleClick = async () => {
    // 1. Immediately highlight this text (optimistic UI)
    // 2. Fetch citation chain from API
    // 3. Simultaneously:
    //    a. Map flies to source location
    //    b. Graph highlights source nodes
    //    c. EvidenceModal opens with raw source
    // This must happen within 200ms of click for demo impact.

    const chain = await fetchCitationChain(sectionId);
    setActiveCitation(chain);
  };

  return (
    <span
      onClick={handleClick}
      className={`
        cursor-pointer underline decoration-dotted
        ${confidence > 0.8 ? 'text-green-300' :
          confidence > 0.6 ? 'text-yellow-300' : 'text-red-300'}
        hover:bg-white/10 rounded px-0.5 transition-all duration-150
      `}
      title={`Confidence: ${(confidence * 100).toFixed(0)}% — click for sources`}
    >
      {text}
    </span>
  );
};
```

### The map panel — Leaflet with dark tiles

```tsx
// src/components/MapPanel.tsx
// Use Stamen Toner or CartoDB Dark Matter tiles for a serious, dark UI

const MAP_TILES = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";

// Greek EEZ overlay: load from /data/geojson/greek_eez.geojson
// Render as a semi-transparent blue polygon

// Vessel detections: red circles, sized by confidence
// AIS-dark vessels: pulsing red circles (CSS animation)
// News events: orange triangles
// Telegram signals: purple squares

// When citation is active:
//   - Non-relevant features fade to 20% opacity
//   - Relevant feature pulses and shows popup
//   - Map flies to relevant feature over 800ms
```

### The evidence modal

```tsx
// src/components/EvidenceModal.tsx
// Opens when judge clicks a cited sentence
// Shows raw evidence:
//   For SAR tile: grayscale radar image with vessel bounding box highlighted
//   For GDELT event: article URL, headline, timestamp, goldstein scale
//   For Telegram: message text, channel, timestamp, views/forwards
// IMPORTANT: show the raw data, not a summary of the raw data
// The judge needs to see that this is real, not manufactured
```

---

## COMPONENT 10: THE DEMO DATA PIPELINE

**File:** `scripts/seed_neo4j.py`

**Critical decision:** Do not rely on live data for the demo. Here is why:
- Sentinel-1 has a 6-day revisit. If you demo on a Tuesday there might be no fresh tile.
- GDELT may have no relevant Greece/Turkey events in the last 7 days on demo day.
- Telegram channels may be quiet.

**The professional approach:** Pre-process a real historical scenario (e.g., March-April 2024, during the period of heightened Aegean tensions), load it into Neo4j, and demo against that. The data is real. The processing is real. The scenario is historical but genuine. When judges ask, say: *"This demo runs on a historical scenario from March 2024. In production deployment the same pipeline runs on live data with a 15-minute lag."* No judge will penalize this. Every professional demo works this way.

```python
# scripts/seed_neo4j.py
"""
Pre-loads a specific historical scenario for the demo.

Scenario: "March 14-20, 2024 — Aegean EEZ Activity"
This was a period of documented Turkish research vessel activity
near Dodecanese islands.

Data sources for seeding:
1. Download Sentinel-1 tiles: Copernicus archive (free, historical)
2. Download GDELT events: query BigQuery for this date range (free)
3. Sample Telegram messages: manually curated from public channel archives
4. AIS data: use MarineTraffic free tier for vessel positions

The seed script:
1. Downloads/processes all data for the scenario
2. Runs it through the full pipeline (geospatial sensor → fusion → graph)
3. Pre-generates the briefs and caches them
4. Stores everything in Neo4j

Demo then queries this pre-loaded data — instant responses.
"""
```

---

## BUILD SEQUENCE — 3 WEEKS

### Week 1: Data pipeline + graph (Days 1-7)
**Goal: data flows from sensors into Neo4j, fusion works, graph is queryable.**

Day 1-2: Project setup, Neo4j schema, base models, start.sh
Day 3-4: Geospatial sensor — Sentinel-1 download + CFAR vessel detection
Day 5: AIS cross-reference + dark vessel detection
Day 6: GDELT + Telegram sensors
Day 7: Fusion engine + graph ingestion + verify_sources.py passes

**End of week 1 test:** Run `scripts/seed_neo4j.py` for the March 2024 scenario. Neo4j Browser shows a populated graph with vessels, news events, social signals, and composite events all connected. Query the citation chain manually in Cypher.

---

### Week 2: Agent layer + API (Days 8-14)
**Goal: agents produce structured briefs with citations, API is complete.**

Day 8: Ollama setup + base agent + GeospatialAgent
Day 9: OSINTAgent + LinguistAgent (Greek NER)
Day 10: Devil's Advocate Agent (this is the hardest — iterate on the prompt)
Day 11: Supervisor Agent + brief assembly
Day 12: FastAPI backend — all endpoints including WebSocket
Day 13: Audit logger — Merkle chain, verify function
Day 14: Integration test — full pipeline end-to-end, all agents, complete brief with citations

**End of week 2 test:** POST a Watch for the seeded scenario. Receive a complete JSON brief. Every key_judgment has citation_node_ids that resolve to real graph nodes. Devil's Advocate fires with at least one challenge. Audit chain verifies clean.

---

### Week 3: Frontend + demo polish (Days 15-21)
**Goal: the demo works, looks good, and the citation click is instant.**

Day 15-16: Frontend scaffold + three-panel layout + map tiles
Day 17: Brief panel with CitableText + confidence color coding
Day 18: Graph panel (Cytoscape) + map-graph synchronization
Day 19: Citation click handler + EvidenceModal — THIS IS THE PRIORITY
Day 20: Progress WebSocket + audit log panel + overall UX polish
Day 21: Full dry-run of the 5-minute demo. Time it. Fix what breaks.

**End of week 3 test:** Complete dry run. From "Aegean — last 7 days" to full brief: under 60 seconds (acceptable for pre-loaded data). Citation click to evidence modal: under 200ms. Devil's Advocate visible and readable. Audit log scrolling live during processing.

---

## PROMPT ENGINEERING RULES FOR ALL AGENTS

Apply these to every agent prompt, without exception:

1. **Schema enforcement:** End every prompt with "Output ONLY valid JSON matching this schema: [schema]. Do not add any text before or after the JSON."

2. **Citation enforcement:** "Every factual claim must include at least one citation_node_id from the knowledge graph. An output with uncited claims is INVALID and will be rejected."

3. **Uncertainty enforcement:** "Include a field 'uncertainty_flags' listing at minimum one thing you are uncertain about. An empty uncertainty_flags field is INVALID — there is always uncertainty."

4. **Temperature:** Use 0.1 for all factual agents. Use 0.3 for Devil's Advocate (needs slightly more creative counter-arguments). Use 0.0 for the Supervisor (pure synthesis, no creativity needed).

5. **Context window management:** Each agent receives only the graph data it needs — not the full graph. Use the Cypher query library to fetch targeted subgraphs. Never pass more than 4,000 tokens of context to a local 8B model.

6. **Retry logic:** If an agent produces invalid JSON or uncited claims, retry once with an error correction prompt: "Your previous output had this error: [error]. Produce a corrected output."

---

## TESTING STRATEGY

### The gold-medal test (implement first)

```python
# tests/test_citation_chain.py

async def test_citation_chain_completeness():
    """
    For every sentence in a generated brief,
    every citation_node_id must:
    1. Exist in Neo4j
    2. Be reachable via the citation chain endpoint
    3. Have a lat/lon for map highlighting
    4. Have raw_evidence that can be returned to the frontend
    
    If this test passes, the demo moment works.
    If this test fails, you don't have a gold medal.
    """
    brief = await generate_brief_for_demo_scenario()
    for section in brief.all_sections():
        for node_id in section.citation_node_ids:
            chain = await get_citation_chain(brief.id, section.id)
            source = next(n for n in chain.source_nodes
                         if n.node_id == node_id)
            assert source is not None, f"Node {node_id} not found"
            assert source.map_highlight.lat is not None
            assert source.raw_evidence is not None

async def test_devils_advocate_fires():
    """
    For every brief, the Devil's Advocate section must:
    1. Exist and be non-empty
    2. Contradict at least one key_judgment
    3. Have its own citation_node_ids (can't challenge with nothing)
    """
    ...

async def test_audit_chain_integrity():
    """
    After a full pipeline run, the Merkle chain must verify clean.
    """
    entries = await get_audit_entries_for_run()
    assert verify_merkle_chain(entries) == True
```

---

## ENVIRONMENT VARIABLES

```bash
# .env.example — copy to .env and fill in

# ─── LLM PROVIDER ────────────────────────────────────────────────────────────
# Switch between providers without any code changes.
# gemini = development on Windows (fast, cheap, cloud)
# ollama = demo and GCP production (local, sovereign, no external calls)
LLM_PROVIDER=gemini

# Google Gemini (development only — register free at aistudio.google.com)
# Free tier: 15 RPM, 1M tokens/day. More than enough for development.
GEMINI_API_KEY=

# Ollama (demo/production — only needed when LLM_PROVIDER=ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
# For Devil's Advocate agent (slightly more creative model):
OLLAMA_DEVIL_MODEL=qwen2.5:7b

# ─── GEOSPATIAL ──────────────────────────────────────────────────────────────
# Copernicus / Sentinel Hub (free account at dataspace.copernicus.eu)
SENTINELHUB_CLIENT_ID=
SENTINELHUB_CLIENT_SECRET=

# ─── OSINT ────────────────────────────────────────────────────────────────────
# Telegram (register app at my.telegram.org — free)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

# AISStream (register at aisstream.io — free tier)
AISSTREAM_API_KEY=

# ─── GRAPH DATABASE ───────────────────────────────────────────────────────────
# Neo4j — running via Docker on Windows, systemd on GCP
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME_neo4j_password

# ─── APPLICATION ──────────────────────────────────────────────────────────────
DAMOCLES_ENV=development          # development | production
LOG_LEVEL=INFO
DEMO_MODE=true                    # true = uses seeded data, false = live APIs
GCP_PROJECT_ID=                   # Set when deploying to GCP
```

---

## THE START SCRIPTS

### Windows — `start.ps1` (PowerShell)

```powershell
# start.ps1 — Windows development startup
# Usage: .\start.ps1 [--seed]

param([switch]$seed)

Write-Host "Damocles starting..." -ForegroundColor Cyan

# Check Docker is running (needed for Neo4j)
try {
    docker info | Out-Null
} catch {
    Write-Host "Docker Desktop is not running. Please start it." -ForegroundColor Red
    exit 1
}

# Start Neo4j via Docker Compose
Write-Host "Starting Neo4j..." -ForegroundColor Yellow
docker compose -f docker/neo4j/docker-compose.yml up -d

# Wait for Neo4j to be ready (it takes ~15 seconds on first start)
Write-Host "Waiting for Neo4j to be ready..."
$maxWait = 30
$waited = 0
do {
    Start-Sleep -Seconds 2
    $waited += 2
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:7474" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { break }
    } catch {}
} while ($waited -lt $maxWait)

# Install Python dependencies (uv must be installed: pip install uv)
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
uv sync

# Install spaCy Greek model
Write-Host "Checking spaCy models..."
python -m spacy info el_core_news_lg 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m spacy download el_core_news_lg
}

# Seed demo data if requested
if ($seed) {
    Write-Host "Seeding demo scenario (March 2024 Aegean)..." -ForegroundColor Yellow
    uv run python scripts/seed_neo4j.py
}

# Start backend (in new PowerShell window)
Write-Host "Starting backend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

# Start frontend (in new PowerShell window)
Write-Host "Starting frontend..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd frontend; npm install; npm run dev"

Write-Host ""
Write-Host "Damocles is running." -ForegroundColor Green
Write-Host "  Frontend:  http://localhost:5173" -ForegroundColor White
Write-Host "  API:       http://localhost:8000" -ForegroundColor White
Write-Host "  API docs:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Neo4j:     http://localhost:7474" -ForegroundColor White
Write-Host ""
Write-Host "  LLM Provider: $env:LLM_PROVIDER" -ForegroundColor Magenta
Write-Host "  Demo Mode:    $env:DEMO_MODE" -ForegroundColor Magenta
Write-Host ""
Write-Host "  Primary demo query: 'Aegean -- last 7 days'" -ForegroundColor Cyan
```

### Linux / GCP — `start.sh` (bash)

```bash
#!/bin/bash
# start.sh — Linux/GCP startup
# Usage: ./start.sh [--seed]

set -e

echo "Damocles starting..."

# Check dependencies
command -v docker >/dev/null 2>&1 || { echo "Docker not found. Run: scripts/setup_linux.sh"; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "uv not found. Run: pip install uv"; exit 1; }

# Start Neo4j
echo "Starting Neo4j..."
docker compose -f docker/neo4j/docker-compose.yml up -d

# Wait for Neo4j
echo "Waiting for Neo4j..."
until curl -sf http://localhost:7474 > /dev/null; do sleep 2; done

# Install dependencies
uv sync

# spaCy Greek model
python -m spacy info el_core_news_lg > /dev/null 2>&1 || python -m spacy download el_core_news_lg

# Seed if requested
if [ "$1" == "--seed" ]; then
    echo "Seeding demo scenario..."
    uv run python scripts/seed_neo4j.py
fi

# Start backend
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &

# Start frontend (dev) or serve static build (production)
if [ "$DAMOCLES_ENV" == "production" ]; then
    cd frontend && npm run build
    # Nginx serves the built files — see scripts/setup_linux.sh for Nginx config
else
    cd frontend && npm install && npm run dev &
fi

echo ""
echo "Damocles is running."
echo "  Frontend:  http://localhost:5173"
echo "  API:       http://localhost:8000"
echo "  Neo4j:     http://localhost:7474"
echo "  LLM:       ${LLM_PROVIDER:-not set}"
```

### Windows one-time setup — `scripts/setup_windows.ps1`

```powershell
# scripts/setup_windows.ps1
# Run once to set up the Windows development environment

Write-Host "Setting up Damocles development environment on Windows..." -ForegroundColor Cyan

# Install uv (Python package manager)
pip install uv

# Install Node.js dependencies check
node --version 2>$null || Write-Host "Install Node.js from https://nodejs.org" -ForegroundColor Red

# Install Docker Desktop check
docker --version 2>$null || Write-Host "Install Docker Desktop from https://docker.com" -ForegroundColor Red

# Create .env from example
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env created from .env.example. Fill in your API keys." -ForegroundColor Yellow
}

# Pull Neo4j image
docker pull neo4j:5.24-community

# Install Python dependencies
uv sync

# Install spaCy models
python -m spacy download el_core_news_lg

Write-Host ""
Write-Host "Setup complete. Next steps:" -ForegroundColor Green
Write-Host "1. Edit .env and add your GEMINI_API_KEY" -ForegroundColor White
Write-Host "2. Run: .\start.ps1 --seed" -ForegroundColor White
Write-Host "3. Open http://localhost:5173" -ForegroundColor White
```

---

## WHAT THE AGENT SHOULD DO FIRST

When you receive this brief, execute in this exact order:

1. `mkdir damocles && cd damocles && git init`
2. Create the full directory structure using `mkdir` (use `New-Item -ItemType Directory` on Windows or `mkdir -p` on Linux)
3. Create `pyproject.toml` with exact dependencies
4. Create `package.json` for the frontend
5. Create `.env.example` — then immediately copy to `.env` and instruct the developer to add their `GEMINI_API_KEY`
6. Create `docker/neo4j/docker-compose.yml`
7. Create `start.ps1` and `start.sh`
8. Create `scripts/setup_windows.ps1`
9. **Create `backend/llm/` first — before any other backend code.** The LLM abstraction is the foundation. Nothing calls the LLM directly.
10. Create `backend/models/` — all Pydantic models
11. Create `backend/graph/schema.py` and `backend/graph/client.py`
12. Create `backend/watch_engine/parser.py` and `backend/watch_engine/registry.py`
13. Run `scripts/verify_sources.py` — write this script first, it tests all API connections
14. Then sensors, then agents, then API, then frontend

**Critical Windows-specific notes:**
- Use `pathlib.Path` everywhere — never string-concatenate paths
- Use `asyncio.run()` with `loop_factory=asyncio.DefaultEventLoopPolicy` if you hit Windows event loop issues with uvicorn
- If `rasterio` has Windows install issues, install via conda: `conda install -c conda-forge rasterio` or use the pre-built wheel from `https://github.com/cgohlke/geospatial-wheels`
- Neo4j runs in Docker — never assume a native `neo4j` command exists on Windows

**Do not write frontend code until the backend citation chain test passes.**

**Do not use Ollama during development — use Gemini. It is faster, requires no GPU, and the abstraction layer means zero changes when switching.**

---

## DEMO SCRIPT — 5 MINUTES EXACTLY

Practice this until it is muscle memory.

**[0:00]** "Good morning. Intelligence analysts today have a problem. There are 14,000 signals waiting in their queue. They will review 47 by end of shift. Damocles changes that number."

**[0:30]** Open the browser. Show the dark three-panel interface. Point to the chip buttons above the input: *"The analyst can launch a preset Watch — maritime, border, airspace, information — or type any free-text query. Nothing is locked."*

**[0:45]** Type: "Aegean — last 7 days." Hit enter. The progress stream fires — judges see each agent activating in real time. Say: *"Gemini during development, a local sovereign LLM in production. One environment variable. Zero code changes."*

**[1:30]** Brief appears. Say: "Damocles has fused satellite radar, maritime traffic data, international news, and regional social media. Three alerts. Top alert: AMBER."

**[2:00]** Click the BLUF sentence. Map flies to coordinates. Graph highlights source nodes. Evidence modal opens showing the SAR tile with bounding box. Say: *"That click just traversed three independent data sources and a knowledge graph. The analyst sees the chain of custody for every claim."*

**[2:30]** Say: "Every single claim traces to its source. Not a summary of a summary. A citation chain — the same standard you would expect in a court." Show one more citation click.

**[3:00]** Scroll to Devil's Advocate. Say: "But we don't just tell you what we found. We tell you why we might be wrong. Damocles institutionalizes skepticism. This is what real intelligence tradecraft looks like."

**[3:30]** Scroll to audit log. Say: "Every model call, every analyst action, hashed and chained. Any parliamentary committee can verify this log has not been tampered with."

**[4:00]** Show the graph panel. "47 nodes, 89 relationships, built in under 60 seconds from free, public, sovereign data. Nothing left Greek infrastructure."

**[4:15]** Type a second query: "Turkish research vessel activity last 30 days." Hit enter. Say: *"The Watch system accepts any query. The analyst is not limited to presets."* Let it run for 20 seconds then say: "New brief. Same pipeline. Different scope."

**[4:45]** Close with: "Palantir costs €3 million per deployment. Requires a US cloud. Cannot run in Greek. Damocles costs zero to run, runs on a €1,500 server, runs in Greek, and was built in three weeks by a Greek team. The question for EYP is not whether they can afford Damocles. The question is whether they can afford not to have it."

**[5:00]** Stop.

---

## PHASE 2 — CAPABILITY EXPANSION (Days 22-28)

After Day 21 the v1 platform is demo-ready: live pipeline, citation chain, audit log, three-panel UI. Phase 2 raises the ceiling on five axes the gold-medal narrative needs:

1. **Greece-wide standing coverage** — a daily 7-day full-territory scan whose results live in a persistent fact store. User watches become DB reads, not fresh API hits. This collapses cost (no re-fetch, no re-spend on LLM) and latency (sub-second brief refresh on cached scopes).
2. **AI-inferred Areas of Interest** — the supervisor doesn't just rank events; it draws polygons around emergent hotspots, names them in Greek + English, and persists them as first-class graph entities citable from briefs.
3. **Analyst-drawn polygons** — terra-draw on MapLibre. The analyst can ring any region, save it as an AoI, and use it as a filter for new watches. AoIs live in the same store as the AI ones — same schema, different `source`.
4. **WebGL graph at scale** — Cytoscape.js out, Sigma.js v3 + graphology in. Greece-wide scans produce graphs of 5k–20k nodes; we need 60fps pan/zoom and sub-100ms citation highlight.
5. **Map as the primary cognitive surface** — vessel trajectories with timestamp fade, semantic icon symbology, toggleable layers (AoI, SAR detections, news heatmap, vessel trails, flight tracks), satellite basemap, click-through to evidence on every shape.

### Phase 2 architecture commitments

- **Fact store: DuckDB + spatial extension.** Embedded, single Python dep, columnar (the right shape for "Greece × 7 days × 100k events" range queries), MIT, file-based — sovereignty-aligned. Schema lives in `backend/store/schema.sql`. Pairs with Parquet exports for cold archive and audit replay. Neo4j keeps its role: relationships and citation chain. DuckDB owns: raw sensor rows, materialized derivations (trajectories, hex-aggregations), AoI polygons.
- **Read-through pattern.** Every sensor gets a `cache_key` (sensor_name + bbox + time-bucket). On `fetch()`: check DuckDB → return cached rows if window is fresh (< TTL); else hit the upstream API, write to DuckDB, return. Sensors keep their public `fetch()` signature — caching is a base-class concern.
- **Greece scan scheduler.** APScheduler in the FastAPI lifespan. Daily 04:00 UTC: run a "greece_full_7d" watch covering bbox `(19.0, 34.5, 29.7, 41.8)` (Greek mainland + EEZ + Aegean + Ionian). Writes through to DuckDB. The frontend gets a dedicated "Standing coverage" panel showing scan freshness.
- **AoI inference.** HDBSCAN on composite-event lat/lon (`min_cluster_size=4`, `min_samples=2`). Each cluster → alpha-shape (alpha=0.5) — handles archipelago geometry better than convex hull. Naming: a small LLM pass with `(centroid, bbox, dominant_sources, dominant_threat_grade)` → `{name_el, name_en, brief_description}`. Persisted in DuckDB `aoi` table; mirrored as `(:AreaOfInterest)` nodes in Neo4j with `[:CONTAINS]` edges to composite events.
- **Graph rendering.** `sigma` v3 + `graphology` + `graphology-layout-forceatlas2`. Initial layout computed once on the worker; subsequent updates incremental. WebGL renderer with custom node program for citation-pulse halos. Viewport-based LOD: hide labels at low zoom, cluster nodes at world zoom.
- **Map drawing.** `terra-draw` (MIT, MapLibre-native). Analyst draws → polygon GeoJSON POSTed to `/api/aoi` → DuckDB → graph. Same render path as AI AoIs.
- **Rich map layers** (additive on the existing MapPanel):
  - Basemap toggle: dark-matter (default) ↔ ESA `s2cloudless` WMTS satellite mosaic.
  - AoI layer: polygon fill + outline, colour by source (`ai`=amber, `user`=cyan), label at centroid.
  - Vessel trail layer: per-MMSI polylines from a DuckDB materialized query, opacity decay over time.
  - SAR detection layer: circles sized by length_m, colour by dark_score.
  - News heatmap: hex-binned GDELT events, intensity by tone-magnitude.
  - Flight track layer: OpenSky polylines (when sensor active).
  - Layer panel UI in MapPanel right-rail: stack of toggles + opacity sliders.

### Day 22 — Persistence layer (DuckDB) + sensor write-through cache

**Goal:** every sensor fetch is mirrored into DuckDB. Re-running the same watch reads from cache. Greek-wide scans become possible without re-burning quota.

1. Add deps: `duckdb>=1.1.0`, `apscheduler>=3.10`, `shapely>=2.0`, `hdbscan>=0.8.40`, `alphashape>=1.3.1`. Update `pyproject.toml`.
2. New module `backend/store/`:
   - `schema.sql` — CREATE TABLE for `raw_ais`, `raw_news`, `raw_social`, `raw_sar`, `raw_flight`, `composite_events`, `aoi`, `scan_runs`. Use `INSTALL spatial; LOAD spatial;` for `GEOMETRY`/`ST_*` functions. Indices on `(time_bucket, h3_8)` and on `(mmsi, ts)` for trajectory reads.
   - `client.py` — `DuckDBStore` singleton with `connect()`, `upsert_*()`, `read_*()`, `cache_lookup(sensor, bbox, t_from, t_to)` methods. Connection per-thread (DuckDB's `cursor()` for concurrency).
   - `cache.py` — `CachedSensor` mixin: wraps `BaseSensor.fetch()`, computes a deterministic cache key, returns cached rows if `now - cached_at < ttl`. TTL per sensor: AIS 5min, GDELT 30min, SAR 6h, Telegram 10min.
3. Migrate sensors: `AISSensor`, `GDELTSensor`, `GeospatialSensor`, `TelegramSensor` extend `CachedSensor`. Each implements `_to_rows(events)` and `_from_rows(rows)`.
4. New endpoint `GET /api/store/stats` — row counts per table, freshest timestamp per sensor. Renders in a small "Data store" badge in the topbar.
5. Migration script `scripts/migrate_to_duckdb.py` — backfills any current Neo4j vessel/news/social rows into DuckDB so the cache starts warm.
6. Tests: `backend/tests/test_store.py` — round-trip `Vessel`/`NewsEvent` rows; `test_cache.py` — second `fetch()` hits the store, not the API (assert via mock-counter).

**Definition of done:** running `seed_neo4j.py` twice in a row: first run hits APIs, second run completes in < 5s with zero outbound HTTP. Verified via the existing audit metadata (the second run's `metadata.cache_hit=true`).

### Day 23 — Greece-wide standing scan

**Goal:** a scheduled job that keeps a 7-day rolling Greece-wide cache fresh; user watches read from it.

1. New module `backend/watch_engine/standing.py` — `StandingScanScheduler`:
   - APScheduler `AsyncIOScheduler` started in `main.py` lifespan.
   - Cron job `04:00 UTC` daily; runs `WatchExecutor` with `WatchSpec(name="greece_full_7d", bbox=GREECE_BBOX, time_window=timedelta(days=7), ...)`.
   - Writes a row to `scan_runs(scan_id, started_at, finished_at, sensor_counts, status)`.
2. `WatchExecutor.execute()` gains a `mode='live'|'cached'` parameter. `cached` reads from DuckDB instead of dispatching sensors; agents still re-run but on cached rows. New watches default to `mode='cached'` if a fresh standing scan covers their bbox/time window.
3. Endpoint `POST /api/standing/scan` — manual trigger (idempotent: returns the in-flight scan if one is running). `GET /api/standing/status` — most recent scan summary + freshness.
4. Frontend: new `StandingCoveragePanel` slot above ProgressStream — green dot + "Greece coverage: fresh (2h ago) · 12,847 events". Click → triggers manual scan with confirmation.
5. Cost guard: if a `mode='live'` watch is requested, log to audit; the audit verifier reports live-mode runs distinctly so cost overruns are visible.

**Definition of done:** start backend → scheduler triggers a scan within 30s on cold-boot if no fresh scan exists. New "Aegean — last 7 days" watch completes in < 8s end-to-end (down from ~50s) using cached rows.

### Day 24 — AI-defined Areas of Interest

**Goal:** after every scan, the supervisor (or a new dedicated `AoIAgent`) inspects composite events, clusters them, generates named polygons, and registers them.

1. New module `backend/agents/aoi_agent.py`:
   - `AoIAgent.infer(composite_events) -> list[AoI]`.
   - Step 1: HDBSCAN over `(lat, lon)` of composite events. Drop noise (label=-1).
   - Step 2: per cluster, compute alpha-shape via `alphashape` (fallback to convex hull when alpha-shape degenerates to a line for n<4 points).
   - Step 3: per cluster, build a context blob `{centroid, bbox, n_events, top_threat, top_sources, sample_event_summaries[:3]}` → LLM call → `AoIName{name_el, name_en, description, confidence}`.
   - Step 4: emit `AoI(id, name_el, name_en, polygon_wkt, source='ai', threat_summary, citation_event_ids, ...)`.
2. Persist:
   - DuckDB `aoi` table (id, source, name_el, name_en, polygon WKT, threat_grade, created_at, scan_id).
   - Neo4j `(:AreaOfInterest)` node + `[:CONTAINS]` to each composite event in cluster + `[:CITES]` from `(:BriefSection)` if the brief references it.
3. WatchExecutor calls `AoIAgent.infer()` after fusion; AoIs become available to the supervisor prompt as additional grounded entities. Supervisor prompt updated: it can cite `aoi://<id>` alongside `composite://<id>` etc.
4. New endpoint `GET /api/aoi?source=ai|user|all` returning GeoJSON FeatureCollection. Used by the map AoI layer.
5. Tests: `test_aoi_agent.py` — synthetic 3-cluster fixture → asserts 3 AoIs with non-degenerate polygons and Greek names.

**Definition of done:** Aegean watch produces 2-4 AoIs with sensible Greek names ("Λεκάνη Λήμνου", "Στενά Καρπάθου"). Each AoI's polygon visibly wraps its events on the map.

### Day 25 — User-drawn polygons

**Goal:** analyst can draw, name, save, and reuse polygons; they're indistinguishable from AI AoIs except by `source` flag.

1. Frontend deps: `terra-draw`, `terra-draw-maplibre-gl-adapter`. Add a `MapDrawControl` component overlaid on MapPanel — pencil/polygon/rectangle/circle modes, escape to cancel, double-click to finish.
2. On finish: open a tiny modal asking name (el) + name (en) + optional description. POST to `/api/aoi` with `source='user'`.
3. New endpoint:
   - `POST /api/aoi` — body `{name_el, name_en, geometry_geojson, description?}` → 201 with persisted AoI.
   - `DELETE /api/aoi/{id}` — only `source='user'` deletable.
   - `PATCH /api/aoi/{id}` — rename only.
4. Watch creation flow: WatchInput grows an optional "scope" picker → "Greece-wide", "Aegean preset", or any saved AoI. Selecting an AoI sets the watch's bbox to the polygon's bbox AND adds a `polygon_filter` to the WatchSpec (events outside the polygon are dropped at fusion stage).
5. Tests: e2e test draws a polygon via the API, runs a watch scoped to it, asserts the resulting brief's events all fall inside.

**Definition of done:** draw a polygon around Lemnos → name it "Test scope" → run a watch on it → brief returns events only from that polygon.

### Day 26 — Sigma.js + graphology graph migration

**Goal:** replace Cytoscape with Sigma. Maintain feature parity (citation pulse, click-to-cite, layer hide/show by node kind), gain 10x perf.

1. Frontend deps: `sigma@^3`, `graphology`, `graphology-layout-forceatlas2`, `graphology-layout`, `@react-sigma/core`.
2. New `GraphPanel.tsx` (replacement) using `<SigmaContainer>` + `useLoadGraph` + custom node/edge programs:
   - `nodeProgramClasses: { default: NodePointProgram, pulse: NodePulseProgram }` — custom WebGL fragment shader for the citation halo (a sine-modulated outer ring).
   - Edge program with width by `weight` and dashing for `[:CITES]`.
3. Layout strategy: ForceAtlas2 worker on initial mount; subsequent node additions placed near their dominant neighbour without re-layouting the world.
4. Citation highlight: store stays the same (`activeCitation: { sourceIds: [...] }`); the panel reacts by setting `node.attribute('highlighted', true)` and dimming others via `nodeReducer`. Animation runs on `requestAnimationFrame` through `node.attribute('phase')`.
5. LOD: at zoom < 0.4, hide labels; at zoom < 0.2, render super-clusters (graphology's `subGraph` or a custom k-means by community).
6. Bench page `/dev/graph-bench` (dev-only) renders 10k synthetic nodes; assert pan FPS > 50.

**Definition of done:** Greece scan produces 5k+ node graph; pan/zoom is fluid; citation click highlights in < 100ms.

### Day 27 — Rich, layered, interactive map

**Goal:** the map becomes the primary surface. Every shape is meaningful, every shape clicks into evidence.

1. **Vessel trajectory layer.** New endpoint `GET /api/map/trajectories?bbox&t_from&t_to&min_points=5` — DuckDB query groups `raw_ais` by mmsi, yields per-vessel polyline GeoJSON with timestamps. MapLibre `line` layer with `line-opacity` data-driven by a normalised age expression. Click a trail → pin the MMSI, open vessel evidence modal showing track + AIS metadata.
2. **Semantic icon symbology.** Replace the generic vessel circle with an SVG sprite atlas: `vessel-fishing`, `vessel-cargo`, `vessel-tanker`, `vessel-dark`, `news-event`, `social-signal`, `flight`, `composite-amber`, `composite-red`. Driven by `feature.properties.kind` via `icon-image`.
3. **AoI fill layer.** From `/api/aoi` GeoJSON. Two sublayers (ai vs user) with distinct colour. Centroid label layer with `text-field: name_el`. Hovering an AoI shows a tooltip with its threat summary.
4. **News density heatmap.** H3 hex-binned GDELT events from DuckDB `raw_news`; rendered via MapLibre `fill` layer with data-driven opacity. Toggleable.
5. **SAR detection layer.** Circles from `raw_sar` sized by `length_m`, coloured by `dark_score`. Clicking opens the SAR EvidenceModal directly (already exists).
6. **Satellite basemap toggle.** Custom raster source `s2cloudless` from EOX WMTS (`https://tiles.maps.eox.at/wmts`). Toggle in the layer panel swaps the basemap source. Attribution required: "© EOX::Maps · Sentinel-2 cloudless · ESA".
7. **Layer panel.** New `MapLayerPanel.tsx` — collapsible right-rail on the map with a checkbox + opacity slider per layer. State persisted in zustand `mapLayers`.
8. **Map ↔ brief ↔ graph wiring (extended).** Clicking any map shape sets `activeCitation` so the brief jumps to the citing section AND the graph highlights the source node — same flow as today, but now driven from any of three surfaces.

**Definition of done:** open the app post-scan → see Greek territory dotted with vessel trails, named AoI polygons, news hex hotspots, SAR detections. Toggle layers on/off. Switch to satellite basemap. Click a vessel trail → modal with SAR tile + AIS metadata.

### Day 28 — Phase 2 integration polish

**Goal:** demo-ready Phase 2. Everything tested. Docs updated. Limitations recorded.

1. End-to-end script `scripts/test_e2e_phase2.py` — extends `test_e2e.py` with: scan trigger, AoI inference assertions, polygon-scoped watch, trajectory endpoint, layer endpoints. Target: 35+ green assertions.
2. Performance budget in CI:
   - Cached watch < 8s.
   - Graph initial render (5k nodes) < 2s.
   - Map first interactive < 1.5s.
3. Update docs:
   - `docs/architecture.md` — add Phase 2 architecture diagram (DuckDB layer, scan scheduler, AoI agent, Sigma).
   - `docs/data-model.md` — add `aoi` table, `raw_*` tables, AoI/Trajectory Pydantic models.
   - `docs/sensors.md` — caching contract.
   - `docs/frontend.md` — Sigma migration, terra-draw, layer panel.
   - new `docs/store.md` — DuckDB schema, query patterns, retention policy.
   - new `docs/aoi.md` — AoI lifecycle (AI vs user), naming agent, polygon math.
4. `docs/limitations.md` — append Phase 2 limitations (DuckDB single-writer, alpha-shape edge cases, terra-draw mobile gaps).
5. Update `docs/demo-script.md` — fold the new capabilities into the 5-min script: open with the standing-coverage badge ("Greece is being watched right now"), show AoIs, draw a polygon live ("the analyst is in the loop"), highlight the WebGL graph speed, end with a satellite-basemap fly-to.
6. `.env.example` additions: `EOX_WMTS_URL`, `STANDING_SCAN_CRON`, `DUCKDB_PATH`.

**Definition of done:** phase2 e2e green, docs current, demo script rehearsed under 5min, limitations honest.

---

*Build document version: 1.2*
*Changes from v1.1: Phase 2 capability expansion — DuckDB persistence, Greece-wide standing scan, AI/user AoIs, Sigma.js graph, rich map layers*
*Changes from v1.0: Gemini API for development, Windows dev environment, arbitrary Watch queries*
*Target: EYP National Security Innovation Challenge 2026*
*Demo date: June 2026*
*Gold medal or nothing.*