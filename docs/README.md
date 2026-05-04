# Damocles documentation

Sovereign intelligence-analysis platform built for the **EYP National Security Innovation Challenge 2026**.
This folder is the engineering ground truth — every claim in the demo can be traced back here.

## Reading order

If you're brand new, read these in order. Each is self-contained but builds on the previous.

1. **[architecture.md](architecture.md)** — the big picture. System diagram, the 5-agent reasoning layer, the citation chain that is the gold-medal differentiator.
2. **[pipeline.md](pipeline.md)** — what happens between *"analyst types a query"* and *"brief appears with citations"*. WatchExecutor stage-by-stage.
3. **[data-model.md](data-model.md)** — the Pydantic types and Neo4j graph schema. Read this before touching any agent or sensor code.
4. **[sensors.md](sensors.md)** — Sentinel-1 SAR + CFAR vessel detection, AIS dark-vessel cross-reference, GDELT, Telegram, OpenSky. Free-tier limits, gotchas, schema offsets.
5. **[agents.md](agents.md)** — BaseAgent contract, the five agents, prompt-engineering rules, citation discipline, retry-on-validation-failure path.
6. **[audit.md](audit.md)** — Merkle-chained tamper-evident log, dual JSONL+Neo4j store, EU AI Act Article 12 alignment.
7. **[api.md](api.md)** — REST + WebSocket reference. Every endpoint with curl examples and response shapes.
8. **[frontend.md](frontend.md)** — three-panel React UI, Zustand store, MapLibre + Cytoscape, the citation-click handler.
9. **[testing.md](testing.md)** — unit, smoke, and end-to-end tests. The 22-assertion regression bar.
10. **[operations.md](operations.md)** — running, debugging, troubleshooting common issues.
11. **[deployment.md](deployment.md)** — GCP deployment plan: Secret Manager, systemd, nginx, sovereignty notes.
12. **[demo-script.md](demo-script.md)** — the 5-minute pitch script, timing, fallback options if something fails on stage.

## Reference docs

- **[credentials.md](credentials.md)** — step-by-step instructions for obtaining every API key and credential the stack needs.
- **[limitations.md](limitations.md)** — candid ledger of what's not done, what's compromised, and what's planned. **Read this before promising anything to a stakeholder.**

## Conventions used in these docs

- File paths are clickable links: `[backend/main.py](../backend/main.py)`. They open in IDEs that respect markdown navigation (VS Code, JetBrains).
- **BLOCKER / WORKAROUND / DEBT / BY DESIGN** severity tags follow the limitations doc convention.
- Code blocks are real, runnable code from the repo unless explicitly noted as illustrative.
- Cross-references between docs use plain links: `[architecture.md](architecture.md)`.

## What's NOT in here

- The build journal (Day-by-day commits and what was built when) — that lives in git history and the in-line section comments of [limitations.md](limitations.md).
- The plan itself — see [`.prompts/PLAN.md`](../.prompts/PLAN.md) for the original 3-week build spec. These docs describe what was actually built; the plan describes what was *intended*.
- API authentication — production deployment will need OIDC/SAML wired through the EYP identity provider. See [deployment.md](deployment.md) §"Auth".

## How to use this folder

- **Implementing a feature?** Start with [architecture.md](architecture.md) to know where it fits, then jump to the relevant component doc.
- **Reviewing the system?** Read in numbered order; takes ~45 minutes.
- **Preparing for the EYP demo?** Read [demo-script.md](demo-script.md), then [audit.md](audit.md) (most-asked-about technical detail), then [limitations.md](limitations.md) (so you can answer "what's not done?" honestly).
- **Onboarding a new contributor?** Have them read the numbered list, then run [testing.md §Quickstart](testing.md#quickstart).
