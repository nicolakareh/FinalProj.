"""Guess a meeting's number and date from the transcript file name or its opening lines.

PMs name files every which way ("OAC 12 - 9-15-26.docx", "GMT20260915-130004_Recording.vtt",
"oac_meeting_03.txt") and usually say the meeting number and date out loud in the first
minute. Guesses are shown for confirmation, never trusted silently.
"""
from __future__ import annotations

import re
from datetime import date

from .dates import parse_date

_NUMBER_WORDS = {w: i for i, w in enumerate(
    ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
     "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
     "nineteen", "twenty"])}
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"

_NUMBER_PATTERNS = [
    re.compile(r"(?:oac|owner|progress|meeting|mtg)[\s_#\-.]*(?:no\.?|number|#)?[\s_#\-.]*(\d{1,3})(?!\d)", re.I),
    re.compile(r"(?:meeting|mtg)[\s_#\-.]*(?:no\.?|number|#)?[\s_#\-.]*(" + "|".join(_NUMBER_WORDS) + r")(?![a-z])", re.I),
    re.compile(r"#\s?(\d{1,3})(?!\d)"),
]
_DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})"),                                 # 2026-09-15
    re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"),                                  # 20260915 (Zoom)
    re.compile(r"(?<![\d/])(\d{1,2})[-_./](\d{1,2})[-_./](20\d{2}|\d{2})(?![\d/])"),      # 9-15-26, 09/15/2026
    re.compile(r"\b(" + _MONTHS + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?(?:\s+(20\d{2}))?", re.I),  # September 15th, 2026
]


def _number_from(text: str) -> int | None:
    best: tuple[int, int] | None = None
    for pattern in _NUMBER_PATTERNS:
        m = pattern.search(text)
        if m and (best is None or m.start() < best[0]):
            raw = m.group(1).lower()
            value = int(raw) if raw.isdigit() else _NUMBER_WORDS.get(raw)
            if value:
                best = (m.start(), value)
    return best[1] if best else None


def _date_from(text: str, default_year: int | None) -> date | None:
    best: tuple[int, date] | None = None
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            groups = m.groups()
            if pattern is _DATE_PATTERNS[0] or pattern is _DATE_PATTERNS[1]:
                candidate = parse_date(f"{groups[0]}-{groups[1]}-{groups[2]}")
            elif pattern is _DATE_PATTERNS[2]:
                candidate = parse_date(f"{groups[0]}/{groups[1]}/{groups[2]}")
            else:
                candidate = parse_date(f"{groups[0]} {groups[1]}" + (f" {groups[2]}" if groups[2] else ""), default_year=default_year)
            if candidate and (best is None or m.start() < best[0]):
                best = (m.start(), candidate)
            if candidate:
                break
    return best[1] if best else None


def detect_meeting(file_name: str, transcript: str, *, default_year: int | None = None) -> tuple[int | None, date | None]:
    """Return (meeting_no, meeting_date); either may be None when nothing convincing is found."""
    head = transcript[:1500]
    number = _number_from(file_name) or _number_from(head[:800])
    when = _date_from(file_name, default_year) or _date_from(head, default_year)
    return number, when
