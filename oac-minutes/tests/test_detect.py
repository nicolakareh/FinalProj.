from datetime import date

import pytest

from oacminutes.detect import detect_meeting
from oacminutes.samples import sample_transcript


@pytest.mark.parametrize("name,text,expected", [
    ("OAC 12 - 9-15-26.docx", "", (12, date(2026, 9, 15))),
    ("OAC-12_2026-09-15.vtt", "", (12, date(2026, 9, 15))),
    ("Meeting #7 09.22.2026.txt", "", (7, date(2026, 9, 22))),
    ("GMT20260915-130004_Recording.transcript.vtt", "", (None, date(2026, 9, 15))),
    ("oac_meeting_03.txt", "", (3, None)),
    ("notes.txt", "Dana: Okay, this is OAC meeting number four for the station, September 22nd. Let's start.", (4, date(2026, 9, 22))),
    ("notes.txt", "Dana: OAC meeting twelve, 10/6/26, nine o'clock.", (12, date(2026, 10, 6))),
    ("notes.txt", "Nothing useful here. Item 1.01 is due 9/4.", (None, None)),
])
def test_detect_from_names_and_content(name, text, expected):
    assert detect_meeting(name, text, default_year=2026) == expected


def test_detect_on_bundled_samples():
    for n in (1, 2, 3):
        text = sample_transcript(f"oac_meeting_0{n}.txt")
        number, when = detect_meeting("transcript.txt", text, default_year=2026)
        assert number == n
        assert when == {1: date(2026, 9, 1), 2: date(2026, 9, 8), 3: date(2026, 9, 15)}[n]


def test_file_name_wins_over_content():
    text = sample_transcript("oac_meeting_02.txt")
    assert detect_meeting("OAC 9 - 2026-10-20.txt", text, default_year=2026) == (9, date(2026, 10, 20))
