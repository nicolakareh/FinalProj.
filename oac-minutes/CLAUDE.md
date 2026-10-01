# OAC Minutes – notes for Claude Code

This folder is a Streamlit app for Owner's Project Manager (OPM) firms: an OAC meeting
transcript goes in, issued minutes in the firm's format (.docx) and an open-items log
(.xlsx) come out, and the log carries forward from meeting to meeting. Read `README.md`
for the user-facing description.

## What matters

- **The carry-forward engine is the product.** `oacminutes/carryforward.py` is pure,
  deterministic Python: items keep their number for life, untouched items are carried
  with a "not discussed" note, closed items show once then drop, overdue is computed from
  dates. The language model only reports what was said about each numbered item; it never
  decides the tracker. Keep that split.
- **A firm's format is data, not code.** `oacminutes/formats/*.json` (validated by
  `FirmFormat` in `models.py`) holds sections with hints, open-items columns, numbering,
  status labels, header fields and the disclaimer. Onboarding a firm means producing one
  of these files from the firm's real minutes. Section hints are read by the extractor,
  so write them the way the firm's minutes actually sort topics.
- **Minimal UI.** One screen: drop transcript files → minutes and log come out, with the
  open-items table underneath. Meeting numbers and dates are detected from file names and
  transcript openings (`detect.py`) and shown for confirmation. Prefer removing UI over
  adding it.

## Layout

```
app.py                     Streamlit UI (the only file that imports streamlit)
oacminutes/models.py       Pydantic models incl. MeetingExtraction (the LLM output schema)
oacminutes/extract.py      ClaudeExtractor (structured output, cached system prompt,
                           server-side fallbacks) + MockExtractor (fixtures, offline)
oacminutes/carryforward.py engine  ·  pipeline.py draft→finalize, process_batch, withdraw/replay
oacminutes/detect.py       meeting number/date guesses  ·  format_from_minutes.py format from a sample
oacminutes/parsers.py      .txt/.md/.vtt/.srt/.docx → text  ·  transcription.py audio (optional)
oacminutes/render_*.py     .docx / markdown / .xlsx+csv  ·  storage.py SQLite
oacminutes/samples/        demo project: 3 transcripts + extraction fixtures (invented names)
tests/                     pytest; run `python -m pytest` here (73 tests, no network)
```

## Working here

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- Run: `streamlit run app.py` or the launchers `start.command` / `start.bat`. The key is
  read from `.env` (see `.env.example`); without it the app is in demo mode and only the
  bundled samples work.
- Model calls go through `ClaudeExtractor.request_kwargs()`; change prompts in
  `build_system_prompt` / `build_user_prompt`, not in the UI.
- To fit a real firm: put a few of their issued minutes and the matching transcripts in
  `data/` (gitignored), derive a format with `python -m oacminutes.format_from_minutes`
  (or Settings → add a format from a sample) into `data/formats/<firm>.json`, run the
  transcripts through the app, and diff the output against the hand-made minutes.
  Tune the format hints and the extractor prompt until the differences are ones the
  firm would not care about. Turn the final agreed extraction into a fixture only if it
  contains no client data.

## Do not

- Commit client transcripts, minutes or trackers. `data/` is gitignored for that reason.
- Skip or weaken tests in `tests/test_carryforward.py` to make output "look right";
  change the rule deliberately and update the test with it.
- Add dependencies without a reason; the app must stay installable with one `pip install`.
- Add a second way to do something the UI already does.
