# OAC Minutes

Upload an OAC (Owner–Architect–Contractor) meeting transcript or recording and get back:

1. **Issued minutes in the firm's own format** as a Word document.
2. **An open-items log that carries forward from meeting to meeting**: every prior item is accounted for, resolved items are marked closed, anything past its date is flagged overdue, and items nobody mentioned are carried forward and marked as such instead of silently disappearing.

That second part is the point. Generic note-takers summarize one meeting at a time. Owner's Project Manager (OPM) firms live off a running list that keeps its item numbers for months, and a PM currently rebuilds it by hand every week.

## How it works

```
recording / transcript ──► parse ──► Claude reads the transcript against the
                                     project's prior open items and returns
                                     structured content (sections, decisions,
                                     one update per prior item, new items)
                                             │
                                             ▼
                              deterministic carry-forward engine
                              (numbering, closed/overdue/not-discussed,
                               history log, duplicate warnings)
                                             │
                     ┌───────────────────────┼───────────────────────┐
                     ▼                       ▼                       ▼
            review & edit in app     minutes .docx in the       open-items log
            (nothing is committed    firm's format              .xlsx / .csv
             until "Finalize")
```

The language model never decides what happens to the tracker; it only reports what was said about each numbered item. Plain Python applies the rules, so the log is reproducible and a meeting can be withdrawn and re-issued.

## Quick start

```bash
cd oac-minutes
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...      # omit to run in demo mode
streamlit run app.py
```

Then in the browser:

- Press **Load demo project** in the sidebar. It runs three consecutive sample OAC meetings for a fictional fire-station project through the whole pipeline, so you can see items get raised, skipped, revised, closed and flagged overdue.
- Or create a firm (pick a format template), create a project, and go to **New meeting**.

Without an API key the app runs in **demo mode** and can only process the bundled sample transcripts. With a key it uses Claude (`claude-opus-5-5` by default) with structured output, so the response is validated against the schema before it reaches the engine. Server-side refusal fallback is enabled by default (`fallbacks: "default"`), so a false-positive safety decline is re-run on Anthropic's recommended substitute model instead of failing the meeting.

## Using it for a real meeting

1. **New meeting** → check the meeting number and date (defaults to the next meeting), upload the transcript (`.txt`, `.md`, `.vtt` from Zoom/Teams/Meet, `.srt`, `.docx`) or paste it.
2. Press **Generate minutes**. The draft shows warnings first (things the PM should verify), then editable attendees, discussion by section, decisions, a table of every prior open item with its status for this meeting, and the new action items.
3. Fix anything, press **Apply edits & refresh preview** to see the minutes as they will read.
4. Press **Finalize & issue minutes**. The `.docx` and `.xlsx` are generated, the open-items log is committed, and the next meeting starts from it.

**Open items** shows the live log with overdue flags as of any date, filters, Excel/CSV export, and a between-meetings editor (for example an item closed by email). **Meeting history** keeps every issued meeting, its files and its transcript, and can withdraw the last issued meeting if it needs to be redone.

### Recordings

Audio and video uploads go through a pluggable speech-to-text step. The bundled provider is local `faster-whisper` (`pip install faster-whisper`), which keeps recordings on the PM's machine. It is optional and was not exercised in this environment; the transcript path is the tested one. Zoom, Teams and Otter all export transcripts that work directly.

## Firm formats

A firm's format is a JSON document (see `oacminutes/formats/`) and is fully editable in the **Firm format** tab:

- header fields and their labels
- the ordered list of sections, with a hint per section that guides the extractor ("what belongs here")
- the open-items table columns, labels and relative widths
- numbering style: `3.04` (meeting.item, the OPM convention) or sequential `A-004`
- status labels, the "not discussed" wording, the disclaimer, fonts and accent color

Two templates ship: **Standard OPM minutes** (ten sections, `3.04` numbering, history under each item) and **Compact action log** (five sections, sequential numbering). Add a new firm by exporting its current minutes into a format file once; every project of the firm then uses it.

## Carry-forward rules

| Situation | What the engine does |
|---|---|
| Prior item discussed, still pending | Status stays open; the note, any new due date and any reassignment are appended to the item's history |
| Prior item reported complete | Closed with the closing note; shown once more in these minutes, then dropped from the log |
| Prior item never mentioned | Carried forward with "Not discussed – carried forward." in its history and flagged in the draft |
| Prior item deferred | On hold; not counted as overdue |
| Open item whose due date is before the meeting date | Flagged **OVERDUE** in the minutes and the log; computed from dates, never asserted by the model |
| New action item | Numbered `meeting.seq` (or sequentially), stamped with the meeting it was raised at, warned if it looks like a duplicate of an open item |
| Closed item raised again | Reopened, with the reopening logged |

## Configuration

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API credentials (or `ANTHROPIC_AUTH_TOKEN`, or an `ant auth login` profile) |
| `OACMINUTES_EXTRACTOR` | `auto` (default: Claude when credentials exist, else demo), `claude`, or `mock`/`demo` |
| `OACMINUTES_MODEL` | Override the model id (default `claude-opus-5-5`) |
| `OACMINUTES_DATA_DIR` | Where the SQLite database, uploads and generated files live (default `./data`) |
| `OACMINUTES_TRANSCRIBER` | Speech-to-text provider for recordings (default `faster_whisper`) |
| `OACMINUTES_WHISPER_MODEL` | Whisper model size (default `base`) |

Cost: a one-hour meeting is roughly 12–15k input tokens and a few thousand output tokens, which is on the order of 10–30 cents per meeting at Opus 5.5 list prices. The system prompt is marked cacheable so repeat meetings on the same project cost less.

## Project layout

```
oac-minutes/
  app.py                     Streamlit UI
  oacminutes/
    models.py                Pydantic models (firm format, project, meeting, items, extraction schema)
    carryforward.py          the open-items engine (pure Python, no network)
    extract.py               ClaudeExtractor (structured output, caching, fallbacks) + MockExtractor
    pipeline.py              draft -> review -> finalize; withdraw/replay
    parsers.py               .txt/.md/.vtt/.srt/.docx -> text
    transcription.py         audio -> text adapter (faster-whisper, optional)
    storage.py               SQLite store
    render_docx.py / render_md.py / render_xlsx.py
    formats/                 built-in firm formats (JSON)
    samples/                 demo project: 3 transcripts + extraction fixtures
  tests/                     pytest suite (engine, parsers, storage, extractor, renderers, pipeline)
```

Run the tests with `python -m pytest` from `oac-minutes/`.

## Not built yet

- Accounts, roles and multi-user access; the app is single-tenant and stores everything in a local SQLite file.
- Hosting and billing. Streamlit Community Cloud or a small VM works for a pilot; per-firm pricing lives outside the app.
- Emailing the issued minutes to the distribution list.
- Integrations with Procore, e-Builder or other PMIS tools.
- Cloud speech-to-text providers (the adapter is pluggable; only local Whisper is wired).
