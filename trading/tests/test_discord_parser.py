import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from tradesys.discord_bot.bot import SignalBot
from tradesys.discord_bot.parser import parse_trade_call, to_signal
from tradesys.signals.models import Direction


@pytest.mark.parametrize("text,symbol,direction,entry,stop,target", [
    ("BUY AAPL @ 150, SL 145, TP 160", "AAPL", Direction.LONG, 150, 145, 160),
    ("$TSLA long entry 250 stop 240 target 270", "TSLA", Direction.LONG, 250, 240, 270),
    ("Long BTC 65k stop 63k target 70k", "BTC/USD", Direction.LONG, 65000, 63000, 70000),
    ("longing ETH/USD here at 3,250.50 sl: 3,100 tp1: 3,500 tp2: 3,800", "ETH/USD", Direction.LONG, 3250.5, 3100, 3500),
    ("Bought NVDA 900.25 stop loss 880", "NVDA", Direction.LONG, 900.25, 880, None),
    ("buy MSFT now, stop at 400", "MSFT", Direction.LONG, None, 400, None),
    ("Short NVDA 900 stop 920 target 850", "NVDA", Direction.SHORT, 900, 920, 850),
    ("Sold my AAPL here, nice win", "AAPL", Direction.CLOSE, None, None, None),
    ("Exit $COIN", "COIN", Direction.CLOSE, None, None, None),
    ("Adding to bitcoin at $64,100 invalidation 62,000 goal 70,000", "BTC/USD", Direction.LONG, 64100, 62000, 70000),
    ("Entry: AMD 155 | Stop: 149 | Target: 170 | swing", "AMD", Direction.LONG, 155, 149, 170),
    ("Long $SPY entry 500 stop 495 PT 512", "SPY", Direction.LONG, 500, 495, 512),
])
def test_parse_formats(text, symbol, direction, entry, stop, target):
    p = parse_trade_call(text)
    assert p is not None, text
    assert p.symbol == symbol
    assert p.direction == direction
    assert p.entry == entry
    assert p.stop == stop
    assert p.target == target


def test_non_calls_return_none():
    for text in ["good morning everyone", "the market looks weak today", "buy the dip", "AAPL earnings tomorrow",
                 "", "!!"]:
        assert parse_trade_call(text) is None, text


def test_options_flagged_and_never_ok():
    for text in ["AAPL 150C 1/17 buy now", "buying TSLA calls", "long SPY 500p 0dte", "bto NVDA 900 call"]:
        p = parse_trade_call(text)
        assert p is not None and p.instrument == "option" and not p.ok, text


def test_short_and_inconsistent_levels_not_ok():
    p = parse_trade_call("Short NVDA 900 stop 920")
    assert p.direction == Direction.SHORT and not p.ok
    p = parse_trade_call("Long AAPL entry 150 stop 155")
    assert p.direction == Direction.LONG and not p.ok and "stop" in p.reason
    p = parse_trade_call("Long AAPL entry 150 stop 145 target 140")
    assert not p.ok and "target" in p.reason


def test_to_signal():
    p = parse_trade_call("$TSLA long entry 250 stop 240 target 270")
    ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    s = to_signal(p, "discord:1", "bob@server", ts)
    assert s.symbol == "TSLA" and s.direction == Direction.LONG and s.entry == 250 and s.stop == 240
    assert s.meta["parse_ok"] and s.source_id == "discord:1"


def _message(content, author_id=7, channel_id=123, bot=False):
    author = SimpleNamespace(id=author_id, bot=bot, display_name="bob", name="bob")
    reactions = []

    async def add_reaction(emoji):
        reactions.append(emoji)

    replies = []

    async def reply(text):
        replies.append(text)

    msg = SimpleNamespace(author=author, content=content, channel=SimpleNamespace(id=channel_id),
                          guild=SimpleNamespace(name="srv"), created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                          add_reaction=add_reaction, reply=reply, reactions=reactions, replies=replies)
    return msg


def test_bot_routes_signals_and_commands(settings):
    received = []
    commands = []

    async def on_signal(signal, parsed):
        received.append(signal)
        return "tracked"

    async def on_command(cmd, args):
        commands.append((cmd, args))
        return f"ran {cmd}"

    bot = SignalBot(settings, on_signal, on_command)

    async def scenario():
        msg = _message("Long $AAPL entry 150 stop 145 target 160")
        await bot.on_message(msg)
        assert received and received[0].source_id == "discord:7" and msg.reactions == ["📝"]
        # wrong channel: ignored
        await bot.on_message(_message("Long $AAPL entry 150 stop 145", channel_id=999))
        assert len(received) == 1
        # bots ignored
        await bot.on_message(_message("Long $AAPL entry 150 stop 145", bot=True))
        assert len(received) == 1
        # owner command
        owner_msg = _message("!status", author_id=42)
        await bot.on_message(owner_msg)
        assert commands == [("status", [])] and owner_msg.replies
        # non-owner cannot run commands
        await bot.on_message(_message("!kill", author_id=8))
        assert len(commands) == 1

    asyncio.run(scenario())
