# OAC Minutes

Drop an OAC (Owner–Architect–Contractor) meeting transcript into the app and get back:

1. **The issued minutes in the firm's format**, as a Word document.
2. **An open-items log that carries forward from meeting to meeting**: every prior item is accounted for, resolved items are marked closed, anything past its date is flagged overdue, and items nobody mentioned are carried forward and marked as such instead of silently disappearing.

That second part is the point. Generic note-takers summarize one meeting at a time. Owner's Project Manager (OPM) firms live off a running list that keeps its item numbers for months, and a PM currently rebuilds it by hand every week.

## Start it

**Double-click** `start.command` (Mac) or `start.bat` (Windows). The first run sets itself up (about a minute); after that it opens the app in your browser at http://localhost:8501. Keep the window open while you use it.

Put your Claude API key in a file named `.env` next to `app.py` (copy `.env.example`). Without a key the app runs in demo mode and can only process the bundled sample transcripts.

From a terminal instead:

```bash
cd oac-minutes
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Python 3.10 or newer is required.

## Use it

1. Create a project (top right) or press **Try it with the sample project**.
2. **Drop the transcript** (.vtt from Zoom/Teams/Meet, .txt, .docx, .srt, .md). Drop several meetings at once and they are processed in order. The app reads the meeting number and date from the file name or the first minute of the transcript; fix them in the table if it guessed wrong.
3. Press **Create minutes**. Each meeting gets a card with the minutes (.docx), the open-items log (.xlsx), a preview, and a short list of things worth a look before sending (unclear owners, dates the transcript didn't state, an item that looks like a duplicate).
4. The **Open items** table underneath is always current. Correct an item there if something closed by email between meetings; the next meeting's minutes pick that up.
5. Got the extraction wrong? **Undo last meeting** under "Issued meetings" and drop the file again.

The firm's details (name, who prepares the minutes, distribution, usual attendees, a glossary for the transcript reader) live under **Settings**.

### Recordings

Audio and video uploads go through a pluggable speech-to-text step. The bundled provider is local `faster-whisper` (`pip install faster-whisper`), which keeps recordings on the PM's machine. It is optional and was not exercised in this environment; the transcript path is the tested one. Zoom, Teams and Otter all export transcripts that work directly.

## Fit it to a firm

A firm's format is a JSON file (see `oacminutes/formats/`): header fields, the ordered sections with a hint per section telling the transcript reader what the firm files there, the open-items table columns, numbering style (`3.04` meeting.item or sequential), status labels, disclaimer, fonts.

To onboard a firm, open **Settings → Add a format from a sample of the firm's minutes** and upload one of their issued minutes documents. The app proposes a format file, saves it under `data/formats/`, and applies it. Review it against the sample and edit the JSON where the proposal missed something. The same works from the command line:

```bash
python -m oacminutes.format_from_minutes "their minutes.docx" --firm "Their Firm" --out data/formats/their-firm.json
```

Then run two consecutive real meetings through the app and compare the output with the minutes the firm actually issued; adjust the section hints and the glossary until the differences are ones the firm would not care about.

## How it works

```
transcript files ──► meeting number/date detected ──► Claude reads each transcript against the
                                                      project's prior open items and returns
                                                      structured content (sections, decisions,
                                                      one update per prior item, new items)
                                                                 │
                                                                 ▼
                                                  deterministic carry-forward engine
                                                  (numbering, closed/overdue/not-discussed,
                                                   history log, duplicate warnings)
                                                                 │
                                              ┌──────────────────┴──────────────────┐
                                              ▼                                     ▼
                                   minutes .docx in the firm's format      open-items log .xlsx / .csv
```

The language model never decides what happens to the tracker; it only reports what was said about each numbered item. Plain Python applies the rules, so the log is reproducible and a meeting can be undone and redone.

| Situation | What the engine does |
|---|---|
| Prior item discussed, still pending | Status stays open; the note, any new due date and any reassignment are appended to the item's history |
| Prior item reported complete | Closed with the closing note; shown once more in these minutes, then dropped from the log |
| Prior item never mentioned | Carried forward with "Not discussed – carried forward." in its history and flagged in the results |
| Prior item deferred | On hold; not counted as overdue |
| Open item whose due date is before the meeting date | Flagged **OVERDUE** in the minutes and the log; computed from dates, never asserted by the model |
| New action item | Numbered `meeting.seq` (or sequentially), stamped with the meeting it was raised at, warned if it looks like a duplicate of an open item |
| Closed item raised again | Reopened, with the reopening logged |

## Configuration

| Variable (in `.env` or the environment) | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API credentials (or `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile) |
| `OACMINUTES_EXTRACTOR` | `auto` (default: Claude when credentials exist, else demo), `claude`, or `mock`/`demo` |
| `OACMINUTES_MODEL` | Override the model id (default `claude-opus-5-5`) |
| `OACMINUTES_DATA_DIR` | Where the SQLite database, uploads, formats and generated files live (default `./data`) |
| `OACMINUTES_FIRM_NAME` | Firm name used until it is set in Settings |
| `OACMINUTES_TRANSCRIBER` / `OACMINUTES_WHISPER_MODEL` | Speech-to-text provider and Whisper model size for recordings |

Cost: a one-hour meeting is roughly 12–15k input tokens and a few thousand output tokens, on the order of 10–30 cents per meeting at Opus 5.5 list prices. The system prompt is marked cacheable so repeat meetings on the same project cost less. Transcripts are sent to the Claude API; recordings transcribed with the local provider never leave the machine.

## Hosting

For a shared URL, deploy from GitHub on Streamlit Community Cloud: main file `oac-minutes/app.py`, and put `ANTHROPIC_API_KEY = "..."` in the app's Secrets. Files there are wiped on restart, so treat it as a demo or a pilot, not the system of record.

## Project layout

```
oac-minutes/
  app.py                     the one-screen Streamlit app
  start.command / start.bat  double-click launchers
  oacminutes/
    models.py                Pydantic models (firm format, project, meeting, items, extraction schema)
    carryforward.py          the open-items engine (pure Python, no network)
    extract.py               ClaudeExtractor (structured output, caching, fallbacks) + MockExtractor
    pipeline.py              draft -> finalize; batch; undo/replay
    detect.py                meeting number/date from file names and transcript openings
    format_from_minutes.py   propose a firm format from a sample minutes document
    parsers.py               .txt/.md/.vtt/.srt/.docx -> text
    transcription.py         audio -> text adapter (faster-whisper, optional)
    storage.py               SQLite store
    render_docx.py / render_md.py / render_xlsx.py
    formats/                 built-in firm formats (JSON)
    samples/                 demo project: 3 transcripts + extraction fixtures (invented names)
  tests/                     pytest suite; run `python -m pytest`
```

## Not built yet

- Accounts, roles and multi-user access; the app is single-tenant and stores everything in a local SQLite file.
- Emailing the issued minutes to the distribution list.
- Integrations with Procore, e-Builder or other PMIS tools.
- Cloud speech-to-text providers (the adapter is pluggable; only local Whisper is wired).
