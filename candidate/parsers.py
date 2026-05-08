"""
Level 1 — Parsing utilities for Italian procurement data.

Hints:
- Italian locale uses '.' as thousands separator and ',' as decimal separator
- Italian dates can appear as DD/MM/YYYY, "DD mese YYYY", or ISO YYYY-MM-DD
- A valid CIG is exactly 10 alphanumeric characters and is NOT a placeholder
"""
from __future__ import annotations
from datetime import date


def parse_amount(raw: str) -> float | None:
    """Parse an Italian-format monetary amount into a float. Returns None if unparseable."""
    raise NotImplementedError


def parse_date(raw: str) -> date | None:
    """Parse an Italian-format date string into a datetime.date. Returns None if unparseable."""
    raise NotImplementedError


def is_valid_cig(cig: str | None) -> bool:
    """Check whether a CIG is valid (10 alnum, not a placeholder)."""
    raise NotImplementedError
