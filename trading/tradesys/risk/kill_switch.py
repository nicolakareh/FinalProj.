"""Kill switch: cancel every open order, optionally flatten every position, mark the
system killed (persisted) and alert. Triggered from the CLI (`tradesys kill`), a
Discord `!kill` from the owner, or by creating the KILL file next to the process.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..alerts import Notifier
from ..config import Settings
from ..storage import Database
from .manager import RiskManager

log = logging.getLogger(__name__)


class KillSwitch:
    def __init__(self, settings: Settings, db: Database, broker, risk: RiskManager, notifier: Notifier | None = None):
        self.settings = settings
        self.db = db
        self.broker = broker
        self.risk = risk
        self.notifier = notifier

    def file_triggered(self) -> bool:
        return Path(self.settings.kill_file).exists()

    def trigger(self, reason: str, flatten: bool = False) -> dict:
        """Idempotent: safe to call repeatedly. Marks killed FIRST so nothing new can be approved."""
        self.risk.kill(reason)
        result = {"reason": reason, "orders_cancelled": 0, "positions_closed": 0, "errors": []}
        try:
            result["orders_cancelled"] = self.broker.cancel_all_orders()
        except Exception as e:
            result["errors"].append(f"cancel_all_orders: {e}")
            log.exception("kill: cancel_all_orders failed")
        if flatten:
            try:
                from ..signals.tracker import SourceTracker
                prices = {p.symbol: p.current_price for p in self.broker.get_positions()}
                closed = self.broker.close_all_positions()
                result["positions_closed"] = len(closed)
                tracker = SourceTracker(self.db)
                for t in self.db.open_trades(mode=self.settings.mode):
                    if t["status"] == "open" and t["symbol"] in prices:
                        tracker.close_trade(t["id"], prices[t["symbol"]], exit_reason="kill")
                    else:
                        tracker.cancel_trade(t["id"], "kill")
            except Exception as e:
                result["errors"].append(f"close_all_positions: {e}")
                log.exception("kill: close_all_positions failed")
        msg = (f"KILL SWITCH ENGAGED: {reason}\nCancelled {result['orders_cancelled']} order(s)"
               f"{', flattened ' + str(result['positions_closed']) + ' position(s)' if flatten else ' (positions left open; stops were cancelled too)'}."
               f"\nSystem stays killed until: tradesys resume --kill")
        if result["errors"]:
            msg += "\nErrors: " + "; ".join(result["errors"])
        if self.notifier:
            self.notifier.notify("KILL", msg)
        return result
