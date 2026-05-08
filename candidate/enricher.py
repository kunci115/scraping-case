"""
Level 3 — ANAC Dettaglio CIG enrichment.

Explore /cig/{CIG} with DevTools to understand the SPA flow.
"""
from __future__ import annotations
from models import CIGDetail


async def enrich_cig(cig: str, base_url: str) -> CIGDetail | None:
    """Fetch detailed ANAC data for a single CIG via the SPA at base_url/cig/{cig}."""
    raise NotImplementedError


async def enrich_batch(cigs: list[str], base_url: str) -> dict[str, CIGDetail | None]:
    """Fetch ANAC details for multiple CIGs, respecting rate limits."""
    raise NotImplementedError
