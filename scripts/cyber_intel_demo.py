"""Cyber Intelligence Demo — Damocles Hackathon

Fetches LIVE threat data from two free sources and prints structured samples
showing what cyber attacks look like so you can map them into the knowledge graph.

Sources
-------
1. AlienVault OTX  — https://otx.alienvault.com  (free API key required)
2. Feodo Tracker   — https://feodotracker.abuse.ch (no key, completely open)

Usage
-----
    # With OTX key (recommended):
    export OTX_API_KEY="your_key_here"
    python scripts/cyber_intel_demo.py

    # Without OTX key (Feodo only):
    python scripts/cyber_intel_demo.py

How to get a free OTX key
--------------------------
    1. Go to https://otx.alienvault.com
    2. Register (free, instant)
    3. Profile → Settings → OTX Key → copy it
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import httpx

# ── colour helpers ────────────────────────────────────────────────────────────
RED    = "\033[91m"
AMBER  = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def grade_colour(grade: str) -> str:
    return {
        "RED":   RED + BOLD,
        "AMBER": AMBER + BOLD,
        "GREEN": GREEN + BOLD,
    }.get(grade, RESET)


# ══════════════════════════════════════════════════════════════════════════════
# 1.  FEODO TRACKER  (no API key — always works)
# ══════════════════════════════════════════════════════════════════════════════

FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist.json"


def _grade_botnet(malware: str) -> str:
    """Map malware family to Damocles ThreatGrade."""
    high = {"Emotet", "QakBot", "TrickBot", "IcedID", "Dridex"}
    med  = {"AsyncRAT", "AgentTesla", "Formbook"}
    if malware in high:
        return "RED"
    if malware in med:
        return "AMBER"
    return "GREEN"


def fetch_feodo() -> list[dict[str, Any]]:
    """Fetch live Feodo C2 blocklist and return normalised CyberEvent dicts."""
    print(f"\n{CYAN}{BOLD}━━━  FEODO TRACKER — Live Botnet C2 Servers  ━━━{RESET}")
    try:
        resp = httpx.get(FEODO_URL, timeout=15)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"  [ERROR] Feodo Tracker unreachable: {exc}")
        return []

    raw: list[dict] = resp.json()
    print(f"  Total C2 IPs in blocklist: {len(raw)}")

    events: list[dict[str, Any]] = []
    for entry in raw[:20]:          # show first 20 as samples
        grade = _grade_botnet(entry.get("malware", ""))
        event: dict[str, Any] = {
            # ── fields that map directly to a future Neo4j node ───────────────
            "source":          "feodo_tracker",
            "event_type":      "botnet_c2",
            "ip_address":      entry.get("ip_address", ""),
            "port":            entry.get("dst_port"),
            "protocol":        "tcp",
            "malware_family":  entry.get("malware", "Unknown"),
            "country":         entry.get("country", "??"),
            "as_number":       entry.get("asn"),
            "first_seen":      entry.get("first_seen"),
            "last_online":     entry.get("last_online"),
            "confidence":      0.95,   # blocklist = high confidence
            "threat_grade":    grade,
            # ── Neo4j edge template ───────────────────────────────────────────
            "neo4j_cypher_hint": (
                f"(:IP_Address {{value: '{entry.get('ip_address','')}'}}) "
                f"-[:HOSTS_C2 {{malware: '{entry.get('malware','')}', "
                f"confidence: 0.95}}]->(:Botnet_C2)"
            ),
        }
        events.append(event)

    return events


def print_feodo_samples(events: list[dict]) -> None:
    if not events:
        return

    print(f"\n  {'IP ADDRESS':<18} {'PORT':<7} {'MALWARE':<15} {'COUNTRY':<6} {'GRADE'}")
    print(f"  {'─'*18} {'─'*7} {'─'*15} {'─'*6} {'─'*8}")

    for e in events:
        colour = grade_colour(e["threat_grade"])
        print(
            f"  {e['ip_address']:<18} "
            f"{str(e['port'] or '?'):<7} "
            f"{e['malware_family']:<15} "
            f"{e['country']:<6} "
            f"{colour}{e['threat_grade']}{RESET}"
        )

    red_count   = sum(1 for e in events if e["threat_grade"] == "RED")
    amber_count = sum(1 for e in events if e["threat_grade"] == "AMBER")
    print(f"\n  Summary (sample): {RED}{BOLD}{red_count} RED{RESET}  "
          f"{AMBER}{BOLD}{amber_count} AMBER{RESET}  "
          f"{GREEN}{BOLD}{len(events)-red_count-amber_count} GREEN{RESET}")

    print(f"\n  {BOLD}Sample Neo4j hint:{RESET}")
    print(f"  {CYAN}{events[0]['neo4j_cypher_hint']}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# 2.  ALIENVAULT OTX  (free API key required)
# ══════════════════════════════════════════════════════════════════════════════

OTX_BASE = "https://otx.alienvault.com/api/v1"


def _grade_pulse(tags: list[str], adversary: str) -> str:
    """Estimate threat grade from pulse tags and adversary label."""
    critical_tags = {
        "ddos", "ransomware", "apt", "critical infrastructure",
        "government", "nato", "greece", "hellenic",
    }
    high_tags = {"malware", "botnet", "phishing", "exploit", "c2"}
    joined = " ".join(t.lower() for t in tags) + adversary.lower()
    if any(t in joined for t in critical_tags):
        return "RED"
    if any(t in joined for t in high_tags):
        return "AMBER"
    return "GREEN"


def fetch_otx_pulses(api_key: str, query: str = "greece OR hellenic OR aegean", limit: int = 10) -> list[dict[str, Any]]:
    """Fetch recent OTX pulses matching a search term and return normalised events."""
    print(f"\n{CYAN}{BOLD}━━━  ALIENVAULT OTX — Threat Intelligence Pulses  ━━━{RESET}")
    headers = {"X-OTX-API-KEY": api_key}

    # Search for Greece/Hellenic-tagged pulses first; fall back to latest if none.
    for search_q in (query, ""):
        params: dict[str, Any] = {"limit": limit, "page": 1}
        if search_q:
            params["q"] = search_q
            endpoint = f"{OTX_BASE}/pulses/search"
        else:
            endpoint = f"{OTX_BASE}/pulses/subscribed"

        try:
            resp = httpx.get(endpoint, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 403:
                print(f"  [ERROR] OTX API key invalid or missing. "
                      f"Get a free key at https://otx.alienvault.com")
                return []
            print(f"  [ERROR] OTX request failed: {exc}")
            return []
        except httpx.HTTPError as exc:
            print(f"  [ERROR] OTX unreachable: {exc}")
            return []

        data = resp.json()
        results = data.get("results", [])
        if results:
            print(f"  Search '{search_q or 'latest'}': {len(results)} pulses found")
            break
    else:
        return []

    events: list[dict[str, Any]] = []
    for pulse in results:
        tags      = pulse.get("tags", [])
        adversary = pulse.get("adversary", "") or ""
        grade     = _grade_pulse(tags, adversary)
        created   = pulse.get("created", "")

        # Count IoC types in this pulse
        indicators = pulse.get("indicators", [])
        ioc_counts: dict[str, int] = {}
        for ioc in indicators:
            t = ioc.get("type", "unknown")
            ioc_counts[t] = ioc_counts.get(t, 0) + 1

        # Grab first 3 IP indicators for the Neo4j example
        sample_ips = [
            i["indicator"] for i in indicators
            if i.get("type") in ("IPv4", "IPv6")
        ][:3]

        event: dict[str, Any] = {
            "source":          "alienvault_otx",
            "event_type":      "threat_pulse",
            "pulse_id":        pulse.get("id", ""),
            "pulse_name":      pulse.get("name", ""),
            "adversary":       adversary or "Unknown",
            "tags":            tags,
            "targeted_countries": pulse.get("targeted_countries", []),
            "malware_families": [m.get("display_name", "") for m in pulse.get("malware_families", [])],
            "created":         created,
            "modified":        pulse.get("modified", ""),
            "ioc_count":       len(indicators),
            "ioc_types":       ioc_counts,
            "sample_ips":      sample_ips,
            "confidence":      min(0.5 + len(tags) * 0.05, 0.95),
            "threat_grade":    grade,
            "reference_urls":  pulse.get("references", [])[:2],
            # ── Neo4j edge template ───────────────────────────────────────────
            "neo4j_cypher_hint": (
                f"(:ThreatActor {{name: '{adversary or 'Unknown'}'}}) "
                f"-[:EXECUTED_CAMPAIGN {{pulse: '{pulse.get('id','')}', "
                f"confidence: {min(0.5 + len(tags) * 0.05, 0.95):.2f}}}]"
                f"->(:Threat_Pulse {{name: '{pulse.get('name','')[:40]}'}})"
            ),
        }
        events.append(event)

    return events


def print_otx_samples(events: list[dict]) -> None:
    if not events:
        return

    for i, e in enumerate(events, 1):
        colour = grade_colour(e["threat_grade"])
        print(f"\n  {BOLD}[{i}] {e['pulse_name'][:70]}{RESET}")
        print(f"      Adversary   : {e['adversary']}")
        print(f"      Tags        : {', '.join(e['tags'][:6]) or 'none'}")
        print(f"      Countries   : {', '.join(e['targeted_countries'][:5]) or 'global'}")
        print(f"      Malware     : {', '.join(e['malware_families'][:3]) or 'unspecified'}")
        print(f"      IoCs        : {e['ioc_count']} total — {e['ioc_types']}")
        if e["sample_ips"]:
            print(f"      Sample IPs  : {', '.join(e['sample_ips'])}")
        print(f"      Confidence  : {e['confidence']:.0%}")
        print(f"      Grade       : {colour}{e['threat_grade']}{RESET}")
        print(f"      Created     : {e['created'][:10]}")
        if e["reference_urls"]:
            print(f"      References  : {e['reference_urls'][0]}")
        print(f"      {CYAN}Neo4j hint  : {e['neo4j_cypher_hint']}{RESET}")


# ══════════════════════════════════════════════════════════════════════════════
# 3.  HYBRID THREAT SCENARIO  — fuse both sources
# ══════════════════════════════════════════════════════════════════════════════

def print_hybrid_scenario(feodo_events: list[dict], otx_events: list[dict]) -> None:
    """Show what a fused Cyber-Physical alert looks like in Damocles."""
    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  DAMOCLES — Hybrid Threat Fusion Scenario{RESET}")
    print(f"{BOLD}{'═'*65}{RESET}")

    red_botnets = [e for e in feodo_events if e["threat_grade"] == "RED"]
    red_pulses  = [e for e in otx_events  if e["threat_grade"] == "RED"]

    if not red_botnets and not red_pulses:
        print(f"  No RED-grade events in current sample — try a broader query.")
        return

    botnet = red_botnets[0] if red_botnets else feodo_events[0] if feodo_events else None
    pulse  = red_pulses[0]  if red_pulses  else otx_events[0]   if otx_events  else None

    print(f"""
  SCENARIO: Coordinated Hybrid Attack on Greek Port Infrastructure
  ─────────────────────────────────────────────────────────────────

  LAYER 1 — Physical OSINT (already in Damocles):
    • Telegram channels show anti-Greek port rhetoric spike (+340% in 6h)
    • GDELT detects coordinated narrative: "Greek ports foreign control"

  LAYER 2 — Cyber Intelligence (NEW — from this sensor):""")

    if botnet:
        print(f"""    • Feodo Tracker: {botnet['ip_address']} ({botnet['country']})
      └─ Active C2 for {botnet['malware_family']} botnet (port {botnet['port']})
      └─ Threat Grade: {grade_colour(botnet['threat_grade'])}{botnet['threat_grade']}{RESET}""")

    if pulse:
        print(f"""    • OTX Pulse: "{pulse['pulse_name'][:55]}"
      └─ {pulse['ioc_count']} IoCs, adversary: {pulse['adversary']}
      └─ Targeted: {', '.join(pulse['targeted_countries'][:3]) or 'unspecified'}
      └─ Threat Grade: {grade_colour(pulse['threat_grade'])}{pulse['threat_grade']}{RESET}""")

    print(f"""
  LAYER 3 — Graph Fusion (Neo4j):

    (OSINT_Campaign)-[:PRECEDES {{gap_hours: 2.1}}]->
    (Cyber_Campaign)-[:TARGETS]->(:Infrastructure {{name: "Port of Piraeus"}})

  SUPERVISOR AGENT OUTPUT:
  ┌─────────────────────────────────────────────────────────────────┐
  │  {RED}{BOLD}⚠  COORDINATED HYBRID THREAT — HIGH CONFIDENCE (0.91){RESET}          │
  │                                                                 │
  │  Disinformation campaign (Telegram + GDELT) and active C2      │
  │  botnet activity share a 2.1h temporal overlap targeting the   │
  │  same entity class (Greek port infrastructure).                 │
  │  Pattern matches historical hybrid operation signatures.        │
  │                                                                 │
  │  RECOMMENDED ACTION: Notify ADAE + activate port SOC protocol  │
  └─────────────────────────────────────────────────────────────────┘
""")


# ══════════════════════════════════════════════════════════════════════════════
# 4.  SAVE SAMPLES TO JSON
# ══════════════════════════════════════════════════════════════════════════════

def save_samples(feodo: list[dict], otx: list[dict]) -> None:
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "cyber_samples")
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if feodo:
        path = os.path.join(out_dir, f"feodo_{ts}.json")
        with open(path, "w") as f:
            json.dump(feodo, f, indent=2, default=str)
        print(f"  Feodo samples saved → {path}")

    if otx:
        path = os.path.join(out_dir, f"otx_{ts}.json")
        with open(path, "w") as f:
            json.dump(otx, f, indent=2, default=str)
        print(f"  OTX samples saved   → {path}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    otx_key = os.environ.get("OTX_API_KEY", "")

    print(f"\n{BOLD}{'═'*65}{RESET}")
    print(f"{BOLD}  DAMOCLES — Cyber Intelligence Data Demo{RESET}")
    print(f"{BOLD}{'═'*65}{RESET}")
    print(f"  Timestamp : {datetime.now(timezone.utc).isoformat()}")
    print(f"  OTX key   : {'✓ found' if otx_key else '✗ not set (Feodo only)'}")

    # ── Feodo (always) ────────────────────────────────────────────────────────
    feodo_events = fetch_feodo()
    print_feodo_samples(feodo_events)

    # ── OTX (if key present) ──────────────────────────────────────────────────
    otx_events: list[dict] = []
    if otx_key:
        otx_events = fetch_otx_pulses(otx_key)
        print_otx_samples(otx_events)
    else:
        print(f"\n{AMBER}  OTX_API_KEY not set — skipping AlienVault OTX.{RESET}")
        print(f"  Get a free key at https://otx.alienvault.com (takes 2 minutes)")

    # ── Hybrid scenario ───────────────────────────────────────────────────────
    if feodo_events or otx_events:
        print_hybrid_scenario(feodo_events, otx_events)

    # ── Save JSON samples ────────────────────────────────────────────────────
    print(f"\n{BOLD}Saving samples to data/cyber_samples/...{RESET}")
    save_samples(feodo_events, otx_events)


if __name__ == "__main__":
    main()
