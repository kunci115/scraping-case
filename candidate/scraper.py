"""
Level 2 — Maggioli PortaleAppalti scraper.

Explore the portal at http://127.0.0.1:18080/PortaleAppalti/it/homepage.wp
with a real browser before writing code.
"""
from __future__ import annotations
import asyncio
import re
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page
from models import TenderResult, DocumentRef
from candidate.parsers import parse_amount, parse_date, is_valid_cig


def _abs_url(href: str, base_url: str) -> str:
    """Resolve a document href to an absolute URL."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    base = base_url.rstrip("/")
    return base + (href if href.startswith("/") else "/" + href)


def _extract_docs_inline(soup: BeautifulSoup, base_url: str) -> list[DocumentRef]:
    allegati = soup.find("div", class_="allegati")
    if not allegati:
        return []
    return [
        DocumentRef(name=a.get_text(strip=True), url=_abs_url(a["href"], base_url))
        for a in allegati.find_all("a", href=True)
        if a.get_text(strip=True)
    ]


def _parse_layout0(soup: BeautifulSoup, base_url: str) -> dict:
    """<table class="dettaglio-bando"> — straightforward th/td rows."""
    data = {}
    for row in soup.select("table.dettaglio-bando tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            data[th.get_text(strip=True)] = td.get_text(strip=True)
    return {
        "cig": data.get("CIG", ""),
        "cup": data.get("CUP", ""),
        "amount": data.get("Importo a base di gara", ""),
        "deadline": data.get("Scadenza presentazione offerte", ""),
        "pub_date": data.get("Data pubblicazione", ""),
        "contracting_body": data.get("Stazione appaltante"),
        "procedure_type": data.get("Procedura"),
        "documents": _extract_docs_inline(soup, base_url),
    }


def _parse_layout1(soup: BeautifulSoup, tender_id: int, base_url: str) -> dict:
    """<dl class="dati-gara"> — amount is empty until inline JS fires."""
    data = {}
    dl = soup.find("dl", class_="dati-gara")
    if dl:
        for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
            data[dt.get_text(strip=True)] = dd.get_text(strip=True)

    # Inline IIFE sets #imp-{id} textContent synchronously on page load.
    # page.content() reflects the post-JS DOM, so this is populated.
    imp_el = soup.find(id=f"imp-{tender_id}")
    amount_raw = imp_el.get_text(strip=True) if imp_el else data.get("Importo a base di gara", "")

    return {
        "cig": data.get("Codice CIG", ""),
        "cup": data.get("Codice CUP", ""),
        "amount": amount_raw,
        "deadline": data.get("Termine presentazione offerte", ""),
        "pub_date": data.get("Data pubblicazione", ""),
        "contracting_body": data.get("Stazione appaltante"),
        "procedure_type": data.get("Tipo procedura"),
        "documents": _extract_docs_inline(soup, base_url),
    }


def _build_campo_map(soup: BeautifulSoup) -> dict[str, str]:
    """Single-pass scan of all campo-dato divs → label:value dict."""
    out: dict[str, str] = {}
    for div in soup.find_all("div", class_="campo-dato"):
        lbl = div.find("label")
        if lbl:
            span = div.find("span", class_="valore")
            out[lbl.get_text(strip=True)] = span.get_text(strip=True) if span else ""
    return out


async def _parse_layout2(page: Page, soup: BeautifulSoup, tender_id: int, base_url: str) -> dict:
    """Box layout — documents are JS-injected on button click."""
    docs: list[DocumentRef] = []
    btn = await page.query_selector(f"#btn-allegati-{tender_id}")
    if btn:
        await btn.click()
        try:
            await page.wait_for_selector(
                f"#allegati-container-{tender_id} a", timeout=5000
            )
        except Exception:
            pass
        content = await page.content()
        container = BeautifulSoup(content, "html.parser").find(
            id=f"allegati-container-{tender_id}"
        )
        if container:
            docs = [
                DocumentRef(name=a.get_text(strip=True), url=_abs_url(a["href"], base_url))
                for a in container.find_all("a", href=True)
                if a.get_text(strip=True)
            ]

    data = _build_campo_map(soup)
    return {
        "cig": data.get("CIG", ""),
        "cup": data.get("CUP", ""),
        "amount": data.get("Importo a base di gara", ""),
        "deadline": data.get("Scadenza presentazione offerte", ""),
        "pub_date": data.get("Data pubblicazione", ""),
        "contracting_body": data.get("Stazione appaltante"),
        "procedure_type": data.get("Procedura"),
        "documents": docs,
    }


async def _fetch_detail(page: Page, tender_id: int, base_url: str) -> dict:
    url = f"{base_url}/PortaleAppalti/it/ppgare_bando_dettaglio.wp?id={tender_id}"

    for attempt in range(2):
        resp = await page.goto(url, wait_until="domcontentloaded")
        if resp and resp.status == 503:
            if attempt == 0:
                await asyncio.sleep(1)
                continue
        break

    content = await page.content()
    soup = BeautifulSoup(content, "html.parser")

    if soup.find("table", class_="dettaglio-bando"):
        return _parse_layout0(soup, base_url)
    if soup.find("dl", class_="dati-gara"):
        return _parse_layout1(soup, tender_id, base_url)
    return await _parse_layout2(page, soup, tender_id, base_url)


async def scrape_portal(base_url: str) -> list[TenderResult]:
    """Scrape all tenders from the Maggioli-style portal at base_url."""
    results: list[TenderResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        # Homepage visit establishes JSESSIONID — required for all subsequent requests
        await page.goto(
            f"{base_url}/PortaleAppalti/it/homepage.wp", wait_until="domcontentloaded"
        )

        # Collect tender stubs from listing pages
        tender_stubs: list[tuple[int, str]] = []
        page_num = 1
        while True:
            await page.goto(
                f"{base_url}/PortaleAppalti/it/ppgare_bandi_lista.wp?page={page_num}",
                wait_until="domcontentloaded",
            )
            # FriendlyCaptcha overlay removed after 3s via JS; table becomes visible then
            await page.wait_for_selector("#tender-list", state="visible", timeout=10000)

            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            rows = soup.select("#tender-list tbody tr")
            if not rows:
                break

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                title = cells[0].get_text(strip=True)
                link = cells[1].find("a", href=True)
                if not link:
                    continue
                m = re.search(r"id=(\d+)", link["href"])
                if m:
                    tender_stubs.append((int(m.group(1)), title))

            if not soup.find("a", href=re.compile(rf"\?page={page_num + 1}")):
                break
            page_num += 1

        # Fetch and parse each detail page
        for tender_id, listing_title in tender_stubs:
            raw = await _fetch_detail(page, tender_id, base_url)

            cig_raw = (raw.get("cig") or "").strip()
            cup_raw = (raw.get("cup") or "").strip()

            results.append(TenderResult(
                tender_id=tender_id,
                cig=cig_raw if is_valid_cig(cig_raw) else None,
                cup=cup_raw or None,
                title=listing_title,
                amount=parse_amount(raw.get("amount") or ""),
                deadline=parse_date(raw.get("deadline") or ""),
                pub_date=parse_date(raw.get("pub_date") or ""),
                contracting_body=raw.get("contracting_body") or None,
                procedure_type=raw.get("procedure_type") or None,
                detail_url=f"{base_url}/PortaleAppalti/it/ppgare_bando_dettaglio.wp?id={tender_id}",
                documents=raw.get("documents", []),
            ))

        await browser.close()

    return results
