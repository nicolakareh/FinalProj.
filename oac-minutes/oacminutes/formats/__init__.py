"""Built-in firm formats. A firm's format is plain JSON and fully editable in the app."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import FirmFormat

FORMATS_DIR = Path(__file__).parent
DEFAULT_FORMAT_KEY = "standard_opm"


def list_builtin_formats() -> dict[str, FirmFormat]:
    formats = {}
    for path in sorted(FORMATS_DIR.glob("*.json")):
        formats[path.stem] = FirmFormat.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return formats


def load_builtin_format(key: str = DEFAULT_FORMAT_KEY) -> FirmFormat:
    path = FORMATS_DIR / f"{key}.json"
    if not path.exists():
        raise KeyError(f"No built-in format named {key!r}")
    return FirmFormat.model_validate(json.loads(path.read_text(encoding="utf-8")))
