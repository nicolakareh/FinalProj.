from datetime import date
from types import SimpleNamespace

import pytest

from oacminutes.extract import (
    ClaudeExtractor,
    ExtractionContext,
    ExtractionError,
    MockExtractor,
    build_system_prompt,
    build_user_prompt,
    get_extractor,
    sanitize_extraction,
)
from oacminutes.formats import load_builtin_format
from oacminutes.models import Firm, MeetingExtraction, OpenItem, Project, SectionNotes
from oacminutes.samples import sample_transcript


def make_ctx(prior=()):
    firm = Firm(name="Acme OPM", format=load_builtin_format("standard_opm"))
    project = Project(firm_id=firm.id, name="Library", number="24-1", owner="Town of X", extractor_notes="DPW = public works")
    return ExtractionContext(firm_name=firm.name, firm_format=firm.format, project=project, meeting_no=2, meeting_date=date(2026, 9, 8), prior_items=list(prior), previous_meeting_date=date(2026, 9, 1))


def prior_item():
    return OpenItem(project_id="p", item_number="1.01", description="Submit schedule", responsible="GC", date_raised=date(2026, 9, 1), raised_meeting_no=1, due_date=date(2026, 9, 5), last_discussed_meeting_no=1)


def test_system_prompt_is_stable_and_describes_the_format():
    ctx = make_ctx()
    prompt = build_system_prompt(ctx)
    assert "Acme OPM" in prompt
    assert "- safety: Safety" in prompt and "- owner_items: Owner Items" in prompt
    assert "DPW = public works" in prompt
    assert "Town of X" in prompt
    assert build_system_prompt(ctx) == prompt  # deterministic -> cacheable


def test_user_prompt_lists_prior_items_and_transcript():
    ctx = make_ctx(prior=[prior_item()])
    prompt = build_user_prompt("Hello: world", ctx)
    assert "Meeting number: 2" in prompt
    assert "Previous meeting date: 09/01/2026" in prompt
    assert "1.01 | Submit schedule | Responsible: GC | Due: 09/05/2026 | Status: open" in prompt
    assert "<transcript>\nHello: world\n</transcript>" in prompt


def test_user_prompt_without_prior_items():
    assert "(none" in build_user_prompt("x", make_ctx())


def test_mock_extractor_by_stem_and_by_content():
    ctx = make_ctx()
    mock = MockExtractor()
    by_name = mock.extract("anything", ctx, source_name="OAC_Meeting_02.vtt")
    assert [u.item_number for u in by_name.prior_item_updates][:2] == ["1.01", "1.02"]
    by_content = mock.extract(sample_transcript("oac_meeting_01.txt"), ctx)
    assert len(by_content.new_items) == 7
    with pytest.raises(ExtractionError):
        mock.extract("some unknown transcript", ctx, source_name="mine.txt")


def test_sanitize_moves_unknown_sections_to_general():
    ctx = make_ctx()
    ext = MeetingExtraction(sections=[SectionNotes(section_key="weather", bullets=["Rained."]), SectionNotes(section_key="safety", bullets=["Fine.", "  "])])
    out = sanitize_extraction(ext, ctx)
    keys = {s.section_key: s.bullets for s in out.sections}
    assert keys == {"general": ["Rained."], "safety": ["Fine."]}
    assert any("unknown section" in f for f in out.review_flags)


def test_claude_request_shape():
    ctx = make_ctx(prior=[prior_item()])
    kwargs = ClaudeExtractor().request_kwargs("transcript text", ctx)
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_format"] is MeetingExtraction
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["fallbacks"] == "default" and kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in kwargs  # always on for this model; effort controls depth
    assert "transcript text" in kwargs["messages"][0]["content"]
    plain = ClaudeExtractor(use_fallbacks=False).request_kwargs("t", ctx)
    assert "fallbacks" not in plain and "betas" not in plain


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, message=None, error=None):
        self.calls = []
        outer = self

        class Messages:
            def stream(self, **kwargs):
                outer.calls.append(kwargs)
                if error is not None:
                    raise error
                return FakeStream(message)

        self.beta = SimpleNamespace(messages=Messages())


def fake_message(**overrides):
    base = dict(stop_reason="end_turn", stop_details=None, parsed_output=MeetingExtraction(decisions=["ok"]), content=[], usage=None, _request_id="req_1")
    base.update(overrides)
    return SimpleNamespace(**base)


def test_claude_extract_returns_parsed_output():
    client = FakeClient(message=fake_message())
    ext = ClaudeExtractor(client=client)
    out = ext.extract("transcript", make_ctx())
    assert out.decisions == ["ok"]
    assert client.calls[0]["output_format"] is MeetingExtraction
    assert ext.last_request_id == "req_1"


def test_claude_extract_falls_back_to_json_text():
    text_block = SimpleNamespace(type="text", text='{"decisions": ["from text"]}')
    client = FakeClient(message=fake_message(parsed_output=None, content=[text_block]))
    assert ClaudeExtractor(client=client).extract("t", make_ctx()).decisions == ["from text"]


def test_claude_extract_refusal_and_truncation():
    refused = fake_message(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"))
    with pytest.raises(ExtractionError, match="declined"):
        ClaudeExtractor(client=FakeClient(message=refused)).extract("t", make_ctx())
    with pytest.raises(ExtractionError, match="cut off"):
        ClaudeExtractor(client=FakeClient(message=fake_message(stop_reason="max_tokens"))).extract("t", make_ctx())
    with pytest.raises(ExtractionError, match="empty"):
        ClaudeExtractor(client=FakeClient(message=fake_message())).extract("   ", make_ctx())


def test_claude_api_errors_are_translated():
    import anthropic
    import httpx2 as httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    auth_error = anthropic.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
    with pytest.raises(ExtractionError, match="API key"):
        ClaudeExtractor(client=FakeClient(error=auth_error)).extract("t", make_ctx())
    rate = anthropic.RateLimitError("slow down", response=httpx.Response(429, request=request), body=None)
    with pytest.raises(ExtractionError, match="Rate limited"):
        ClaudeExtractor(client=FakeClient(error=rate)).extract("t", make_ctx())
    conn = anthropic.APIConnectionError(request=request)
    with pytest.raises(ExtractionError, match="reach"):
        ClaudeExtractor(client=FakeClient(error=conn)).extract("t", make_ctx())


def test_get_extractor_modes(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("OACMINUTES_EXTRACTOR", raising=False)
    assert isinstance(get_extractor(), MockExtractor)
    assert isinstance(get_extractor("mock"), MockExtractor)
    assert isinstance(get_extractor("claude"), ClaudeExtractor)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert isinstance(get_extractor(), ClaudeExtractor)
    monkeypatch.setenv("OACMINUTES_EXTRACTOR", "demo")
    assert isinstance(get_extractor(), MockExtractor)
    monkeypatch.setenv("OACMINUTES_EXTRACTOR", "claude")
    monkeypatch.setenv("OACMINUTES_MODEL", "claude-sonnet-5-5")
    assert get_extractor().model == "claude-sonnet-5-5"
