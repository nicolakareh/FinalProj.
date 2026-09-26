"""The single choke point for every order.

`RiskManager.evaluate` runs the hard rules and, only if all pass, returns a signed
`RiskApproval`. The broker wrapper refuses to submit anything without a valid
approval, so no code path (strategy, Discord signal, CLI) can reach the broker
around these checks. Halt and kill state is persisted in SQLite, so restarting the
process does not lift a weekly halt or a kill.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Iterable

from ..alerts import Notifier
from ..common import canonical_json, from_iso, to_iso, trading_date, utcnow, week_start
from ..config import HARD_MAX_RISK_PER_TRADE_PCT, Settings
from ..execution.models import AccountSnapshot, AssetInfo, ClockInfo, OrderIntent, OrderSnapshot, PositionSnapshot
from ..storage import Database

log = logging.getLogger(__name__)

_PROCESS_SECRET = secrets.token_bytes(32)
APPROVAL_TTL = timedelta(seconds=120)
GO_LIVE_PHRASE = "GO LIVE"
PDT_EQUITY_THRESHOLD = 25_000.0


class RiskViolation(Exception):
    pass


@dataclass(frozen=True)
class RiskApproval:
    intent: OrderIntent
    checks: tuple[str, ...]
    signature: str
    created_at: str
    mode: str


def _sign(intent: OrderIntent, created_at: str, mode: str) -> str:
    payload = canonical_json({"intent": intent.as_dict(), "created_at": created_at, "mode": mode})
    return hmac.new(_PROCESS_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_approval(approval: RiskApproval, now: datetime | None = None) -> None:
    """Raise RiskViolation unless `approval` was issued by this process's RiskManager and is fresh."""
    if not isinstance(approval, RiskApproval):
        raise RiskViolation("order submitted without a RiskApproval")
    expected = _sign(approval.intent, approval.created_at, approval.mode)
    if not hmac.compare_digest(expected, approval.signature):
        raise RiskViolation("RiskApproval signature mismatch (intent altered after approval?)")
    created = from_iso(approval.created_at)
    if created is None or (now or utcnow()) - created > APPROVAL_TTL:
        raise RiskViolation("RiskApproval expired; re-evaluate the order")


@dataclass
class RiskDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    approval: RiskApproval | None = None

    def __str__(self) -> str:
        return "ALLOWED" if self.allowed else "REJECTED: " + "; ".join(self.reasons)


@dataclass
class PnLSnapshot:
    daily: float
    weekly: float
    realized_today: float
    realized_week: float
    unrealized_intraday: float
    unrealized_total: float
    fees_today: float
    fees_week: float
    account_daily: float


class RiskManager:
    K_KILLED = "killed"
    K_KILL_REASON = "kill_reason"
    K_DAILY_HALT = "daily_halt_date"
    K_DAILY_REASON = "daily_halt_reason"
    K_WEEKLY_HALT = "weekly_halt"
    K_WEEKLY_REASON = "weekly_halt_reason"
    K_ARMED = "live_armed_at"

    def __init__(self, settings: Settings, db: Database, notifier: Notifier | None = None,
                 clock: Callable[[], datetime] = utcnow):
        if settings.max_risk_per_trade_pct > HARD_MAX_RISK_PER_TRADE_PCT:
            raise RiskViolation("risk per trade above the hard ceiling")
        self.settings = settings
        self.db = db
        self.notifier = notifier
        self.clock = clock

    # ------------------------------------------------------------ state
    def is_killed(self) -> bool:
        return self.db.get_state(self.K_KILLED) == "1"

    def is_daily_halted(self, now: datetime | None = None) -> bool:
        d = self.db.get_state(self.K_DAILY_HALT)
        if not d:
            return False
        if d < trading_date(now or self.clock()).isoformat():
            self.db.set_state(self.K_DAILY_HALT, None)   # a new trading day lifts it automatically
            self.db.set_state(self.K_DAILY_REASON, None)
            log.info("daily halt from %s expired", d)
            return False
        return True

    def is_weekly_halted(self) -> bool:
        return self.db.get_state(self.K_WEEKLY_HALT) == "1"

    def is_halted(self, now: datetime | None = None) -> bool:
        return self.is_killed() or self.is_daily_halted(now) or self.is_weekly_halted()

    def is_armed(self) -> bool:
        return bool(self.db.get_state(self.K_ARMED))

    def live_orders_allowed(self) -> bool:
        """Paper mode always may trade; live mode only once armed with GO LIVE."""
        return (not self.settings.live_mode) or self.is_armed()

    def status(self) -> dict:
        return {
            "mode": self.settings.mode, "armed": self.is_armed(), "killed": self.is_killed(),
            "kill_reason": self.db.get_state(self.K_KILL_REASON),
            "daily_halted": self.is_daily_halted(), "daily_halt_reason": self.db.get_state(self.K_DAILY_REASON),
            "weekly_halted": self.is_weekly_halted(), "weekly_halt_reason": self.db.get_state(self.K_WEEKLY_REASON),
            "capital_cap": self.settings.total_capital_cap, "risk_per_trade_pct": self.settings.max_risk_per_trade_pct,
            "daily_loss_limit": self.settings.daily_loss_limit, "weekly_loss_limit": self.settings.weekly_loss_limit,
        }

    # ------------------------------------------------------------ transitions
    def kill(self, reason: str) -> None:
        self.db.set_state(self.K_KILLED, "1")
        self.db.set_state(self.K_KILL_REASON, f"{to_iso(self.clock())}: {reason}")
        log.critical("KILL SWITCH: %s", reason)

    def clear_kill(self) -> None:
        self.db.set_state(self.K_KILLED, None)
        self.db.set_state(self.K_KILL_REASON, None)

    def halt_daily(self, reason: str, now: datetime | None = None) -> None:
        now = now or self.clock()
        self.db.set_state(self.K_DAILY_HALT, trading_date(now).isoformat())
        self.db.set_state(self.K_DAILY_REASON, reason)
        log.critical("DAILY HALT: %s", reason)
        if self.notifier:
            self.notifier.notify("HALT_DAILY", f"{reason}\nNo new entries until the next trading day.")

    def halt_weekly(self, reason: str) -> None:
        self.db.set_state(self.K_WEEKLY_HALT, "1")
        self.db.set_state(self.K_WEEKLY_REASON, f"{to_iso(self.clock())}: {reason}")
        log.critical("WEEKLY HALT: %s", reason)
        if self.notifier:
            self.notifier.notify("HALT_WEEKLY", f"{reason}\nHalted until you run: tradesys resume --weekly")

    def resume_weekly(self) -> None:
        self.db.set_state(self.K_WEEKLY_HALT, None)
        self.db.set_state(self.K_WEEKLY_REASON, None)
        log.warning("weekly halt cleared manually")

    def arm_live(self, confirmation: str) -> None:
        if confirmation.strip() != GO_LIVE_PHRASE:
            raise RiskViolation(f"live trading is armed only by typing exactly {GO_LIVE_PHRASE!r}")
        if not self.settings.live_mode:
            raise RiskViolation("LIVE_MODE is false; arming is only meaningful in live mode")
        self.db.set_state(self.K_ARMED, to_iso(self.clock()))
        log.critical("LIVE ORDERS ARMED")

    def disarm(self) -> None:
        self.db.set_state(self.K_ARMED, None)
        log.warning("live orders disarmed")

    # ------------------------------------------------------------ evaluation
    def evaluate(self, intent: OrderIntent, account: AccountSnapshot, positions: Iterable[PositionSnapshot],
                 open_orders: Iterable[OrderSnapshot], asset: AssetInfo | None = None,
                 clock_info: ClockInfo | None = None, now: datetime | None = None) -> RiskDecision:
        now = now or self.clock()
        positions = list(positions)
        open_orders = list(open_orders)
        s = self.settings
        reasons: list[str] = []
        checks: list[str] = []

        def check(name: str, ok: bool, why: str) -> None:
            if ok:
                checks.append(name)
            else:
                reasons.append(f"{name}: {why}")

        is_buy = intent.side == "buy"
        check("side", intent.side in ("buy", "sell"), f"unknown side {intent.side!r}")
        check("qty", intent.qty > 0, "quantity must be positive")
        check("live_gate", self.live_orders_allowed(), "LIVE_MODE is on but live orders are not armed (run: tradesys arm)")
        check("account_ok", not (account.trading_blocked or account.account_blocked), "broker account is blocked")
        check("asset_class", intent.asset_class in ("us_equity", "crypto") and not intent.looks_like_option,
              "only plain US equities and crypto are allowed (no options)")
        if asset is not None:
            check("asset_tradable", asset.tradable and asset.status == "active" and asset.asset_class in ("us_equity", "crypto"),
                  f"asset {asset.symbol} is not a tradable equity/crypto ({asset.asset_class}, tradable={asset.tradable})")
            if not asset.fractionable and abs(intent.qty - round(intent.qty)) > 1e-9:
                check("whole_shares", False, "asset is not fractionable; qty must be a whole number")

        held = {p.symbol: p for p in positions}
        if is_buy:
            check("not_killed", not self.is_killed(), "kill switch is engaged")
            check("not_daily_halted", not self.is_daily_halted(now), "daily loss limit hit; halted until next trading day")
            check("not_weekly_halted", not self.is_weekly_halted(), "weekly loss limit hit; halted until manual resume")
            check("single_position", intent.symbol not in held, f"already holding {intent.symbol}; no pyramiding")
            entry = intent.entry_price
            stop = intent.stop_price
            check("stop_required", stop is not None and stop > 0 and stop < entry,
                  f"every buy needs a stop below entry (entry {entry}, stop {stop})")
            if stop is not None and stop > 0 and stop < entry:
                risk_dollars = intent.qty * (entry - stop)
                max_risk = s.total_capital_cap * s.max_risk_per_trade_pct / 100.0
                check("risk_per_trade", risk_dollars <= max_risk + 1e-6,
                      f"risk ${risk_dollars:,.2f} exceeds {s.max_risk_per_trade_pct}% of capital (${max_risk:,.2f})")
            deployed = sum(float(p.cost_basis) for p in positions if p.qty > 0)
            pending_buys = sum(o.remaining_qty * float(o.limit_price or o.stop_price or intent.reference_price)
                               for o in open_orders if o.side == "buy" and o.is_open and o.symbol != intent.symbol)
            pending_buys += sum(o.remaining_qty * float(o.limit_price or intent.reference_price)
                                for o in open_orders if o.side == "buy" and o.is_open and o.symbol == intent.symbol)
            check("capital_cap", deployed + pending_buys + intent.notional <= s.total_capital_cap + 1e-6,
                  f"deployed ${deployed + pending_buys:,.2f} + order ${intent.notional:,.2f} exceeds cap ${s.total_capital_cap:,.2f}")
            check("no_margin", intent.notional <= account.spendable_cash + 1e-6,
                  f"order ${intent.notional:,.2f} exceeds settled cash ${account.spendable_cash:,.2f} (no margin)")
            open_buy_symbols = {o.symbol for o in open_orders if o.side == "buy" and o.is_open}
            check("max_positions", len(held) + len(open_buy_symbols - set(held)) < s.max_open_positions,
                  f"already at MAX_OPEN_POSITIONS={s.max_open_positions}")
            day_start = to_iso(datetime.combine(trading_date(now), datetime.min.time()).replace(tzinfo=now.tzinfo)) or ""
            orders_today = self.db.count_orders_since(day_start)
            check("max_orders_per_day", orders_today < s.max_orders_per_day,
                  f"{orders_today} buy orders already today (MAX_ORDERS_PER_DAY={s.max_orders_per_day})")
            if not intent.is_crypto:
                check("pdt_guard", account.equity >= PDT_EQUITY_THRESHOLD or account.daytrade_count < 3,
                      "equity under $25k with 3 day trades used; a same-day stop exit could be rejected as a PDT violation")
                if clock_info is not None:
                    check("market_open", clock_info.is_open, "stock market is closed; entries wait for the next session")
        else:
            pos = held.get(intent.symbol)
            check("no_short", pos is not None and pos.qty > 0 and intent.qty <= pos.sellable_qty + 1e-9,
                  f"sell {intent.qty} would exceed held quantity ({pos.sellable_qty if pos else 0}); shorting is not allowed")

        allowed = not reasons
        approval = None
        if allowed:
            created = to_iso(now) or ""
            approval = RiskApproval(intent=intent, checks=tuple(checks), signature=_sign(intent, created, s.mode),
                                    created_at=created, mode=s.mode)
        decision = RiskDecision(allowed, reasons, checks, approval)
        (log.info if allowed else log.warning)("risk %s %s %s x%s: %s", intent.side.upper(), intent.symbol,
                                                intent.source_id, intent.qty, decision)
        return decision

    # ------------------------------------------------------------ loss limits
    def _day_start_iso(self, now: datetime) -> str:
        from ..common import NY
        d = trading_date(now)
        return to_iso(datetime(d.year, d.month, d.day, tzinfo=NY)) or ""

    def _week_start_iso(self, now: datetime) -> str:
        from ..common import NY
        d = week_start(trading_date(now))
        return to_iso(datetime(d.year, d.month, d.day, tzinfo=NY)) or ""

    def pnl_snapshot(self, account: AccountSnapshot, positions: Iterable[PositionSnapshot],
                     now: datetime | None = None) -> PnLSnapshot:
        now = now or self.clock()
        positions = list(positions)
        modes = (self.settings.mode,)
        realized_today, fees_today = self.db.realized_pnl_since(self._day_start_iso(now), modes)
        realized_week, fees_week = self.db.realized_pnl_since(self._week_start_iso(now), modes)
        unreal_intraday = sum(float(p.unrealized_intraday_pl) for p in positions)
        unreal_total = sum(float(p.unrealized_pl) for p in positions)
        return PnLSnapshot(
            daily=realized_today + unreal_intraday, weekly=realized_week + unreal_total,
            realized_today=realized_today, realized_week=realized_week, unrealized_intraday=unreal_intraday,
            unrealized_total=unreal_total, fees_today=fees_today, fees_week=fees_week,
            account_daily=float(account.equity) - float(account.last_equity),
        )

    def check_loss_limits(self, account: AccountSnapshot, positions: Iterable[PositionSnapshot],
                          now: datetime | None = None) -> list[str]:
        """Trigger halts when the day's or week's loss reaches the configured limits. Returns halts fired."""
        now = now or self.clock()
        snap = self.pnl_snapshot(account, positions, now)
        fired: list[str] = []
        s = self.settings
        if snap.daily <= -s.daily_loss_limit and not self.is_daily_halted(now):
            self.halt_daily(f"Daily P&L {snap.daily:+,.2f} reached the daily loss limit of ${s.daily_loss_limit:,.2f} "
                            f"(realized {snap.realized_today:+,.2f}, unrealized {snap.unrealized_intraday:+,.2f})", now)
            fired.append("daily")
        if snap.weekly <= -s.weekly_loss_limit and not self.is_weekly_halted():
            self.halt_weekly(f"Weekly P&L {snap.weekly:+,.2f} reached the weekly loss limit of ${s.weekly_loss_limit:,.2f} "
                             f"(realized {snap.realized_week:+,.2f}, unrealized {snap.unrealized_total:+,.2f})")
            fired.append("weekly")
        return fired
