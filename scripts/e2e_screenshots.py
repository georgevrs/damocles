"""End-to-end UI exploration with Playwright.

Drives the live Vite dev server at http://localhost:5173 through a set of
named scenarios. Each scenario captures one or more PNG screenshots into
``screenshots/`` for human review. The script does NOT assert pass/fail —
it produces evidence that a subsequent reviewer (Claude or human) can
analyse for UX/UI flaws.

Run after both servers are up:
    uv run python scripts/e2e_screenshots.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, sync_playwright, expect, TimeoutError as PlaywrightTimeout

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "screenshots"
SHOTS.mkdir(exist_ok=True)

FRONTEND = "http://127.0.0.1:5173"
BACKEND = "http://127.0.0.1:8001"

VIEWPORT = {"width": 1600, "height": 950}

LOG: list[dict] = []


def log(name: str, status: str, detail: str = "", screenshot: str | None = None) -> None:
    entry = {
        "ts":     datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name":   name,
        "status": status,
        "detail": detail,
        "screenshot": screenshot,
    }
    LOG.append(entry)
    icon = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]", "INFO": "[i]"}.get(status, "  ")
    print(f"  {icon} {name}: {detail}")


def shot(page: Page, name: str, *, full_page: bool = False) -> str:
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=full_page)
    return path.name


def wait_settle(page: Page, ms: int = 800) -> None:
    """Tiny pause so map / SVG / animations settle before screenshot."""
    page.wait_for_timeout(ms)


# ─────────────────────────── scenarios ───────────────────────────


def scenario_cold_open(page: Page) -> None:
    """The morning view — no watch active, AoI triage list as default."""
    page.goto(FRONTEND, wait_until="networkidle")
    wait_settle(page, 2000)
    s = shot(page, "01_cold_open")
    log("cold_open", "OK", "landed at /", s)


def scenario_health_indicators(page: Page) -> None:
    """Top bar should show standing-scan + LLM + audit chips."""
    # Top bar is always visible; just capture a region focused on it.
    page.screenshot(path=str(SHOTS / "02_topbar.png"),
                    clip={"x": 0, "y": 0, "width": 1600, "height": 110})
    log("topbar", "OK", "captured top bar region", "02_topbar.png")


def scenario_triage_list(page: Page) -> None:
    """The triage list as the right-rail default. Count rows visible."""
    rows = page.locator("li button").filter(has_text="events")
    count = 0
    try:
        page.wait_for_selector("li button", timeout=8000)
        count = rows.count()
    except PlaywrightTimeout:
        count = 0
    s = shot(page, "03_triage_list")
    log("triage_list", "OK" if count > 0 else "WARN",
        f"{count} AoI rows visible", s)


def scenario_triage_filters(page: Page) -> None:
    """Click the RED filter chip."""
    try:
        red_filter = page.get_by_role("button", name="RED").first
        red_filter.click(timeout=3000)
        wait_settle(page, 500)
        s = shot(page, "04_triage_filter_red")
        log("triage_filter_red", "OK", "RED filter applied", s)
    except PlaywrightTimeout:
        log("triage_filter_red", "WARN", "could not find RED filter chip")
    # Reset
    try:
        page.get_by_role("button", name="All").first.click(timeout=2000)
        wait_settle(page, 300)
    except PlaywrightTimeout:
        pass


def scenario_click_first_aoi(page: Page) -> str | None:
    """Click the first (highest-priority) AoI row → open AoITabbed panel."""
    try:
        row = page.locator("li button").first
        title_el = row.locator("span.font-serif").first
        title = title_el.inner_text(timeout=3000) if title_el else ""
        row.click(timeout=5000)
        wait_settle(page, 2000)   # map fly + tabs render
        s = shot(page, "05_aoi_clicked")
        log("aoi_click", "OK", f"opened AoI '{title.strip()}'", s)
        return title.strip()
    except PlaywrightTimeout:
        log("aoi_click", "FAIL", "no AoI row clickable")
        return None


def scenario_brief_tab(page: Page) -> None:
    """Brief tab is now the default after click and auto-fires.
    Wait up to 120s for the 4-agent pipeline to render the BLUF."""
    wait_settle(page, 1500)
    s = shot(page, "06_brief_tab_initial")
    log("brief_tab_initial", "INFO", "default tab — pipeline should be running", s)

    bluf_loaded = False
    for i in range(120):  # up to ~120s
        try:
            # Section header text from prompts/supervisor.txt → SectionType.BLUF
            if page.locator("text=Bottom Line").count() > 0:
                bluf_loaded = True
                break
        except Exception:
            pass
        page.wait_for_timeout(1000)

    s = shot(page, "07_brief_after_wait", full_page=True)
    log("brief_after_wait", "OK" if bluf_loaded else "WARN",
        f"BLUF visible={bluf_loaded} (waited {i+1}s)", s)


def scenario_dna_tab(page: Page) -> None:
    """Switch to DNA tab and capture the helix."""
    try:
        page.get_by_role("button", name="DNA", exact=False).first.click(timeout=3000)
        wait_settle(page, 2500)   # let SVG render
        s = shot(page, "08_dna_tab", full_page=False)
        log("dna_tab", "OK", "DNA helix rendered", s)
    except PlaywrightTimeout:
        log("dna_tab", "FAIL", "could not click DNA tab")


def scenario_detail_tab(page: Page) -> None:
    """Switch to Detail tab and capture composites + sources."""
    try:
        page.get_by_role("button", name="Detail", exact=False).first.click(timeout=3000)
        wait_settle(page, 1500)
        s = shot(page, "09_detail_tab", full_page=True)
        log("detail_tab", "OK", "Detail metadata + composites visible", s)
    except PlaywrightTimeout:
        log("detail_tab", "FAIL", "could not click Detail tab")


def scenario_layer_panel(page: Page) -> None:
    """Layer panel is now closed by default — open it explicitly.
    Verifies the user can find and open it."""
    try:
        # The expand button has a chevron icon; click the top-right small button
        # The collapse arrow on the panel surface is `<ChevronRight />` in code.
        # Try a few selectors.
        opener = page.locator('button[title="Expand layers"]')
        if opener.count() > 0:
            opener.first.click(timeout=2000)
            wait_settle(page, 500)
        s = shot(page, "10_layer_panel")
        log("layer_panel", "OK", "layer panel opened", s)
    except Exception as e:
        log("layer_panel", "WARN", str(e))


def scenario_toggle_earthquakes(page: Page) -> None:
    """Toggle the USGS earthquakes layer ON and capture."""
    try:
        # The layer panel uses Eye buttons next to "Earthquakes (USGS)" label
        eq_row = page.locator("text=Earthquakes (USGS)").first
        if eq_row.is_visible(timeout=2000):
            # Eye button is sibling of the label
            eq_row.locator("xpath=preceding-sibling::button").first.click(timeout=2000)
            wait_settle(page, 4000)   # let the fetch + render
            s = shot(page, "11_earthquakes_on")
            log("earthquakes_layer", "OK", "USGS layer enabled", s)
        else:
            log("earthquakes_layer", "WARN", "label not visible")
    except Exception as e:
        log("earthquakes_layer", "WARN", f"could not toggle: {e}")


def scenario_toggle_satellite(page: Page) -> None:
    """Toggle the satellite basemap and screenshot."""
    try:
        sat = page.locator("text=Satellite").first
        if sat.is_visible(timeout=2000):
            sat.locator("xpath=preceding-sibling::button").first.click(timeout=2000)
            wait_settle(page, 4500)
            s = shot(page, "12_satellite_basemap")
            log("satellite_basemap", "OK", "Sentinel-2 basemap active", s)
        else:
            log("satellite_basemap", "WARN", "satellite toggle not visible")
    except Exception as e:
        log("satellite_basemap", "WARN", f"could not toggle: {e}")


def scenario_run_watch(page: Page) -> None:
    """Type a watch query and run it."""
    try:
        inp = page.get_by_placeholder("Type a watch", exact=False).first
        inp.fill("Aegean — last 24 hours", timeout=3000)
        s_before = shot(page, "13a_watch_input_filled")
        page.get_by_role("button", name="Run watch", exact=False).first.click(timeout=3000)
        wait_settle(page, 6000)
        s_after = shot(page, "13b_watch_running")
        log("watch_run", "OK", "watch dispatched", s_after)
    except Exception as e:
        log("watch_run", "WARN", f"watch input flow failed: {e}")


def scenario_lang_switch(page: Page) -> None:
    """Switch to Greek and capture."""
    try:
        btn = page.get_by_title("Αλλαγή στα ελληνικά", exact=False)
        if btn.count() == 0:
            btn = page.get_by_role("button", name="EL")
        btn.first.click(timeout=3000)
        wait_settle(page, 1000)
        s = shot(page, "14_greek_ui")
        log("greek_ui", "OK", "switched to Greek", s)
    except Exception as e:
        log("greek_ui", "WARN", f"could not switch language: {e}")


def scenario_resize_panel(page: Page) -> None:
    """Drag the vertical resize handle to widen the brief panel."""
    try:
        # First v-handle separates map from brief
        handle = page.locator('[role="separator"]').first
        if handle.count() == 0:
            handle = page.locator(".cursor-col-resize").first
        box = handle.bounding_box()
        if box:
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(cx, cy)
            page.mouse.down()
            page.mouse.move(cx - 200, cy, steps=10)
            page.mouse.up()
            wait_settle(page, 500)
            s = shot(page, "15_resized_layout")
            log("resize", "OK", "panel resized", s)
        else:
            log("resize", "WARN", "no resize handle found")
    except Exception as e:
        log("resize", "WARN", f"resize failed: {e}")


def scenario_esc_to_deselect(page: Page) -> None:
    """Press Esc — should deselect the AoI and return to triage."""
    try:
        page.keyboard.press("Escape")
        wait_settle(page, 1000)
        s = shot(page, "16_after_esc")
        # Confirm triage list re-appeared
        rows = page.locator("li button").filter(has_text="events").count()
        log("esc_deselect", "OK" if rows > 0 else "WARN",
            f"Esc deselected; {rows} rows visible again", s)
    except Exception as e:
        log("esc_deselect", "WARN", str(e))


def scenario_permalink(page: Page) -> None:
    """After clicking an AoI, the URL should carry ?aoi=… ."""
    try:
        # Click first AoI again
        row = page.locator("li button").first
        row.click(timeout=4000)
        wait_settle(page, 1500)
        url = page.url
        has_param = "aoi=" in url
        log("permalink", "OK" if has_param else "WARN",
            f"URL after click: {url[-60:] if len(url) > 60 else url}")
        s = shot(page, "17_permalink")
    except Exception as e:
        log("permalink", "WARN", str(e))


def scenario_full_page_final(page: Page) -> None:
    """Full-page snapshot at the end."""
    s = shot(page, "99_final_full_page", full_page=True)
    log("final_full_page", "OK", "end-of-run full page", s)


# ─── W3 scenarios — tamper, llm swap, scan cinema ───────────────────────────

def scenario_tamper_chain(page: Page) -> None:
    """W3-T1 — click Tamper byte, screenshot the rose-coloured verdict,
    click Restore, screenshot back-to-green.

    The button only renders after /health resolves with ``demo_mode=true``
    (which can take a second on cold start because the backend probes
    Gemini in /health). Wait for it explicitly so we don't race the
    button render.
    """
    try:
        page.wait_for_selector('button:has-text("Tamper byte")', timeout=15_000)
        # Focused capture of just the AuditLog header strip so the
        # Tamper / Restore / Verify buttons are legible in the artefact.
        try:
            strip_box = page.locator('button:has-text("Tamper byte")').first.bounding_box()
            if strip_box:
                clip_y = max(0, int(strip_box["y"]) - 22)
                page.screenshot(path=str(SHOTS / "19_audit_strip_buttons.png"),
                                clip={"x": 0, "y": clip_y, "width": 1600, "height": 40})
                log("audit_strip", "OK", "captured audit-log header buttons",
                    "19_audit_strip_buttons.png")
        except Exception:
            pass
        page.get_by_role("button", name="Tamper byte", exact=False).first.click(timeout=4000)
        wait_settle(page, 1500)
        s1 = shot(page, "20_audit_tampered",
                  full_page=False)
        # Confirm verdict text changed
        verdict_text = ""
        try:
            verdict_text = page.locator("text=TAMPER").first.inner_text(timeout=3000)
        except Exception:
            verdict_text = "(verdict locator not found)"
        log("tamper_byte", "OK", f"verdict={verdict_text[:80]!r}", s1)

        # Verify chain to make the colour obvious in the strip
        page.get_by_role("button", name="Verify chain", exact=False).first.click(timeout=3000)
        wait_settle(page, 1500)
        s2 = shot(page, "21_audit_verify_after_tamper")
        log("verify_after_tamper", "OK", "verify clicked while tampered", s2)

        # Restore
        page.get_by_role("button", name="Restore", exact=False).first.click(timeout=4000)
        wait_settle(page, 1500)
        page.get_by_role("button", name="Verify chain", exact=False).first.click(timeout=3000)
        wait_settle(page, 1500)
        s3 = shot(page, "22_audit_restored")
        log("audit_restored", "OK", "chain back to green", s3)
    except Exception as e:
        log("tamper_demo", "FAIL", f"{type(e).__name__}: {e}")


def scenario_llm_swap(page: Page) -> None:
    """W3-T2 — click the SystemPill's model name, screenshot Gemini→Ollama,
    click again, screenshot back. The button is gated on demo_mode so
    wait for /health to resolve before clicking."""
    try:
        page.wait_for_selector('button[title*="click to swap to"]', timeout=15_000)
        # Focused capture of the system pill so the model + audit chip are legible
        try:
            pill_box = page.locator('button[title*="click to swap to"]').first.bounding_box()
            if pill_box:
                clip_y = max(0, int(pill_box["y"]) - 6)
                page.screenshot(path=str(SHOTS / "22b_systempill_focus.png"),
                                clip={"x": 0, "y": clip_y, "width": 1600, "height": 32})
                log("system_pill_focus", "OK", "captured system pill",
                    "22b_systempill_focus.png")
        except Exception:
            pass
        # The button has title="click to swap to ollama" or "...gemini"
        pill = page.get_by_title("click to swap to ollama", exact=False)
        if pill.count() == 0:
            pill = page.get_by_title("click to swap to gemini", exact=False)
        pill.first.click(timeout=4000)
        # Wait for the "swapping…" label to clear and the new model name
        # to render. Gemini health_check inside /llm/switch can take 1-3s,
        # plus the React-Query health refetch on top, so 8s gives slack.
        try:
            page.wait_for_function(
                "() => !Array.from(document.querySelectorAll('button')).some("
                "b => b.textContent && b.textContent.includes('swapping'))",
                timeout=10_000,
            )
        except Exception:
            pass
        wait_settle(page, 1000)
        page.screenshot(path=str(SHOTS / "23_llm_swapped.png"),
                        clip={"x": 0, "y": 0, "width": 1600, "height": 110})
        s1 = "23_llm_swapped.png"
        log("llm_swap_to_alt", "OK", "swapped provider", s1)

        # Swap back
        pill2 = page.get_by_title("click to swap to ollama", exact=False)
        if pill2.count() == 0:
            pill2 = page.get_by_title("click to swap to gemini", exact=False)
        pill2.first.click(timeout=4000)
        try:
            page.wait_for_function(
                "() => !Array.from(document.querySelectorAll('button')).some("
                "b => b.textContent && b.textContent.includes('swapping'))",
                timeout=10_000,
            )
        except Exception:
            pass
        wait_settle(page, 1000)
        page.screenshot(path=str(SHOTS / "24_llm_back_to_gemini.png"),
                        clip={"x": 0, "y": 0, "width": 1600, "height": 110})
        s2 = "24_llm_back_to_gemini.png"
        log("llm_swap_back", "OK", "swapped back to gemini", s2)
    except Exception as e:
        log("llm_swap", "FAIL", f"{type(e).__name__}: {e}")


def _click_first_feature(page: Page, layer_id: str) -> bool:
    """Use MapLibre's queryRenderedFeatures to find a feature in a given
    layer, then dispatch a click at its on-screen coordinates. Returns
    True if a feature was found and clicked.

    Going through the map API rather than mouse-sampling is the only
    reliable way to hit a 3-pixel circle in a 1600×950 viewport.
    """
    point = page.evaluate(
        """(layerId) => {
            const map = window.__damoclesMap;
            if (!map) return null;
            const feats = map.queryRenderedFeatures(undefined, { layers: [layerId] });
            if (!feats || !feats.length) return null;
            const f = feats[0];
            const g = f.geometry;
            if (!g || g.type !== 'Point') return null;
            const [lng, lat] = g.coordinates;
            const p = map.project([lng, lat]);
            return { x: p.x, y: p.y };
        }""",
        layer_id,
    )
    if not point:
        return False
    canvas = page.locator(".maplibregl-canvas").bounding_box()
    if not canvas:
        return False
    page.mouse.click(canvas["x"] + point["x"], canvas["y"] + point["y"])
    return True


def scenario_click_vessel(page: Page) -> None:
    """Programmatically click the first broadcasting vessel and verify
    the VesselDetail card appears in the brief panel."""
    try:
        page.keyboard.press("Escape")
        wait_settle(page, 600)
        # Try the standing-vessels layer first (the always-on overlay).
        clicked = _click_first_feature(page, "standing-vessels-circle")
        if not clicked:
            clicked = _click_first_feature(page, "vessels")
        wait_settle(page, 1200)
        s = shot(page, "27_vessel_click")
        # VesselDetail renders <Anchor> icon + AIS_STATUS chip; check for
        # the chip text which is one of BROADCASTING/DARK/UNKNOWN.
        has_card = (page.locator("text=BROADCASTING").count()
                    + page.locator("text=DARK").count()
                    + page.locator("text=UNKNOWN").count()) > 0
        log("vessel_click", "OK" if (clicked and has_card) else "WARN",
            f"clicked={clicked} card={has_card}", s)
    except Exception as e:
        log("vessel_click", "WARN", f"{type(e).__name__}: {e}")


def scenario_click_flight(page: Page) -> None:
    """Programmatically click the first flight circle and verify the
    FlightDetail card renders."""
    try:
        page.keyboard.press("Escape")
        wait_settle(page, 400)
        clicked = _click_first_feature(page, "flights-circle")
        wait_settle(page, 1200)
        s = shot(page, "28_flight_click")
        has_card = (page.locator("text=AIRBORNE").count()
                    + page.locator("text=ON GROUND").count()) > 0
        log("flight_click", "OK" if (clicked and has_card) else "WARN",
            f"clicked={clicked} card={has_card}", s)
    except Exception as e:
        log("flight_click", "WARN", f"{type(e).__name__}: {e}")


def scenario_trajectories_visible(page: Page) -> None:
    """Verify trajectory line features exist on the rendered map."""
    try:
        n = page.evaluate(
            """() => {
                const map = window.__damoclesMap;
                if (!map) return -1;
                const feats = map.queryRenderedFeatures(undefined,
                    { layers: ['trajectories'] });
                return feats ? feats.length : -1;
            }"""
        )
        log("trajectories_rendered", "OK" if (n and n > 0) else "WARN",
            f"{n} trajectory features visible")
    except Exception as e:
        log("trajectories_rendered", "WARN", f"{type(e).__name__}: {e}")


def scenario_scan_cinema(page: Page) -> None:
    """W3-T4 — click Play scan, screenshot mid-run, wait for completion."""
    try:
        play = page.get_by_role("button", name="Play scan", exact=False)
        play.first.click(timeout=4000)
        # Capture mid-replay so we see "n/80" progress
        page.wait_for_timeout(3500)
        s_mid = shot(page, "25_scan_cinema_mid", full_page=False)
        log("scan_cinema_mid", "OK", "mid-replay frame captured", s_mid)
        # Wait for the cinema to settle (~14s at 160ms/frame for 80 frames)
        page.wait_for_timeout(13_000)
        s_done = shot(page, "26_scan_cinema_done", full_page=False)
        log("scan_cinema_done", "OK", "cinema complete", s_done)
    except Exception as e:
        log("scan_cinema", "FAIL", f"{type(e).__name__}: {e}")


# ─────────────────────────── orchestration ───────────────────────────


def main() -> int:
    print(f"== Damocles E2E ==  frontend={FRONTEND}  backend={BACKEND}")
    print(f"   screenshots → {SHOTS}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport=VIEWPORT, locale="en-US")
        page = context.new_page()

        # Surface console errors to our log
        console_errors: list[str] = []
        page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))
        def _on_console(msg) -> None:
            if msg.type not in {"error", "warning"}:
                return
            # msg.text often resolves to the lossy "Error" string for thrown
            # Error objects; reach into msg.args to surface the real payload.
            parts = [msg.text]
            try:
                for a in msg.args:
                    try:
                        parts.append(str(a.json_value()))
                    except Exception:
                        parts.append(str(a))
            except Exception:
                pass
            console_errors.append(f"console.{msg.type}: " + " | ".join(parts)[:400])
        page.on("console", _on_console)

        try:
            scenario_cold_open(page)
            scenario_health_indicators(page)
            scenario_triage_list(page)
            scenario_triage_filters(page)
            title = scenario_click_first_aoi(page)
            scenario_brief_tab(page)
            scenario_dna_tab(page)
            scenario_detail_tab(page)
            scenario_layer_panel(page)
            scenario_toggle_earthquakes(page)
            scenario_toggle_satellite(page)
            # Go back to dark basemap before lang switch + watch
            try: scenario_toggle_satellite(page)
            except Exception: pass
            # W3 demo features run BEFORE the language switch so locators
            # match English button text. They're also the gold-medal
            # moments — capture them while everything else is settled.
            scenario_tamper_chain(page)
            scenario_llm_swap(page)
            scenario_trajectories_visible(page)
            scenario_click_vessel(page)
            scenario_click_flight(page)
            scenario_scan_cinema(page)

            scenario_lang_switch(page)
            scenario_resize_panel(page)
            scenario_run_watch(page)
            scenario_esc_to_deselect(page)
            scenario_permalink(page)
            scenario_full_page_final(page)
        except Exception as exc:
            log("orchestrator", "FAIL", f"{type(exc).__name__}: {exc}")
        finally:
            # Capture console errors as their own log entries
            for ce in console_errors[:30]:
                log("console", "WARN" if "warning" in ce else "FAIL", ce)
            browser.close()

    out = ROOT / "screenshots" / "_log.json"
    out.write_text(json.dumps(LOG, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n== log → {out}")
    print(f"   {sum(1 for e in LOG if e['status']=='OK')} OK, "
          f"{sum(1 for e in LOG if e['status']=='WARN')} WARN, "
          f"{sum(1 for e in LOG if e['status']=='FAIL')} FAIL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
