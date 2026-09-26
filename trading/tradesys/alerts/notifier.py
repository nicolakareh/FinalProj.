"""Fan-out alerts to email (SMTP), SMS (Twilio REST) and an optional Discord DM.

Every fill, stop hit and halt goes through `Notifier.notify`. Network sends run in
background threads so a slow SMTP server can never block an order or a halt.
"""
from __future__ import annotations

import logging
import smtplib
import threading
from collections import deque
from email.message import EmailMessage
from typing import Callable

import requests

from ..config import Settings
from ..storage import Database

log = logging.getLogger(__name__)

# Alert kinds that must always page the user, whatever the rate limiter says.
CRITICAL_KINDS = {"FILL", "STOP_HIT", "TARGET_HIT", "HALT_DAILY", "HALT_WEEKLY", "KILL", "ERROR", "SOURCE_DISABLED"}


class Notifier:
    def __init__(self, settings: Settings, db: Database | None = None, *, sync: bool = False):
        self.settings = settings
        self.db = db
        self.sync = sync  # tests: send inline instead of in a thread
        self._extra: list[tuple[str, Callable[[str, str], None]]] = []
        self._recent: deque[float] = deque(maxlen=200)
        self.sent: list[tuple[str, str]] = []  # in-memory record for tests / status

    # ------------------------------------------------------------ channels
    def add_channel(self, name: str, fn: Callable[[str, str], None]) -> None:
        """Register an extra sink, e.g. a Discord DM sender. fn(kind, message)."""
        self._extra.append((name, fn))

    @property
    def email_enabled(self) -> bool:
        s = self.settings
        return bool(s.alert_email_to and s.smtp_host and s.smtp_user and s.smtp_password)

    @property
    def sms_enabled(self) -> bool:
        s = self.settings
        return bool(s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number and s.alert_sms_to)

    def channels(self) -> list[str]:
        out = []
        if self.email_enabled:
            out.append("email")
        if self.sms_enabled:
            out.append("sms")
        out.extend(name for name, _ in self._extra)
        return out

    # ---------------------------------------------------------------- send
    def notify(self, kind: str, message: str) -> None:
        subject = f"[tradesys {self.settings.mode.upper()}] {kind}"
        body = message.strip()
        log.warning("ALERT %s: %s", kind, body.replace("\n", " | "))
        self.sent.append((kind, body))
        chans = self.channels()
        if self.db is not None:
            try:
                self.db.log_alert(kind, body, chans)
            except Exception:  # pragma: no cover - logging must never break trading
                log.exception("failed to persist alert")
        if not chans:
            return
        if self.sync:
            self._dispatch(kind, subject, body)
        else:
            threading.Thread(target=self._dispatch, args=(kind, subject, body), daemon=True).start()

    def _dispatch(self, kind: str, subject: str, body: str) -> None:
        if self.email_enabled:
            try:
                self._send_email(subject, body)
            except Exception:
                log.exception("email alert failed")
        if self.sms_enabled:
            try:
                self._send_sms(f"{subject}\n{body}"[:1500])
            except Exception:
                log.exception("sms alert failed")
        for name, fn in self._extra:
            try:
                fn(kind, f"{subject}\n{body}")
            except Exception:
                log.exception("%s alert failed", name)

    def _send_email(self, subject: str, body: str) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = s.smtp_user
        msg["To"] = s.alert_email_to
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            if s.smtp_port != 465:
                smtp.starttls()
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)

    def _send_sms(self, body: str) -> None:
        s = self.settings
        url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
        resp = requests.post(
            url,
            data={"From": s.twilio_from_number, "To": s.alert_sms_to, "Body": body},
            auth=(s.twilio_account_sid, s.twilio_auth_token),
            timeout=20,
        )
        resp.raise_for_status()
