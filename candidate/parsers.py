"""
Level 1 — Parsing utilities for Italian procurement data.

Hints:
- Italian locale uses '.' as thousands separator and ',' as decimal separator
- Italian dates can appear as DD/MM/YYYY, "DD mese YYYY", or ISO YYYY-MM-DD
- A valid CIG is exactly 10 alphanumeric characters and is NOT a placeholder
"""
from __future__ import annotations
from datetime import date
import re


def parse_amount(raw: str) -> float | None:
    """Parse an Italian-format monetary amount into a float. Returns None if unparseable."""
    if not raw:
        return None
    s = raw.strip().replace("€", "").replace("EUR", "").replace(" ", "")
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


_IT_MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}

_CIG_PLACEHOLDERS = frozenset({"0000000000", "0000000001", "XXXXXXXXXX"})


def parse_date(raw: str) -> date | None:
    """Parse an Italian-format date string into a datetime.date. Returns None if unparseable."""
    if not raw:
        return None
    s = raw.strip()
    # ISO: YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    # DD/MM/YYYY
    m = re.fullmatch(r"(\d{1,2})/(\d{2})/(\d{4})", s)
    if m:
        return date(int(m[3]), int(m[2]), int(m[1]))
    # DD mese YYYY
    m = re.fullmatch(r"(\d{1,2})\s+(\w+)\s+(\d{4})", s)
    if m:
        month = _IT_MONTHS.get(m[2].lower())
        if month:
            return date(int(m[3]), month, int(m[1]))
    return None


def is_valid_cig(cig: str | None) -> bool:
    """Check whether a CIG is valid (10 alnum, not a placeholder)."""
    return (
        bool(cig)
        and len(cig) == 10
        and cig.isalnum()
        and cig not in _CIG_PLACEHOLDERS
    )
