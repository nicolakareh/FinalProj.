"""Which signal sources may place real orders.

* A strategy is approved against a specific backtest id. The backtest must exist,
  cover 2+ years, and have been produced by the exact strategy code + params that are
  configured now (hash check), so a later edit silently drops the approval.
* Discord callers and the news trigger cannot be backtested; they start in shadow
  mode (signals tracked with simulated P&L) and are approved explicitly by you after
  you have looked at that track record.
"""
from __future__ import annotations

from ..config import StrategyConfig
from ..storage import Database
from ..strategies import strategy_code_hash


class ApprovalError(ValueError):
    pass


class ApprovalRegistry:
    def __init__(self, db: Database):
        self.db = db

    def approve_strategy(self, cfg: StrategyConfig, backtest_id: str) -> dict:
        bt = self.db.get_backtest(backtest_id)
        if bt is None:
            raise ApprovalError(f"backtest {backtest_id!r} not found; run `tradesys backtest {cfg.name}` first")
        if bt["strategy"] != cfg.name:
            raise ApprovalError(f"backtest {backtest_id} is for {bt['strategy']}, not {cfg.name}")
        if not bt["results"].get("sufficient_history"):
            raise ApprovalError("that backtest covers less than 2 years of data; not eligible for approval")
        current_hash = strategy_code_hash(cfg.name, cfg.params)
        if bt.get("code_hash") != current_hash:
            raise ApprovalError("strategy code or params changed since that backtest ran; re-run the backtest")
        self.db.upsert_source(cfg.source_id, "strategy", cfg.name)
        self.db.set_approval(cfg.source_id, backtest_id, current_hash, f"approved against backtest {backtest_id}")
        return self.db.get_approval(cfg.source_id)  # type: ignore[return-value]

    def approve_source(self, source_id: str, note: str = "", acknowledged: bool = False) -> dict:
        if source_id.startswith("strategy:"):
            raise ApprovalError("strategies are approved with a backtest id: tradesys approve <strategy> --backtest-id ...")
        if not acknowledged:
            raise ApprovalError("pass --i-reviewed-the-track-record to approve a Discord/news source")
        src = self.db.get_source(source_id)
        if src is None:
            raise ApprovalError(f"unknown source {source_id!r}; it appears once it has sent a signal")
        self.db.set_approval(source_id, None, None, note or "approved after reviewing shadow track record")
        return self.db.get_approval(source_id)  # type: ignore[return-value]

    def revoke(self, source_id: str) -> None:
        self.db.delete_approval(source_id)

    def is_approved(self, source_id: str, code_hash: str | None = None) -> tuple[bool, str]:
        row = self.db.get_approval(source_id)
        if row is None:
            return False, "not approved (shadow tracking only)"
        if code_hash is not None and row.get("code_hash") and row["code_hash"] != code_hash:
            return False, "approval invalidated: strategy code/params changed since the approved backtest"
        return True, f"approved {row['approved_at']}" + (f" (backtest {row['backtest_id']})" if row.get("backtest_id") else "")

    def list(self) -> list[dict]:
        return self.db.list_approvals()
