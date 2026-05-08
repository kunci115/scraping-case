"""
Level 3 — ANAC Dettaglio CIG enrichment.

SPA flow on /cig/{cig}:
  1. Page boots (1s JS init)
  2. Consent checkbox click → 1.5s mosparo validation → sets _mosparo_session cookie
  3. "Cerca" button click → POST /api/v1/operations/consultaCIG/1.0/exec
  4. JSON result rendered into #result div
"""
from __future__ import annotations
import asyncio
import json
from playwright.async_api import async_playwright, Page
from models import CIGDetail


def _parse_cig_detail(cig: str, data: dict | list) -> CIGDetail | None:
    # API may return a plain dict or a single-element list depending on the CIG record
    if isinstance(data, list):
        data = data[0] if data else {}
    bando = data.get("bando") or {}
    if not bando:
        return None
    sa = bando.get("STAZIONE_APPALTANTE") or {}
    return CIGDetail(
        cig=bando.get("CIG") or cig,
        numero_gara=bando.get("NUMERO_GARA"),
        procedure_type=bando.get("TIPO_SCELTA_CONTRAENTE"),
        description=bando.get("OGGETTO_GARA"),
        cpv_codes=bando.get("CPV"),
        amount=bando.get("IMPORTO"),
        start_date=bando.get("DATA_AVVIO"),
        contracting_body=sa.get("DENOMINAZIONE"),
        contracting_body_cf=sa.get("CF"),
    )


async def _spa_flow(page: Page, cig: str, base_url: str) -> CIGDetail | None:
    """Full SPA interaction — establishes _mosparo_session cookie as a side effect."""
    await page.goto(f"{base_url}/cig/{cig}", wait_until="domcontentloaded")
    # Wait for SPA to finish 1s boot and render the form
    await page.wait_for_selector("#consent-check", timeout=5000)
    # Checkbox click triggers 1.5s mosparo validation, then sets cookie and enables button
    await page.click("#consent-check")
    await page.wait_for_selector("#cerca-btn:not([disabled])", timeout=5000)
    await page.click("#cerca-btn")
    # Wait until #result has content other than the loading message
    await page.wait_for_function(
        "() => { const t = document.getElementById('result').textContent;"
        " return t.length > 0 && t !== 'Ricerca in corso...'; }",
        timeout=10000,
    )
    raw = await page.evaluate("document.getElementById('result').textContent")
    try:
        return _parse_cig_detail(cig, json.loads(raw))
    except Exception:
        return None


async def _api_call(page: Page, cig: str, base_url: str) -> CIGDetail | None:
    """Direct API call from within the browser context (reuses _mosparo_session cookie)."""
    data = await page.evaluate(
        """async (args) => {
            const r = await fetch(args.url, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({cig: args.cig})
            });
            if (!r.ok) return null;
            return r.json();
        }""",
        {"url": f"{base_url}/api/v1/operations/consultaCIG/1.0/exec", "cig": cig},
    )
    if not data:
        return None
    return _parse_cig_detail(cig, data)


async def enrich_cig(cig: str, base_url: str) -> CIGDetail | None:
    """Fetch detailed ANAC data for a single CIG via the SPA at base_url/cig/{cig}."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        result = await _spa_flow(page, cig, base_url)
        await browser.close()
        return result


async def enrich_batch(cigs: list[str], base_url: str) -> dict[str, CIGDetail | None]:
    """Fetch ANAC details for multiple CIGs, respecting rate limits."""
    if not cigs:
        return {}

    results: dict[str, CIGDetail | None] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        # First CIG: full SPA flow — this sets the _mosparo_session cookie
        results[cigs[0]] = await _spa_flow(page, cigs[0], base_url)

        # Remaining CIGs: skip SPA overhead, call API directly via browser fetch.
        # Cookie is already in the browser context from the first interaction.
        for cig in cigs[1:]:
            await asyncio.sleep(5)  # server rate limit: 1 request per 5s per IP
            try:
                results[cig] = await _api_call(page, cig, base_url)
            except Exception:
                results[cig] = None

        await browser.close()

    return results
