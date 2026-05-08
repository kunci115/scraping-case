"""
Level 2 — Maggioli PortaleAppalti scraper.

Explore the portal at http://127.0.0.1:18080/PortaleAppalti/it/homepage.wp
with a real browser before writing code.
"""
from __future__ import annotations
from models import TenderResult


async def scrape_portal(base_url: str) -> list[TenderResult]:
    """Scrape all tenders from the Maggioli-style portal at base_url."""
    raise NotImplementedError
