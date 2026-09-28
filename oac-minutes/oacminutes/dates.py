"""Tolerant date parsing/formatting helpers.

The extractor is asked for ISO dates, but transcripts (and people) say things
like "10/6" or "Oct 6". These helpers accept the common shapes and never raise.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"],
        start=1,
    )
}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9


def parse_date(value: object, default_year: int | None = None) -> date | None:
    """Parse a date from an ISO string or common US formats.

    Returns None when the value is empty or unparseable. ``default_year`` fills
    in a missing year (e.g. "10/6" -> 10/6 of that year).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "tbd", "n/a", "na", "-"}:
        return None

    # ISO 2026-10-06 or 2026-10-06T00:00:00
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # 10/6/2026, 10/6/26, 10-6-2026, 10/6
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year_raw = m.group(3)
        if year_raw is None:
            if default_year is None:
                return None
            year = default_year
        else:
            year = int(year_raw)
            if year < 100:
                year += 2000
        return _safe_date(year, month, day)

    # October 6, 2026 / Oct 6 2026 / 6 October 2026 / Oct 6
    m = re.match(r"^([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(\d{4}))?$", text)
    if m and m.group(1).lower() in _MONTHS:
        month = _MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else default_year
        if year is None:
            return None
        return _safe_date(year, month, day)
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\.?,?(?:\s+(\d{4}))?$", text)
    if m and m.group(2).lower() in _MONTHS:
        month = _MONTHS[m.group(2).lower()]
        day = int(m.group(1))
        year = int(m.group(3)) if m.group(3) else default_year
        if year is None:
            return None
        return _safe_date(year, month, day)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def fmt_date(value: date | None, pattern: str = "%m/%d/%Y") -> str:
    """Format a date, returning an empty string for None."""
    if value is None:
        return ""
    return value.strftime(pattern)
