"""Transcript -> :class:`MeetingExtraction`.

Two extractors share one interface:

* :class:`ClaudeExtractor` calls the Claude API with structured output, so the
  response is validated against the ``MeetingExtraction`` schema before the
  carry-forward engine ever sees it.
* :class:`MockExtractor` replays bundled fixtures for the sample transcripts.
  It powers the demo project and the test-suite without network access.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Protocol

from .dates import fmt_date
from .models import FirmFormat, MeetingExtraction, OpenItem, Project
from .parsers import normalize_transcript

DEFAULT_MODEL = "claude-opus-5-5"
SAMPLES_DIR = Path(__file__).parent / "samples"


class ExtractionError(RuntimeError):
    """A user-facing failure: missing credentials, refusal, truncated output, etc."""


@dataclass
class ExtractionContext:
    firm_name: str
    firm_format: FirmFormat
    project: Project
    meeting_no: int
    meeting_date: date
    prior_items: list[OpenItem] = field(default_factory=list)
    previous_meeting_date: date | None = None
    meeting_time: str = ""
    location: str = ""


class Extractor(Protocol):
    name: str

    def extract(self, transcript: str, ctx: ExtractionContext, *, source_name: str = "") -> MeetingExtraction: ...


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------
def build_system_prompt(ctx: ExtractionContext) -> str:
    """Stable per project, so it can be served from the prompt cache across meetings."""
    fmt = ctx.firm_format
    section_lines = "\n".join(
        f"- {s.key}: {s.title}" + (f" — {s.hint}" if s.hint else "") for s in fmt.sections
    )
    project = ctx.project
    context_lines = [
        f"Project: {project.name}" + (f" (No. {project.number})" if project.number else ""),
        f"Owner: {project.owner}" if project.owner else "",
        f"Owner's Project Manager (OPM): {project.opm_firm or ctx.firm_name}",
        f"Architect: {project.architect}" if project.architect else "",
        f"General Contractor / CM: {project.contractor}" if project.contractor else "",
        f"Location: {project.location}" if project.location else "",
    ]
    context = "\n".join(line for line in context_lines if line)
    attendees = project.default_attendees.strip()
    notes = project.extractor_notes.strip()
    return f"""You prepare formal OAC (Owner–Architect–Contractor) construction meeting minutes for {ctx.firm_name}, an Owner's Project Manager firm. You read a raw meeting transcript and return the structured content of the minutes.

Minutes style
- Write in past tense, third person, minute style: "GC reported…", "Architect to issue…". No filler, no quotes, no hedging.
- One topic per bullet. Keep every number, date, name, drawing/RFI/submittal reference exactly as spoken. Do not invent facts; if something is inaudible or unclear, say so in review_flags.
- Attribute statements to the party (Owner, OPM, Architect, GC, subcontractor by trade) and add the person's name when known.
- Put each discussion point under exactly one of the firm's sections, using the section key. Use "general" only when nothing else fits.

Firm's sections (key: title — what belongs there)
{section_lines}

Prior open items
- You will receive the list of open items carried from previous meetings, each with its item number. Return exactly one prior_item_updates entry for EVERY listed item, using its item number verbatim.
- status "closed" only when the item was explicitly reported complete, resolved, accepted, or no longer required.
- status "open" when it was discussed and is still pending: note what was said and, if a new date was agreed, put it in new_due_date (ISO YYYY-MM-DD).
- status "on_hold" when the group deferred it.
- status "not_discussed" when it never came up. Never omit an item.
- Progress on an existing item is an update, never a new item.

New action items
- A new item is a deliverable someone committed to: who does what, by when. Do not create items for general discussion or for things already covered by a prior item.
- responsible: party and person, e.g. "GC – J. Alvarez", "Architect", "Owner – Facilities".
- due_date: ISO date. Resolve relative dates ("Friday", "next week", "before the next meeting") using the meeting date you are given. If no date was stated, leave it null; do not guess.
- section_key: the firm section the item belongs under.
- note: one line of context worth keeping in the running log.

Also return: attendees (name, company, role, present), decisions formally made, next meeting details if stated, and review_flags listing anything the project manager should verify before issuing the minutes.

Project context
{context}
""" + (f"\nUsual attendees (for names and roles)\n{attendees}\n" if attendees else "") + (f"\nGlossary and notes from the project manager\n{notes}\n" if notes else "")


def format_prior_items(items: list[OpenItem], date_format: str = "%m/%d/%Y") -> str:
    if not items:
        return "(none – this is the first meeting or every item is closed)"
    lines = []
    for item in items:
        last = item.latest_note()
        lines.append(
            f"{item.item_number} | {item.description} | Responsible: {item.responsible or 'unassigned'} | "
            f"Due: {fmt_date(item.due_date, date_format) or 'none'} | Status: {item.status.value} | "
            f"Raised: Mtg {item.raised_meeting_no} ({fmt_date(item.date_raised, date_format)}) | "
            f"Last discussed: Mtg {item.last_discussed_meeting_no}" + (f" | Last note: {last}" if last else "")
        )
    return "\n".join(lines)


def build_user_prompt(transcript: str, ctx: ExtractionContext) -> str:
    prev = fmt_date(ctx.previous_meeting_date, ctx.firm_format.date_format) or "n/a"
    header = [
        f"Meeting number: {ctx.meeting_no}",
        f"Meeting date: {ctx.meeting_date.isoformat()} ({ctx.meeting_date.strftime('%A')})",
        f"Previous meeting date: {prev}",
    ]
    if ctx.meeting_time:
        header.append(f"Meeting time: {ctx.meeting_time}")
    if ctx.location:
        header.append(f"Location: {ctx.location}")
    return (
        "\n".join(header)
        + "\n\nPrior open items (item number | description | responsible | due | status | raised | last discussed | last note)\n"
        + format_prior_items(ctx.prior_items, ctx.firm_format.date_format)
        + "\n\nTranscript\n<transcript>\n"
        + transcript.strip()
        + "\n</transcript>\n\nReturn the structured minutes content for this meeting."
    )


def sanitize_extraction(extraction: MeetingExtraction, ctx: ExtractionContext) -> MeetingExtraction:
    """Coerce section keys the model made up into 'general' and drop empties."""
    valid = set(ctx.firm_format.section_keys()) | {"general"}
    merged: dict[str, list[str]] = {}
    for section in extraction.sections:
        key = section.section_key.strip().lower() if section.section_key in valid else "general"
        if section.section_key not in valid:
            extraction.review_flags.append(f"Extractor used unknown section '{section.section_key}'; moved to General.")
        merged.setdefault(key, []).extend(b.strip() for b in section.bullets if b.strip())
    extraction.sections = [type(extraction.sections[0])(section_key=k, bullets=v) for k, v in merged.items() if v] if extraction.sections else []
    for item in extraction.new_items:
        if item.section_key not in valid:
            item.section_key = "general"
    extraction.decisions = [d.strip() for d in extraction.decisions if d.strip()]
    return extraction


# --------------------------------------------------------------------------
# Claude
# --------------------------------------------------------------------------
class ClaudeExtractor:
    name = "claude"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        client=None,
        effort: str = "high",
        max_tokens: int = 32000,
        use_fallbacks: bool = True,
    ):
        self.model = model
        self._client = client
        self.effort = effort
        self.max_tokens = max_tokens
        self.use_fallbacks = use_fallbacks
        self.last_usage: dict | None = None
        self.last_request_id: str | None = None

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()  # ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / `ant auth login` profile
        return self._client

    def request_kwargs(self, transcript: str, ctx: ExtractionContext) -> dict:
        kwargs: dict = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": build_system_prompt(ctx), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": build_user_prompt(transcript, ctx)}],
            output_format=MeetingExtraction,
            output_config={"effort": self.effort},
        )
        if self.use_fallbacks:
            # Server-side fallback: a safety-classifier refusal is re-run on Anthropic's
            # recommended substitute model inside the same call instead of failing.
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        return kwargs

    def extract(self, transcript: str, ctx: ExtractionContext, *, source_name: str = "") -> MeetingExtraction:
        import anthropic

        if not transcript.strip():
            raise ExtractionError("The transcript is empty.")
        kwargs = self.request_kwargs(transcript, ctx)
        try:
            # Streaming keeps long transcripts clear of HTTP timeouts; we only need the final message.
            with self.client.beta.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ExtractionError("Claude API key is missing or invalid. Set ANTHROPIC_API_KEY and restart.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ExtractionError("The API key does not have permission for this model.") from exc
        except anthropic.NotFoundError as exc:
            raise ExtractionError(f"Model {self.model!r} was not found for this account.") from exc
        except anthropic.RateLimitError as exc:
            raise ExtractionError("Rate limited by the Claude API. Wait a minute and try again.") from exc
        except anthropic.APIStatusError as exc:
            raise ExtractionError(f"Claude API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ExtractionError("Could not reach the Claude API. Check the network connection.") from exc

        self.last_request_id = getattr(message, "_request_id", None)
        usage = getattr(message, "usage", None)
        self.last_usage = usage.model_dump(mode="json") if usage is not None else None

        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details is not None else None
            raise ExtractionError(
                "The model declined to process this transcript"
                + (f" (category: {category})" if category else "")
                + ". Review the transcript for content outside a construction meeting and try again."
            )
        if message.stop_reason == "max_tokens":
            raise ExtractionError("The response was cut off. Split the transcript in two and process each half.")

        parsed = getattr(message, "parsed_output", None)
        if parsed is None:
            text = next((b.text for b in message.content if getattr(b, "type", "") == "text"), "")
            try:
                parsed = MeetingExtraction.model_validate(json.loads(text))
            except (ValueError, json.JSONDecodeError) as exc:
                raise ExtractionError("The model returned something that is not valid minutes JSON.") from exc
        return sanitize_extraction(parsed, ctx)


# --------------------------------------------------------------------------
# Demo / test mode
# --------------------------------------------------------------------------
def transcript_fingerprint(transcript: str) -> str:
    return hashlib.sha256(normalize_transcript(transcript).encode("utf-8")).hexdigest()


class MockExtractor:
    """Replays a fixture chosen by file name or by transcript content."""

    name = "demo"

    def __init__(self, fixtures_dir: Path | None = None):
        self.fixtures_dir = fixtures_dir or SAMPLES_DIR
        self.by_stem: dict[str, dict] = {}
        self.by_hash: dict[str, dict] = {}
        for path in sorted(self.fixtures_dir.glob("*.extraction.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            stem = path.name[: -len(".extraction.json")].lower()
            self.by_stem[stem] = data
            for transcript_path in self.fixtures_dir.glob(f"{stem}.*"):
                if transcript_path.suffix in (".txt", ".md", ".vtt", ".srt"):
                    self.by_hash[transcript_fingerprint(transcript_path.read_text(encoding="utf-8"))] = data

    def extract(self, transcript: str, ctx: ExtractionContext, *, source_name: str = "") -> MeetingExtraction:
        stem = Path(source_name).stem.lower() if source_name else ""
        data = self.by_stem.get(stem) or self.by_hash.get(transcript_fingerprint(transcript))
        if data is None:
            raise ExtractionError(
                "Demo mode can only process the bundled sample transcripts. "
                "Set ANTHROPIC_API_KEY to process your own recordings and transcripts."
            )
        return sanitize_extraction(MeetingExtraction.model_validate(data), ctx)


def credentials_present() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    profile_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "anthropic"
    return profile_dir.exists()


def get_extractor(mode: str | None = None) -> Extractor:
    """auto (default): Claude when credentials exist, otherwise demo fixtures."""
    mode = (mode or os.environ.get("OACMINUTES_EXTRACTOR", "auto")).lower()
    if mode in ("mock", "demo"):
        return MockExtractor()
    if mode == "claude":
        return ClaudeExtractor(model=os.environ.get("OACMINUTES_MODEL", DEFAULT_MODEL))
    if credentials_present():
        return ClaudeExtractor(model=os.environ.get("OACMINUTES_MODEL", DEFAULT_MODEL))
    return MockExtractor()
