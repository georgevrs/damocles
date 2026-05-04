# Agents

The reasoning layer. Five LLM-driven agents that turn a `CompositeEvent` + its source nodes into a structured intelligence brief where every claim is backed by a graph node ID.

## The contract

[`backend/agents/base.py`](../backend/agents/base.py)

Every agent obeys five hard rules from the plan's prompt-engineering section:

1. **Schema enforcement** — output is JSON, validated against a Pydantic class
2. **Citation enforcement** — every key finding cites at least one node ID present in the supplied context
3. **Uncertainty enforcement** — `uncertainty_flags` is non-empty (no agent is omniscient)
4. **Token discipline** — bounded prompt context (≤4k tokens for an 8B local model)
5. **Retry once** on validation failure with the bad output + error message in the correction prompt

```python
class AgentOutput(BaseModel):
    analysis: str                    # one paragraph, ≤300 words
    key_findings: list[str]          # discrete claims, max 5
    confidence: float                # 0.0-1.0
    citation_node_ids: list[str]     # every node ID referenced
    uncertainty_flags: list[str]     # non-empty
```

Subclasses extend the schema:
- `DevilsAdvocateOutput` adds `devil_confidence` (probability primary is wrong)
- `SupervisorOutput` is structurally different — nested per-section blocks; see below

## The five agents

```
                                   ┌───────────────────┐
                                   │  GeospatialAgent  │  T=0.1, max_tokens=2048
                                   │  vessels + AIS    │
                                   └───────────────────┘  output_model=AgentOutput
                                            ↓
                                   ┌───────────────────┐
                                   │  OSINTAgent       │  T=0.1, max_tokens=2048
                                   │  news + social    │
                                   └───────────────────┘  output_model=AgentOutput
                                            ↓
                                   ┌───────────────────┐
                                   │  LinguistAgent    │  T=0.1, max_tokens=2048
                                   │  geocode + lang   │
                                   └───────────────────┘  output_model=AgentOutput
                                            ↓
                                   ┌───────────────────┐
                                   │  Devil's Advocate │  T=0.3 (creative)
                                   │  challenges all   │
                                   └───────────────────┘  output_model=DevilsAdvocateOutput
                                            ↓
                                   ┌───────────────────┐
                                   │  Supervisor       │  T=0.0 (pure synthesis)
                                   │  assembles brief  │
                                   └───────────────────┘  output_model=SupervisorOutput
                                            ↓
                                       ┌────────┐
                                       │ Brief  │
                                       └────────┘
```

### 1. GeospatialAgent
[`backend/agents/geospatial_agent.py`](../backend/agents/geospatial_agent.py) + [prompts/geospatial.txt](../backend/agents/prompts/geospatial.txt)

Reasons over the *vessel slice* of a composite. Pre-fetches the CompositeEvent + its `COMPOSED_OF` Vessel and (incidental) NewsEvent/SocialSignal sources, formats them compactly with the explicit list of valid IDs the model may cite.

**Domain guidance** in the system prompt:
- Sentinel-1 SAR cannot determine vessel intent — only presence, size, AIS-broadcast status. Be precise about what the data supports.
- An AIS-dark vessel in a contested zone with length > 100m is a high-priority signal.
- A broadcasting vessel with a matched MMSI is, absent other evidence, routine commercial traffic. Don't over-state it.

**Calibration**:
- `>0.85` = strong, multi-source corroboration
- `0.6-0.85` = single-source but high quality
- `<0.6` = weak signal, speculative

### 2. OSINTAgent
[`backend/agents/osint_agent.py`](../backend/agents/osint_agent.py) + [prompts/osint.txt](../backend/agents/prompts/osint.txt)

Reasons over the *news + social* slice. Same pattern as Geospatial.

**Domain guidance**:
- High mention-count GDELT events amplified across multiple outlets weigh more than one viral channel post.
- Goldstein ≤ -5 + corroborating Telegram chatter in the same window = real escalation signal.
- Suspect *coordinated inauthentic behaviour* when multiple Telegram channels with no shared editorial line push the same wording within a short time. Flag and cite.
- Distinguish *what was reported* from *what happened*. Both NewsEvent and SocialSignal nodes are reports — they prove someone said it, not that it's true.

### 3. LinguistAgent
[`backend/agents/linguist_agent.py`](../backend/agents/linguist_agent.py) + [prompts/linguist.txt](../backend/agents/prompts/linguist.txt)

Two-phase agent:
1. **Deterministic enrich** — runs the gazetteer geocoder over Telegram messages, writes lat/lon back to Neo4j. No LLM. This is what closes [limitations.md §4c.3](limitations.md) (Telegram has no native geocoding).
2. **Analytical pass** — standard agent loop summarizing the multilingual narrative, picking up coordinated-narrative indicators.

**Geocoder**: [`backend/agents/_geocoder.py`](../backend/agents/_geocoder.py) — NFD-normalized substring match against [`data/geojson/aegean_gazetteer.json`](../data/geojson/aegean_gazetteer.json) (~46 places: Greek mainland + Aegean islands + Turkish coast + Cyprus + select strategic Eastern Med locations).

Two non-obvious behaviors:
- **Greek inflection variants**: `Σάμος` (nominative) doesn't substring-match `Σάμο` (accusative). The gazetteer loader emits both forms (drop trailing sigma) so either matches.
- **Leftmost-in-text wins**: `"Cesme'den Chios'a"` returns Cesme (leftmost) with longest-alias as tiebreaker. The previous "longest-alias-globally" rule returned Chios because of place-iteration order — fixed Day 9.

**Why not spaCy NER?** For a curated AOI a hardcoded gazetteer + diacritic-tolerant matcher catches >85% of place mentions, runs in <1ms per message, and produces zero false positives from misclassified entities. We can swap in spaCy without changing the `Geocoder.geocode_text()` signature when broader coverage is needed.

### 4. Devil's Advocate
[`backend/agents/devils_advocate.py`](../backend/agents/devils_advocate.py) + [prompts/devils_advocate.txt](../backend/agents/prompts/devils_advocate.txt)

The plan calls this *"the hardest — iterate on the prompt"*. It receives the primary agents' outputs and produces the strongest possible counter-assessment.

**Hard rules in the prompt**:
- For each key finding from the primaries, attempt at least ONE of:
  1. Alternative innocent explanation
  2. Data-quality challenge (source bias, sampling gaps, propaganda, mis-geocoding)
  3. Methodological challenge (spurious correlation, confounders, sample-size issues)
- **Required to find at least one challenge.** If genuinely cannot, say so EXPLICITLY and explain why — *do not manufacture false challenges*. Manufactured challenges destroy trust faster than missed ones.

**Output schema** extends `AgentOutput` with `devil_confidence`:
```python
class DevilsAdvocateOutput(AgentOutput):
    devil_confidence: float          # probability primary is WRONG
```

`confidence` (inherited) means "how solid is this counter-analysis"; `devil_confidence` means "probability the PRIMARY assessment is wrong". They diverge intentionally — a strong counter-argument backed by data might score `confidence=0.85` even if `devil_confidence=0.5` because the evidence is genuinely ambiguous.

**Calibration**:
- `> 0.7` — primary is almost certainly wrong; analyst should override
- `~ 0.5` — genuinely ambiguous
- `< 0.3` — primary is almost certainly right; you found minor caveats

**Temperature is 0.3** (vs 0.1 for factual agents) so the model explores creative counter-arguments rather than echoing the primary's framing.

### 5. SupervisorAgent
[`backend/agents/supervisor_agent.py`](../backend/agents/supervisor_agent.py) + [prompts/supervisor.txt](../backend/agents/prompts/supervisor.txt)

Senior intelligence officer. Reads everyone's outputs, produces the final 5-section Brief.

**Output schema** is structurally different — nested:
```python
class SupervisorOutput(BaseModel):
    bluf: SupervisorBriefSection
    key_judgments: list[SupervisorBriefSection] = []
    supporting_evidence: list[SupervisorBriefSection] = []
    devils_advocate: SupervisorDevilsAdvocate | None = None
    recommended_action: SupervisorRecommendation | None = None
    metadata: dict[str, Any] = {}
```

**Validation is per-block**: every text-bearing block (BLUF, each judgment, each supporting evidence item, the devil's text, the recommendation) must have a non-empty `citation_node_ids` list referencing actual graph nodes. The Supervisor overrides `BaseAgent.run()` to do nested validation that doesn't fit the flat-list contract `validate_agent_output()` enforces.

**Temperature is 0.0** — pure synthesis, no creativity needed.

**Calibration the prompt teaches**:
- Disagree with primaries when warranted. The Supervisor is the senior officer.
- If Devil's Advocate found a strong counter (`devil_confidence ≥ 0.7`), the BLUF reflects that doubt — don't paper over it.
- If a key judgment's confidence is `< 0.5`, mark it as a hypothesis ("evidence is consistent with...").

The plan's exact wording lives in the system prompt; see [`backend/agents/prompts/supervisor.txt`](../backend/agents/prompts/supervisor.txt).

After parsing, `assemble_brief()` converts the LLM-shaped `SupervisorOutput` into the canonical `Brief` Pydantic with watch_id, brief_id, and the BriefSection IDs minted server-side.

## The pre-fetched context pattern

Every agent's `fetch_context()` does targeted Cypher upfront and formats results compactly. Example (geospatial):

```python
async def fetch_context(self, composite_event_id: str, **_kwargs):
    rows = await self.graph.run("""
        MATCH (ce:CompositeEvent {id: $id})
        OPTIONAL MATCH (ce)-[:COMPOSED_OF]->(source)
        RETURN ce, collect({type: labels(source)[0], props: source}) AS sources
    """, id=composite_event_id)

    valid_ids = [ce["id"]] + [s["id"] for s in sources if s.get("id")]

    ctx = (
        f"Valid citation_node_ids you may reference (and only these):\n"
        f"  {valid_ids}\n\n"
        f"CompositeEvent under analysis:\n  {json.dumps(ce_compact)}\n\n"
        f"Source nodes ({len(sources_compact)}):\n  {json.dumps(sources_compact)}\n\n"
        f"Produce your structured AgentOutput now."
    )
    return ctx, valid_ids
```

The model gets a compact prompt (typically 600-1500 chars) with **the exact list of IDs it may cite**. Validation rejects anything outside the list.

## Validation lifecycle

```
                    ┌─────────────────────┐
                    │  fetch_context()    │
                    │  → (ctx, valid_ids) │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │  LLM call           │
                    │  json_mode=True     │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │  _parse(raw)        │     ← strips ```json fences, calls
                    │  → output_model     │       json.loads, validates against
                    └──────────┬──────────┘       the agent's output_model
                               ↓
                    ┌─────────────────────┐
                    │  validate_*(out,    │     ← checks citation IDs exist,
                    │  valid_ids)         │       uncertainty non-empty
                    └──────────┬──────────┘
                       ok ↙       ↘ fail
                  ┌──────┐    ┌─────────────────────────────────┐
                  │ done │    │ 2nd LLM call with correction    │
                  └──────┘    │ prompt: prior bad output +      │
                              │ validation error message        │
                              └────────────┬────────────────────┘
                                           ↓
                                    ┌──────────┐
                                    │ revalidate│
                                    │ → done    │
                                    └──────────┘
```

The retry path captures the validation error in `first_error`, then sends:
```
[system prompt]
[user message: original context]
[assistant message: prior bad output verbatim]
[user message: "Your previous output had this validation error: <error>.
 Produce a corrected output. Only use citation_node_ids from the context above..."]
```

This is enough for Gemini 3 to produce a corrected output ~95% of the time. A double-failure raises and the agent layer marks this composite as failed.

## Per-agent extension points

Want to add a sixth agent? Create a class extending `BaseAgent`:

```python
class MyDomainAgent(BaseAgent):
    name = "my_domain"
    temperature = 0.1
    max_tokens = 2048
    output_model = AgentOutput   # or a custom subclass

    def system_prompt(self) -> str:
        return _PROMPT_PATH.read_text(encoding="utf-8")

    async def fetch_context(self, composite_event_id: str, **_kwargs):
        # targeted Cypher → (ctx_string, valid_id_list)
        ...
```

`BaseAgent.run()` handles the rest. If the agent needs a richer schema (like Devil's Advocate), set `output_model` to a subclass of `AgentOutput`. If the validation rules need to change (like Supervisor), override `run()`.

## LLM provider — abstracted at every external call

[`backend/llm/`](../backend/llm/) — see [architecture.md §6](architecture.md) for the design rationale.

The `LLMProvider` interface is tiny:
```python
class LLMProvider(ABC):
    async def complete(messages, temperature, max_tokens, json_mode) -> LLMResponse
    def get_model_name() -> str
    async def health_check() -> bool
```

Today's `GeminiProvider` ([gemini.py](../backend/llm/gemini.py)) ships:
- Comma-separated **fallback chain** (e.g. `gemini-3-flash-preview,gemini-2.5-flash,gemini-2.0-flash`)
- Daily-quota 429 → mark model exhausted for the process, try next in chain
- Per-minute 429 → try next model momentarily without marking exhausted
- `thinking_level="minimal"` for Gemini 3 (without it, thinking tokens eat the visible output budget non-deterministically — this caught us during Day 9)

The Devil's Advocate uses `get_devil_provider()` which returns a more creative model when running on Ollama (`qwen2.5:7b`) and the same chain when running on Gemini.

## Cost forecast

Per Watch, with the demo's "top-1 composite" approach:

| Stage | LLM calls | Average tokens | ~Cost (Gemini paid tier) |
| --- | --- | --- | --- |
| Watch parse | 1 | 200 in, 100 out | $0.0001 |
| Geospatial agent | 1 (+ retry) | 800 in, 400 out | $0.001 |
| OSINT agent | 1 (+ retry) | 800 in, 400 out | $0.001 |
| Devil's Advocate | 1 (+ retry) | 1500 in, 600 out | $0.002 |
| Supervisor | 1 (+ retry) | 2000 in, 800 out | $0.003 |
| **Total per watch** | **~5-10 calls** | | **~$0.01** |

Free tier (15 RPM, ~100-1500/day depending on model) covers ~50-100 watches/day in dev. Demo prep could comfortably run 200+ watches/day across the team.

When running on Ollama for the demo: zero per-watch cost, ~3-5 minutes per watch on a CPU-only machine, ~30-60 seconds on an 8GB GPU.

## Tested behaviors

- [`tests/test_agent_base.py`](../tests/test_agent_base.py) — 14 tests covering validation rules, retry paths, markdown-fence stripping, latency budget
- [`tests/test_devils_advocate.py`](../tests/test_devils_advocate.py) — 10 tests including the `devil_confidence` schema-extension path
- [`tests/test_supervisor.py`](../tests/test_supervisor.py) — 13 tests covering nested validation per section, the `assemble_brief()` conversion, configuration sanity (T=0.0, output_model=SupervisorOutput)
- [`tests/test_geocoder.py`](../tests/test_geocoder.py) — 19 tests including Greek inflection, Turkish diacritics, leftmost-in-text wins
- [`tests/test_linguist_enrich.py`](../tests/test_linguist_enrich.py) — 6 tests on the deterministic enrich phase

Plus live smokes in `scripts/test_*.py` exercising real Gemini round-trips against the seeded graph.

See [testing.md](testing.md) for the full test landscape.
