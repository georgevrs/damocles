# Security

This is a research/competition codebase, not a hardened production deployment.
The notes below document what is and isn't safe in this repo, and what an
operator must do before pointing it at real intelligence data.

## Reporting a vulnerability

Open a GitHub issue tagged `security` or email the maintainer privately. Do
not open public issues for unpatched vulnerabilities.

## Secrets handling

Damocles needs several third-party API keys (Gemini, Sentinel Hub, Telegram,
AISStream) plus a Neo4j password. **None of them are committed.** Required
hygiene:

- All credentials live in `.env`, which is gitignored.
- `.env.example` lists every variable with empty values and a placeholder
  Neo4j password (`CHANGE_ME_neo4j_password`). Replace it.
- Never commit `*.session` files (Telegram authentication tokens).
- Never commit `*credentials*.json` or service-account keys (GCP).
- The `data/*.duckdb*` operational fact store is gitignored — it can contain
  vessel positions, news clippings, and inferred AoIs from your scans.
- The `audit_log.jsonl` Merkle chain is gitignored for the same reason.
- `memory/` and `.claude/` directories are gitignored — they may contain
  user-specific Claude Code context.

If you fork this repo and your fork is public, run a secret scan
(`trufflehog`, `gitleaks`) before you push. The first commit ships clean —
keep it that way.

## Threat model

This codebase is built for the EYP National Security Innovation Challenge
2026 as a sovereign-intelligence prototype. It is intentionally:

- **Single-tenant** — there is no auth layer. Every API endpoint is open to
  whoever can reach the host. Operationally it must run behind a VPN/private
  network. Do not expose `:8000` to the public internet.
- **Trust-the-LLM** — no prompt-injection defense beyond citation validation.
  The Linguist agent and Telegram sensor will faithfully pass through any
  text they're given. Adversarial inputs from monitored channels can shape
  agent reasoning. This is a known limitation, not a vulnerability.
- **Best-effort SSRF** — the `/api/preview` link-preview proxy fetches
  arbitrary URLs from news articles. It is not yet hardened against
  internal-network probing. Run on an isolated network or restrict the
  endpoint behind an egress allowlist.

## Audit trail

The Merkle-chained audit log (`backend/audit/`) is the integrity guarantee:
every model call, every brief assembly, every analyst action is hash-chained.
The `Verify chain` button in the UI re-hashes the entire log and surfaces
any tampering. The chain itself isn't a security boundary against an
attacker who owns the host, but it makes after-the-fact tampering by an
auditor visible.
