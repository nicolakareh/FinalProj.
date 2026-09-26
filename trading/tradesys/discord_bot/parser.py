"""Turn free-text trade calls ("$TSLA long entry 250 stop 240 target 270") into
structured signals: ticker, direction, entry, stop, target.

Anything that smells like options (calls, puts, strikes, 0DTE) is flagged and never
traded. Shorts are parsed so the caller's track record can be judged, but the
executor refuses them (no shorting).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..common import KNOWN_CRYPTO, normalize_symbol
from ..signals.models import Direction, Signal

NUM = r"\$?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK](?![a-zA-Z]))?"

OPTION_RE = re.compile(
    r"\b(calls?|puts?|strikes?|0dte|\d+dte|expir\w*|leaps?|premium|contracts?|straddle|strangle|spread)\b"
    r"|\b\d+(?:\.\d+)?\s*[cp]\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\s*(?:c|p|calls?|puts?)\b",
    re.IGNORECASE,
)
LONG_RE = re.compile(r"\b(long(?:ing|ed)?|buy(?:ing)?|bought|bto|entry|enter(?:ed|ing)?|add(?:ing|ed)?|accumulat\w*|"
                     r"scal(?:e|ing)\s+in|going\s+long|bull(?:ish)?\s+entry)\b", re.IGNORECASE)
SHORT_RE = re.compile(r"\b(short(?:ing|ed)?|sto|going\s+short)\b", re.IGNORECASE)
CLOSE_RE = re.compile(r"\b(sell(?:ing)?|sold|exit(?:ing|ed)?|clos(?:e|ing|ed)|trim(?:ming|med)?|took\s+profits?|"
                      r"taking\s+profits?|out\s+of|stopped\s+out|cut(?:ting)?|stc|flat)\b", re.IGNORECASE)

ENTRY_RE = re.compile(r"\b(?:entry|entered|enter|in\s+at|buy\s+at|long\s+at|bought\s+at|price|avg|average|filled|fill)"
                      r"\s*[:=]?\s*(?:@|at)?\s*" + NUM, re.IGNORECASE)
AT_RE = re.compile(r"(?:@|\bat)\s*" + NUM, re.IGNORECASE)
STOP_RE = re.compile(r"\b(?:sl|s/l|stop\s*loss|stoploss|stop|stops|risk\s+at|invalidation)\s*[:=]?\s*(?:@|at|below|under)?\s*"
                     + NUM, re.IGNORECASE)
# An index digit (TP1, target2) only counts when it sits right after the label and before a separator,
# so "TP 160" keeps its full price.
TARGET_RE = re.compile(r"\b(?:tp|t/p|pt|targets?|take\s*profits?|tgt|goal)(?:\d(?=[\s:=@\$]))?\s*[:=]?\s*"
                       r"(?:@|at|above)?\s*" + NUM, re.IGNORECASE)
CASHTAG_RE = re.compile(r"\$([A-Za-z]{1,6})(?:[/-]?(USD|USDT|USDC))?\b")
PAIR_RE = re.compile(r"\b([A-Z]{2,6})[/-](USD|USDT|USDC)\b")
BARE_RE = re.compile(r"(?<![\$\w/])([A-Z]{1,5})(?![\w/])")
BARE_NUM_RE = re.compile(r"(?<![A-Za-z\d.,])" + NUM + r"(?![\d/%xX])")

STOPWORDS = {
    "A", "I", "AM", "PM", "AT", "IN", "ON", "TO", "OR", "IF", "IS", "IT", "BE", "BY", "OF", "AN", "AS", "SO", "UP",
    "DO", "GO", "OK", "NO", "MY", "ME", "WE", "US", "UK", "EU", "THE", "AND", "NOT", "NOW", "NEW", "ALL", "FOR",
    "BUY", "SELL", "SOLD", "LONG", "SHORT", "SL", "TP", "PT", "STOP", "LOSS", "TGT", "TARGET", "ENTRY", "ENTER",
    "EXIT", "CLOSE", "OPEN", "HIGH", "LOW", "HOLD", "ADD", "ATH", "ATL", "USD", "USDT", "USDC", "DAY", "SWING",
    "SCALP", "LIMIT", "MKT", "RISK", "R", "RR", "RUN", "YOLO", "ASAP", "IMO", "IMHO", "LOL", "FYI", "PSA", "EOD",
    "HOD", "LOD", "VWAP", "EMA", "SMA", "RSI", "ATR", "MACD", "GTC", "DCA", "FOMO", "HODL", "SOON", "BIG", "WTF",
    "CEO", "CFO", "IPO", "ETF", "FED", "CPI", "FOMC", "GDP", "NFP", "USA", "TRADE", "BREAK", "OVER", "UNDER",
    "ABOVE", "BELOW", "NEAR", "HERE", "CALL", "PUT", "CALLS", "PUTS", "BTO", "STC", "STO", "BTC", "ETH", "K", "M",
    "ALERT", "NOTE", "UPDATE", "SIZE", "FULL", "HALF", "MOVE", "MOVES", "TP1", "TP2", "TP3", "AVG", "FILL", "AREA",
    "ZONE", "DIP", "DIPS", "LEVEL", "KEY", "WATCH", "LIST", "PLAY", "PLAYS", "IDEA", "SETUP", "BULL", "BEAR", "BEARS",
    "BULLS", "TRIM", "OUT", "FLAT", "CUT", "ADDING", "IN", "AGAIN", "STOPS", "GOAL", "NFA", "DYOR", "LFG", "GM",
    "GN", "IM", "ID", "BUT", "ANY", "CAN", "GOT", "HAS", "HAD", "WAS", "ARE", "OFF", "ONE", "TWO", "TOO", "VIA",
    "PER", "MAX", "MIN",
}
CRYPTO_NAMES = {
    "bitcoin": "BTC", "ethereum": "ETH", "ether": "ETH", "solana": "SOL", "dogecoin": "DOGE", "litecoin": "LTC",
    "avalanche": "AVAX", "chainlink": "LINK", "ripple": "XRP", "polkadot": "DOT", "uniswap": "UNI", "aave": "AAVE",
    "shiba": "SHIB", "pepe": "PEPE", "cardano": "ADA",
}


@dataclass
class ParsedCall:
    symbol: str | None
    direction: Direction | None
    entry: float | None
    stop: float | None
    target: float | None
    instrument: str          # stock | crypto | option | unknown
    ok: bool
    reason: str
    raw: str
    confidence: float = 0.0


def _to_number(num: str, k: str | None) -> float:
    val = float(num.replace(",", ""))
    return val * 1000.0 if k else val


def _first_labelled(regex: re.Pattern, text: str) -> tuple[float | None, tuple[int, int] | None]:
    m = regex.search(text)
    if not m:
        return None, None
    return _to_number(m.group(1), m.group(2)), m.span()


def _find_symbol(text: str) -> tuple[str | None, int]:
    m = CASHTAG_RE.search(text)
    if m:
        base = m.group(1).upper()
        return (f"{base}/USD" if (m.group(2) or base in KNOWN_CRYPTO) else base), m.start()
    m = PAIR_RE.search(text)
    if m:
        return f"{m.group(1)}/USD", m.start()
    lowered = text.lower()
    for name, base in CRYPTO_NAMES.items():
        pos = re.search(rf"\b{name}\b", lowered)
        if pos:
            return f"{base}/USD", pos.start()
    m = re.search(r"\b(" + "|".join(sorted(c.lower() for c in KNOWN_CRYPTO)) + r")(?:usd|usdt)?\b", lowered)
    if m:
        return f"{m.group(1).upper()}/USD", m.start()
    candidates = [(mm.group(1), mm.start()) for mm in BARE_RE.finditer(text) if mm.group(1) not in STOPWORDS]
    if not candidates:
        return None, -1
    # prefer the first bare ticker that appears after a direction keyword
    for rx in (LONG_RE, SHORT_RE, CLOSE_RE):
        dm = rx.search(text)
        if dm:
            after = [c for c in candidates if c[1] > dm.start()]
            if after:
                return after[0][0], after[0][1]
    return candidates[0][0], candidates[0][1]


def parse_trade_call(text: str) -> ParsedCall | None:
    """Return a ParsedCall for messages that look like trade calls, else None."""
    if not text or len(text.strip()) < 3:
        return None
    raw = text.strip()
    clean = re.sub(r"<@!?\d+>|<#\d+>|<a?:\w+:\d+>|https?://\S+", " ", raw)
    clean = re.sub(r"\s+", " ", clean)

    is_long, is_short, is_close = bool(LONG_RE.search(clean)), bool(SHORT_RE.search(clean)), bool(CLOSE_RE.search(clean))
    if is_long:
        direction: Direction | None = Direction.LONG
    elif is_short:
        direction = Direction.SHORT
    elif is_close:
        direction = Direction.CLOSE
    else:
        direction = None

    symbol, sym_pos = _find_symbol(clean)
    if direction is None or symbol is None:
        return None
    symbol = normalize_symbol(symbol)
    instrument = "crypto" if "/" in symbol else "stock"

    if OPTION_RE.search(clean):
        return ParsedCall(symbol, direction, None, None, None, "option", False, "options are not traded", raw, 0.9)

    entry, entry_span = _first_labelled(ENTRY_RE, clean)
    stop, stop_span = _first_labelled(STOP_RE, clean)
    target, target_span = _first_labelled(TARGET_RE, clean)
    used = [s for s in (entry_span, stop_span, target_span) if s]
    if entry is None:
        for m in AT_RE.finditer(clean):
            if not any(a <= m.start() < b for a, b in used):
                entry, entry_span = _to_number(m.group(1), m.group(2)), m.span()
                used.append(entry_span)
                break
    if entry is None:
        # first bare number after the ticker that is not part of a labelled price
        for m in BARE_NUM_RE.finditer(clean):
            if m.start() < sym_pos:
                continue
            if any(a <= m.start() < b for a, b in used):
                continue
            entry = _to_number(m.group(1), m.group(2))
            break

    ok, reason = True, ""
    if direction == Direction.LONG and entry and stop and stop >= entry:
        ok, reason = False, "stop is not below entry for a long"
    elif direction == Direction.LONG and entry and target and target <= entry:
        ok, reason = False, "target is not above entry for a long"
    elif direction == Direction.SHORT:
        ok, reason = False, "short calls are tracked but never executed"

    confidence = 0.5 + (0.2 if "$" in clean or "/" in symbol else 0.0) + (0.15 if stop else 0.0) + \
        (0.15 if entry_span or target else 0.0)
    return ParsedCall(symbol, direction, entry, stop, target, instrument, ok, reason, raw, min(confidence, 1.0))


def to_signal(parsed: ParsedCall, source_id: str, source_name: str, timestamp: datetime,
              source_kind: str = "discord") -> Signal:
    assert parsed.symbol and parsed.direction
    return Signal(source_id=source_id, source_kind=source_kind, source_name=source_name, symbol=parsed.symbol,
                  direction=parsed.direction, timestamp=timestamp, entry=parsed.entry, stop=parsed.stop,
                  target=parsed.target, raw_text=parsed.raw,
                  meta={"instrument": parsed.instrument, "confidence": parsed.confidence, "parse_ok": parsed.ok,
                        "parse_reason": parsed.reason})
