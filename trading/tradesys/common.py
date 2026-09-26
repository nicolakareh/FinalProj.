"""Small helpers shared across modules."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def is_crypto(symbol: str) -> bool:
    """Alpaca crypto symbols look like BTC/USD; equities are bare tickers."""
    return "/" in symbol


def asset_class_for(symbol: str) -> str:
    return "crypto" if is_crypto(symbol) else "us_equity"


def normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper().replace("-", "/")
    if s.endswith("USD") and "/" not in s and len(s) > 3 and s[:-3].isalpha() and s[:-3] in KNOWN_CRYPTO:
        s = f"{s[:-3]}/USD"
    return s


KNOWN_CRYPTO = {
    "BTC", "ETH", "SOL", "DOGE", "LTC", "AVAX", "LINK", "BCH", "UNI", "AAVE", "DOT",
    "SHIB", "XRP", "MATIC", "USDT", "USDC", "SUSHI", "YFI", "MKR", "CRV", "GRT", "BAT",
    "PEPE", "XTZ", "TRUMP",
}


def trading_date(now: datetime | None = None) -> date:
    """Calendar date in New York; used for the daily loss window."""
    now = now or utcnow()
    return now.astimezone(NY).date()


def week_start(d: date) -> date:
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def from_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def setup_logging(level: str = "INFO", log_dir: str | Path | None = None) -> None:
    fmt = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir:
        ensure_dir(log_dir)
        handlers.append(logging.FileHandler(Path(log_dir) / "tradesys.log"))
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=fmt, handlers=handlers)
    for noisy in ("urllib3", "websockets", "discord", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}
