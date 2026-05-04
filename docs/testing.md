# Testing

## Quickstart

```powershell
# All unit + integration tests (no network, no Neo4j needed for most)
uv run pytest -q

# Specific layer
uv run pytest tests/test_cfar.py            # geospatial detection
uv run pytest tests/test_dark_vessel.py     # AIS cross-reference
uv run pytest tests/test_fusion.py          # spatiotemporal fusion
uv run pytest tests/test_supervisor.py      # brief assembly
uv run pytest tests/test_audit_logger.py    # Merkle chain

# Live smoke tests (need backend running, hit real APIs)
uv run python scripts/verify_sources.py     # all credentials/connectivity
uv run python scripts/test_geospatial.py    # one Sentinel-1 tile + CFAR
uv run python scripts/test_ais.py           # 30s AIS capture + cross-reference
uv run python scripts/test_gdelt.py         # 6 hours of GDELT events
uv run python scripts/test_brief_assembly.py # full pipeline against seeded graph
uv run python scripts/test_audit.py         # populate + tamper + restore

# THE pre-demo regression bar (full button-press → brief → audit verify)
.\start.ps1 -NoFrontend                     # backend + Neo4j
uv run python scripts/test_e2e.py           # 22 assertions
```

## Test pyramid

```
                    ┌─────────────────────┐
                    │  e2e via API + WS   │  scripts/test_e2e.py
                    │  (1 ceremonial)     │  ~65 s, 22 assertions
                    └─────────────────────┘
                  ┌───────────────────────────┐
                  │  Live smoke tests         │  scripts/test_*.py
                  │  (per sensor + per agent  │  ~5-30 s each, network required
                  │   + per major component)  │
                  └───────────────────────────┘
              ┌─────────────────────────────────────┐
              │  Unit tests (140+, deterministic)    │  tests/test_*.py
              │  CFAR, fusion, geocoder, agents,    │  ~5 s total, no network
              │  audit chain, broker, parsers, ...  │
              └─────────────────────────────────────┘
```

The pyramid weighs heavily on unit tests because every layer was designed to be testable in isolation. Live smokes catch integration drift that unit tests can't see (real API shapes, real timing, real LLM behaviors).

## Unit tests

[`tests/`](../tests/) — 140+ tests, ~5 seconds total.

### What's tested

| File | Tests | What it pins |
| --- | --- | --- |
| `test_cfar.py` | 4 | Synthetic SAR + planted point targets; recall, false-positive rate, confidence monotonicity, error paths |
| `test_dark_vessel.py` | 13 | Match/dark/missing-AIS paths, dark-score risk-factor logic, contested zones, immutability |
| `test_gdelt.py` | 12 | TSV parsing, GDELT 2.0 field offsets, dual country-code scheme, CAMEO root filter, defensive handling of missing fields |
| `test_telegram_keywords.py` | 14 | Greek tonos / Turkish dotted-I matching, Greek inflection, edge cases |
| `test_geocoder.py` | 19 | Aegean place-name matching including the Greek-inflection bug, leftmost-in-text wins |
| `test_linguist_enrich.py` | 6 | Deterministic enrichment phase of the Linguist agent |
| `test_fusion.py` | 14 | Co-located/distant pairs, same-sensor isolation, three-sensor chains, all four threat-grade rules |
| `test_agent_base.py` | 14 | Validation rules, retry-on-orphan-citation, retry-on-invalid-JSON, markdown-fence stripping, latency budget |
| `test_devils_advocate.py` | 10 | `devil_confidence` schema-extension, retry path through subclassed output_model |
| `test_supervisor.py` | 13 | Nested per-section validation, `assemble_brief()` conversion, configuration sanity (T=0.0) |
| `test_audit_logger.py` | 14 | Hash primitives, tamper detection, reorder detection, cross-restart continuity, **concurrent log() under asyncio.Lock** |
| `test_broker.py` | 6 | Buffer replay for late-joining WebSocket subscribers, fan-out, GC, race-safe register-then-snapshot |
| `test_llm_provider.py` | 1 | LLM round-trip smoke (auto-skips if `LLM_PROVIDER` not configured) |

### Conventions

- Pytest with `asyncio_mode = auto` (configured in `pyproject.toml`)
- Mock LLM provider for agent tests — `MockLLM` in [`tests/test_agent_base.py`](../tests/test_agent_base.py) returns a queue of canned responses, recording every call
- Synthetic data generators (e.g., `_synthetic_sar()` in `test_cfar.py`) for deterministic input
- No network in unit tests — the LLM smoke test skips automatically when no provider is reachable
- File names match the module under test: `tests/test_<module>.py`

### Adding a test

```python
# tests/test_my_feature.py
import pytest
from backend.<module> import my_function

def test_happy_path():
    assert my_function(input) == expected

@pytest.mark.asyncio
async def test_async_path():
    result = await my_async_function()
    assert result.field == expected
```

If your test needs a graph / LLM / network, write a **smoke test** instead (next section).

## Live smoke tests

[`scripts/test_*.py`](../scripts/) — exercise real external APIs against running services.

These are not in `tests/` because:
- They need credentials (`GEMINI_API_KEY`, `SENTINELHUB_*`, etc.) configured
- They make real network calls (Sentinel Hub, AISStream WS, GDELT, Gemini)
- They take 5-60 seconds each
- They consume rate-limited budgets (Gemini RPM, Sentinel Hub PUs)

| Script | What it exercises | Cost |
| --- | --- | --- |
| `verify_sources.py` | All 7 source connections (LLM, Neo4j, Sentinel, GDELT, OpenSky, AISStream, Telegram) | ~3 s |
| `test_geospatial.py` | One Sentinel-1 IW tile fetch + CFAR detection + preview PNG save | ~12 s, ~5 PU |
| `test_ais.py` | 30 s AISStream WebSocket capture + cross-reference vs synthetic SAR detections | ~30 s |
| `test_gdelt.py` | Last 6 hours of GDELT events filtered by GR/TU/CY actors + CAMEO root | ~10 s, ~25 MB DL |
| `test_geospatial.py`, `test_dark_vessel.py` | (see above) | |
| `test_agent.py` | One real Geospatial agent run on a seeded composite | ~5 s, 1 Gemini call |
| `test_osint_agent.py` | One real OSINT agent run | ~5 s, 1 Gemini call |
| `test_devils_advocate.py` | Geo + OSINT + Devil's Advocate against a seeded composite | ~15 s, 3 Gemini calls |
| `test_brief_assembly.py` | Full agent layer + brief ingestion + citation chain Cypher | ~20 s, 4 Gemini calls |
| `test_audit.py` | Two-pass: populate chain via real pipeline, then tamper-and-verify-rejects | ~20 s, 4 Gemini calls |
| `test_api.py` | All read-only REST endpoints against seeded data | ~5 s |
| `test_e2e.py` | **Full end-to-end via the public API** (POST → WS → brief → citation → audit) | ~65 s, 5 Gemini calls + 1 SAR fetch |

### When to run which

- **Daily, during dev**: `uv run pytest -q` for the unit tests on every save
- **Before pushing changes to a sensor**: the relevant `scripts/test_<sensor>.py`
- **Before pushing changes to an agent**: `scripts/test_brief_assembly.py`
- **Before every demo dry-run**: **`scripts/test_e2e.py` MUST PASS 22/22**

## The end-of-week-2 integration test — `test_e2e.py`

[`scripts/test_e2e.py`](../scripts/test_e2e.py) is the **regression bar that runs before every demo**. If any of the 22 assertions fail, the dry-run is blocked until it's diagnosed.

It walks the full public-API path:

| Phase | What it asserts |
| --- | --- |
| `GET /health` | backend reachable, Neo4j up, LLM up |
| `POST /api/watches` | returns `Watch` with id |
| `WS /ws/watches/{id}` | streams events to completion |
| `GET /api/briefs?watch_id=...` | brief appears |
| `GET /api/briefs/{id}` | brief has BLUF (exactly 1), ≥1 KEY_JUDGMENT, DEVILS_ADVOCATE present, RECOMMENDATION present, every section has citations, BLUF text is substantive |
| `GET /api/briefs/{id}/citation/{section_id}` | each call resolves all claimed citations, every source has node_id + node_type + raw_evidence (× N sections) |
| `GET /api/audit/verify` | chain verifies clean (no tamper), chain has > 0 entries (this run logged something) |

22 assertions in one place. Last verified: `Day 14 OK - end-to-end integration green; demo regression test passes.`

```powershell
# Pre-demo workflow
.\start.ps1 -NoFrontend                # boot backend + Neo4j
uv run python scripts/test_e2e.py      # 22 assertions
# expect: 22/22 PASS in ~65 s
```

## Mocking strategy

### LLM
`MockLLM` in [`tests/test_agent_base.py`](../tests/test_agent_base.py):
```python
class MockLLM(LLMProvider):
    def __init__(self, responses: list[str]):
        self._queue = list(responses)
        self.calls: list[list[LLMMessage]] = []

    async def complete(self, messages, ...):
        self.calls.append(messages)
        content = self._queue.pop(0)
        return LLMResponse(content=content, ...)
```

Tests inject canned responses for each LLM call the agent will make. The retry path is testable by queuing `[bad_output, good_output]` and asserting `len(llm.calls) == 2` plus checking the second call's messages contain the validation error.

### Neo4j
Most agent tests subclass the real agent and override `fetch_context` to return a fixed `(context, valid_ids)` tuple — no Neo4j needed:

```python
class _StubDevil(DevilsAdvocateAgent):
    def __init__(self, llm, valid_ids):
        BaseAgent.__init__(self, llm=llm, graph=None)
        self._valid_ids = list(valid_ids)
    async def fetch_context(self, **kw):
        return "fixed devil context", list(self._valid_ids)
```

For tests that DO need Neo4j (the brief assembly + citation chain smoke), the script assumes Neo4j is running (started by `start.ps1`) and seeded with at least one watch.

### WebSocket
`test_broker.py` uses a real `asyncio.Queue`-based fake; no actual WS server needed. The broker's contract is small enough that the unit tests cover the buffer replay race + fan-out + GC.

For end-to-end WS testing, `test_e2e.py` opens a real `websockets.connect` against a running uvicorn.

## Test gaps to close before production

These are flagged as DEBT in [limitations.md](limitations.md) but worth listing here:

- **No Vitest tests on the frontend** — the citation-click handler is the gold-medal moment and any regression is catastrophic for the demo. Minimum: 3 tests on `CitableText` (renders, click fires `fetchCitationChain`, applies confidence color). [§6.4](limitations.md)
- **No Playwright/Cypress test** — the API e2e covers the data path but doesn't drive the UI. Pre-demo: a Playwright run that types a watch, waits for the brief, clicks BLUF, asserts the map flew, the graph highlighted, the modal opened. [§6.6](limitations.md)
- **No load testing** — single-watch-at-a-time is what the demo needs. Production with concurrent analysts hasn't been benchmarked. The in-memory event broker would also need to swap to Redis for multi-worker uvicorn (limitations §5c.1).

## Test naming + organization

- **Unit tests**: `tests/test_<module>.py`, function names `test_<scenario>`
- **Live smokes**: `scripts/test_<thing>.py` — runnable as `uv run python scripts/...`, prints rich tables, exits non-zero on failure
- **Setup scripts**: `scripts/setup_<thing>.py` — interactive (e.g., Telegram auth)
- **Helpers / debugs (don't ship)**: prefix with `_`, e.g. `scripts/_list_routes.py`, `scripts/_debug_gemini_raw.py` (cleaned up after use)

## Reading test failures

When a test fails:

1. **Unit test**: pytest's traceback points at the line. The mocked LLM's `calls` list is often the most useful inspect target — what did we actually send vs. what did the test expect?
2. **Live smoke**: each script exits non-zero with a Rich-formatted summary. The failing assertion is usually visible in the last 20 lines of output.
3. **`test_e2e.py`**: prints all 22 assertions in a table at the end. The "detail" column has the actionable info (e.g., `claimed=1 resolved=0` means a citation in the brief points at a node that doesn't exist in the graph).

For LLM-side failures (validation errors, schema mismatches), check the live-smoke output for the actual response content. Most agent issues are prompt-engineering problems, not code bugs.

## Test environment requirements

- Python 3.12 (pinned via `.python-version`)
- `uv` for package management (`pip install uv`)
- For unit tests: nothing else
- For live smokes: `.env` populated per [credentials.md](credentials.md)
- For Neo4j-touching scripts: Docker Desktop running with the `damocles-neo4j` container up
- For `test_e2e.py`: backend uvicorn running on `:8000`

## CI considerations

Not yet wired. Plan:

```yaml
# .github/workflows/ci.yml (sketch)
- run: uv sync --extra dev
- run: uv run pytest -q                     # unit tests, no secrets needed
- run: uv run python scripts/verify_sources.py  # if secrets are available
```

Live smokes that consume rate-limited budgets (Gemini, Sentinel Hub) should run on PR merge, not on every push. The 22-assertion `test_e2e.py` should be a manual gate before demo dry-runs.
