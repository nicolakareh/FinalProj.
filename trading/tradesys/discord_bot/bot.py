"""Official Discord bot (discord.py) that reads trade calls from configured channels.

It runs under a bot token from the Discord developer portal and must be invited to
the servers with the *Message Content* intent enabled. It never logs in with a user
account. Owner-only commands: !status !kill !halt !sources !pnl !help
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

import discord

from ..config import Settings
from ..signals.models import Signal
from .parser import ParsedCall, parse_trade_call, to_signal

log = logging.getLogger(__name__)

SignalHandler = Callable[[Signal, ParsedCall], Awaitable[str]]
CommandHandler = Callable[[str, list[str]], Awaitable[str]]

REACTIONS = {"accepted": "✅", "tracked": "📝", "rejected": "❌", "ignored": None}


class SignalBot(discord.Client):
    def __init__(self, settings: Settings, on_signal: SignalHandler, on_command: CommandHandler | None = None):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True
        intents.dm_messages = True
        super().__init__(intents=intents)
        self.settings = settings
        self.on_signal = on_signal
        self.on_command = on_command
        self._owner: discord.User | None = None

    async def on_ready(self) -> None:
        log.info("discord bot logged in as %s; watching channels %s", self.user, self.settings.discord_signal_channel_ids)
        if self.settings.discord_owner_user_id:
            try:
                self._owner = await self.fetch_user(self.settings.discord_owner_user_id)
            except Exception as e:  # pragma: no cover - network
                log.warning("could not fetch owner user: %s", e)

    async def on_message(self, message: discord.Message) -> None:
        author = message.author
        if getattr(author, "bot", False) or (self.user is not None and author.id == self.user.id):
            return
        content = message.content or ""
        if content.startswith("!") and self.on_command is not None:
            if self.settings.discord_owner_user_id and author.id == self.settings.discord_owner_user_id:
                parts = content[1:].split()
                if parts:
                    reply = await self.on_command(parts[0].lower(), parts[1:])
                    await self._safe_reply(message, reply)
            return
        if message.channel.id not in self.settings.discord_signal_channel_ids:
            return
        parsed = parse_trade_call(content)
        if parsed is None:
            return
        guild = getattr(message.guild, "name", "dm")
        display = getattr(author, "display_name", None) or getattr(author, "name", str(author.id))
        signal = to_signal(parsed, source_id=f"discord:{author.id}", source_name=f"{display}@{guild}",
                           timestamp=message.created_at)
        try:
            outcome = await self.on_signal(signal, parsed)
        except Exception:
            log.exception("signal handler failed for %r", content)
            outcome = "rejected"
        emoji = REACTIONS.get(outcome)
        if emoji:
            try:
                await message.add_reaction(emoji)
            except Exception:  # missing permission etc.
                pass

    async def _safe_reply(self, message: discord.Message, text: str) -> None:
        for chunk in [text[i:i + 1900] for i in range(0, max(len(text), 1), 1900)]:
            try:
                await message.reply(f"```\n{chunk}\n```")
            except Exception:
                log.exception("failed to reply on discord")

    # ---------------------------------------------------------- DM alerts
    def dm_sender(self) -> Callable[[str, str], None]:
        """A Notifier channel that DMs the owner; safe to call from any thread."""
        def send(kind: str, text: str) -> None:
            if self._owner is None or self.loop is None or self.loop.is_closed():
                return
            asyncio.run_coroutine_threadsafe(self._owner.send(text[:1900]), self.loop)
        return send


async def run_bot(bot: SignalBot, token: str) -> None:
    await bot.start(token)
