"""Audio/video -> transcript text.

Speech-to-text is pluggable. The bundled provider is local `faster-whisper`
(optional dependency: ``pip install faster-whisper``), which keeps recordings
on the PM's machine. Set ``OACMINUTES_TRANSCRIBER`` to choose a provider.
"""
from __future__ import annotations

import os
from pathlib import Path


class TranscriptionUnavailable(RuntimeError):
    """Raised when no speech-to-text provider is configured or installed."""


def available_provider() -> str | None:
    provider = os.environ.get("OACMINUTES_TRANSCRIBER", "faster_whisper")
    if provider == "faster_whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return None
        return provider
    return None


def transcribe_audio(path: str | Path, *, provider: str | None = None, model_size: str | None = None) -> str:
    """Return a transcript with speaker-less lines, one segment per line."""
    provider = provider or os.environ.get("OACMINUTES_TRANSCRIBER", "faster_whisper")
    if provider == "faster_whisper":
        return _faster_whisper(Path(path), model_size or os.environ.get("OACMINUTES_WHISPER_MODEL", "base"))
    raise TranscriptionUnavailable(f"Unknown transcription provider {provider!r}.")


def _faster_whisper(path: Path, model_size: str) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionUnavailable(
            "Audio upload needs a speech-to-text provider. Install one with "
            "`pip install faster-whisper` (runs locally, no audio leaves the machine), "
            "or upload the transcript exported by Zoom/Teams/Otter instead."
        ) from exc
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(path), vad_filter=True)
    lines = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            lines.append(text)
    return "\n".join(lines)
