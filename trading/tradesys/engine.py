"""The live/paper trading engine: wires every module together and runs the loops.

Loops (all asyncio, blocking broker/data calls pushed to threads):
  strategy_loop  - on each completed bar, evaluate approved strategies -> executor
  news_loop      - poll headlines, alert on unusual volume, emit news:momentum signals
  risk_loop      - kill file / kill state, daily & weekly loss limits, equity snapshots,
                   end-of-day report
  maintenance    - reconcile trades with the broker, software stops, shadow trades
  discord bot    - trade calls from configured channels + owner commands
"""
from __future__ import annotations

import asyncio
import logging
import signal as os_signal
from datetime import datetime, timedelta

from .alerts import Notifier
from .backtest.engine import FeeModel
from .common import NY, is_crypto, to_iso, trading_date, utcnow
from .config import Settings, StrategyConfig
from .data.market_data import MarketData, timeframe_seconds
from .execution.approvals import ApprovalRegistry
from .execution.broker import AlpacaBroker, TradeUpdateStream
from .execution.executor import Executor
from .news.monitor import NEWS_SOURCE_ID, NewsMonitor
from .reporting.daily_report import build_report, market_benchmark_fn, save_report
from .risk.kill_switch import KillSwitch
from .risk.manager import RiskManager
from .signals.tracker import SourceTracker
from .storage import Database
from .strategies import create_strategy, strategy_code_hash
from .strategies.base import PositionState

log = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self, settings: Settings, db: Database | None = None, broker=None, market_data: MarketData | None = None,
                 notifier: Notifier | None = None):
        self.settings = settings
        self.db = db or Database(settings.db_path)
        self.notifier = notifier or Notifier(settings, self.db)
        self.market_data = market_data or MarketData(settings)
        self.broker = broker or AlpacaBroker(settings)
        self.tracker = SourceTracker(self.db, self.notifier)
        self.risk = RiskManager(settings, self.db, self.notifier)
        self.approvals = ApprovalRegistry(self.db)
        self.executor = Executor(settings, self.db, self.broker, self.risk, self.approvals, self.tracker, self.notifier,
                                 price_lookup=self.market_data.get_latest_price, fees=FeeModel())
        self.kill_switch = KillSwitch(settings, self.db, self.broker, self.risk, self.notifier)
        self.news = NewsMonitor(settings, self.db, self.notifier)
        self.strategies: list[tuple[StrategyConfig, object, str]] = []
        for cfg in settings.strategies:
            self.strategies.append((cfg, create_strategy(cfg.name, cfg.params), strategy_code_hash(cfg.name, cfg.params)))
            self.tracker.register(cfg.source_id, "strategy", cfg.name)
        self.tracker.register(NEWS_SOURCE_ID, "news", "News momentum")
        self._last_bar: dict[tuple[str, str], datetime] = {}
        self._stop = asyncio.Event()
        self._stream: TradeUpdateStream | None = None
        self._bot = None
        self._last_report_date = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------ lifecycle
    def startup_checks(self) -> None:
        s = self.settings
        log.info("mode=%s cap=$%s risk/trade=%s%% daily=$%s weekly=$%s", s.mode, s.total_capital_cap,
                 s.max_risk_per_trade_pct, s.daily_loss_limit, s.weekly_loss_limit)
        if s.limits_defaulted:
            log.warning("dollar limits not set in .env; using paper placeholders")
        if self.risk.is_killed():
            raise SystemExit("kill switch is engaged; run `tradesys resume --kill` before starting")
        if s.live_mode and not self.risk.is_armed():
            log.warning("LIVE_MODE=true but live orders are NOT armed: signals will be tracked, no real orders. "
                        "Run `tradesys arm` and type GO LIVE to enable.")
        acct = self.broker.get_account()
        log.info("account equity=$%.2f cash=$%.2f multiplier=%s daytrades=%s", acct.equity, acct.cash, acct.multiplier,
                 acct.daytrade_count)
        if acct.multiplier and acct.multiplier > 1:
            log.warning("broker account is a margin account (multiplier %s); tradesys still never spends beyond settled "
                        "cash, but consider asking Alpaca for a cash account", acct.multiplier)
        if acct.equity < s.total_capital_cap:
            log.warning("account equity $%.2f is below TOTAL_CAPITAL_CAP $%.2f; cash is the binding limit",
                        acct.equity, s.total_capital_cap)
        self.executor.reconcile()
        for cfg, _, h in self.strategies:
            ok, why = self.approvals.is_approved(cfg.source_id, h)
            log.info("strategy %s on %s [%s]: %s", cfg.name, ",".join(cfg.symbols), cfg.timeframe,
                     "APPROVED - real orders" if ok else f"shadow only ({why})")

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.startup_checks()
        self._stream = TradeUpdateStream(self.settings, self._on_trade_update_threadsafe)
        self._stream.start()
        tasks = [
            asyncio.create_task(self._strategy_loop(), name="strategies"),
            asyncio.create_task(self._news_loop(), name="news"),
            asyncio.create_task(self._risk_loop(), name="risk"),
            asyncio.create_task(self._maintenance_loop(), name="maintenance"),
        ]
        if self.settings.discord_bot_token:
            tasks.append(asyncio.create_task(self._discord_task(), name="discord"))
        else:
            log.info("no DISCORD_BOT_TOKEN; Discord signals disabled")
        for sig in (os_signal.SIGINT, os_signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, self.request_stop)
            except (NotImplementedError, RuntimeError):
                pass
        log.info("engine running (%s). Kill switch: `tradesys kill` or create %s", self.settings.mode, self.settings.kill_file)
        await self._stop.wait()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self._stream:
            self._stream.stop()
        if self._bot:
            try:
                await self._bot.close()
            except Exception:
                pass
        log.info("engine stopped")

    def request_stop(self) -> None:
        self._stop.set()

    def _on_trade_update_threadsafe(self, event: str, order, extra: dict) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self.executor.on_trade_update, event, order, extra)
        else:
            self.executor.on_trade_update(event, order, extra)

    # ------------------------------------------------------------ strategies
    def _position_state(self, source_id: str, symbol: str) -> PositionState | None:
        t = self.executor.open_trade_for(source_id, symbol, self.settings.mode)
        if t is None or t["status"] != "open":
            return None
        return PositionState(float(t["qty"]), float(t["entry_price"] or 0), t["stop_price"], t["target_price"])

    def evaluate_strategies(self, now: datetime | None = None) -> int:
        """One pass over every (strategy, symbol); returns the number of intents produced."""
        now = now or utcnow()
        produced = 0
        market_open: bool | None = None
        for cfg, strat, code_hash in self.strategies:
            secs = timeframe_seconds(cfg.timeframe)
            for symbol in cfg.symbols:
                if not is_crypto(symbol):
                    if market_open is None:
                        try:
                            market_open = self.broker.get_clock().is_open
                        except Exception as e:
                            log.warning("clock lookup failed: %s", e)
                            market_open = False
                    if not market_open:
                        continue  # evaluate the completed bar at the next open instead of burning it now
                try:
                    df = self.market_data.get_recent_bars(symbol, cfg.timeframe, strat.warmup + 60)
                except Exception as e:
                    log.warning("bars for %s failed: %s", symbol, e)
                    continue
                if df.empty:
                    continue
                # drop a bar that is still forming
                last_ts = df.index[-1].to_pydatetime()
                if last_ts + timedelta(seconds=secs) > now:
                    df = df.iloc[:-1]
                    if df.empty:
                        continue
                    last_ts = df.index[-1].to_pydatetime()
                key = (cfg.name, symbol)
                if self._last_bar.get(key) == last_ts:
                    continue
                self._last_bar[key] = last_ts
                if len(df) <= strat.warmup:
                    continue
                prepared = strat.prepare(df)
                intent = strat.on_bar(prepared, len(prepared) - 1, self._position_state(cfg.source_id, symbol))
                if intent is None:
                    continue
                price = float(prepared["close"].iloc[-1])
                try:
                    price = self.market_data.get_latest_price(symbol)
                except Exception:
                    pass
                outcome = self.executor.handle_strategy_intent(cfg, symbol, intent, price, code_hash, now)
                log.info("strategy %s %s %s -> %s", cfg.name, symbol, intent.action, outcome)
                produced += 1
        return produced

    async def _strategy_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self.evaluate_strategies)
            except Exception:
                log.exception("strategy loop error")
            await asyncio.sleep(60)

    # ------------------------------------------------------------ news
    def poll_news(self) -> int:
        alerts = self.news.poll()
        signals = self.news.signals(alerts, self.market_data.get_latest_price)
        for sig in signals:
            outcome = self.executor.handle_signal(sig)
            log.info("news signal %s -> %s", sig.symbol, outcome)
        return len(alerts)

    async def _news_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self.poll_news)
            except Exception:
                log.exception("news loop error")
            await asyncio.sleep(max(60, self.settings.news_poll_seconds))

    # ------------------------------------------------------------ risk
    def risk_tick(self, now: datetime | None = None) -> None:
        now = now or utcnow()
        if self.kill_switch.file_triggered():
            log.critical("KILL file found")
            self.kill_switch.trigger("KILL file present", flatten=False)
        if self.risk.is_killed():
            log.critical("kill state set; stopping engine")
            self.request_stop()
            return
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        fired = self.risk.check_loss_limits(account, positions, now)
        if fired:
            self._cancel_pending_entries()
        self.db.snapshot_equity(account.equity, account.cash, self.settings.mode)
        # one end-of-day report per calendar day, once it is 16:05 or later in New York
        ny = now.astimezone(NY)
        today = trading_date(now)
        if (ny.hour, ny.minute) >= (16, 5) and self._last_report_date != today:
            self._last_report_date = today
            try:
                self.write_daily_report(now)
            except Exception:
                log.exception("daily report failed")

    def _cancel_pending_entries(self) -> None:
        for t in self.db.open_trades(mode=self.settings.mode):
            if t["status"] == "pending" and t.get("entry_order_id"):
                try:
                    self.broker.cancel_order(t["entry_order_id"])
                except Exception as e:
                    log.warning("cancel pending entry %s failed: %s", t["entry_order_id"], e)

    async def _risk_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self.risk_tick)
            except Exception:
                log.exception("risk loop error")
            await asyncio.sleep(5)

    # ------------------------------------------------------------ maintenance
    def maintenance_tick(self) -> None:
        self.executor.reconcile()
        self.executor.ensure_protective_stops()
        symbols = {t["symbol"] for t in self.db.open_trades()}
        if symbols:
            prices = self.market_data.get_latest_prices(symbols)
            self.executor.check_software_stops(prices)
            self.executor.update_shadow_trades(prices)

    async def _maintenance_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self.maintenance_tick)
            except Exception:
                log.exception("maintenance loop error")
            await asyncio.sleep(30)

    # ------------------------------------------------------------ discord
    async def _discord_task(self) -> None:
        from .discord_bot.bot import SignalBot

        async def on_signal(sig, parsed):
            return await asyncio.to_thread(self.executor.handle_signal, sig)

        self._bot = SignalBot(self.settings, on_signal, self.discord_command)
        self.notifier.add_channel("discord", self._bot.dm_sender())
        try:
            await self._bot.start(self.settings.discord_bot_token)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("discord bot stopped")

    async def discord_command(self, cmd: str, args: list[str]) -> str:
        if cmd == "kill":
            res = await asyncio.to_thread(self.kill_switch.trigger, "Discord !kill", "flatten" in args)
            self.request_stop()
            return f"KILLED. cancelled {res['orders_cancelled']} orders, closed {res['positions_closed']} positions"
        if cmd == "halt":
            self.risk.halt_daily("Discord !halt")
            n = await asyncio.to_thread(self.executor.exit_all, "halt") if "flatten" in args else 0
            return f"halted for today{f', exited {n} trades' if n else ''}"
        if cmd == "status":
            return self.status_text()
        if cmd == "sources":
            return self.sources_text()
        if cmd == "pnl":
            acct = await asyncio.to_thread(self.broker.get_account)
            pos = await asyncio.to_thread(self.broker.get_positions)
            p = self.risk.pnl_snapshot(acct, pos)
            return f"day {p.daily:+,.2f} (real {p.realized_today:+,.2f}) | week {p.weekly:+,.2f} | equity ${acct.equity:,.2f}"
        return "commands: !status !pnl !sources !halt [flatten] !kill [flatten]"

    # ------------------------------------------------------------ text views
    def status_text(self) -> str:
        st = self.risk.status()
        lines = [f"mode={st['mode']} armed={st['armed']} killed={st['killed']} daily_halted={st['daily_halted']} "
                 f"weekly_halted={st['weekly_halted']}",
                 f"cap ${st['capital_cap']:,.0f} risk/trade {st['risk_per_trade_pct']}% daily limit ${st['daily_loss_limit']:,.0f} "
                 f"weekly limit ${st['weekly_loss_limit']:,.0f}"]
        for t in self.db.open_trades(mode=self.settings.mode):
            lines.append(f"open {t['symbol']} x{t['qty']:g} @ {t['entry_price']} stop {t['stop_price']} [{t['status']}] {t['source_id']}")
        return "\n".join(lines)

    def sources_text(self) -> str:
        rows = ["source | status | approved | trades | win% | net | last20"]
        for s in self.tracker.all_stats():
            rows.append(f"{s.source_id} | {s.status} | {'y' if s.approved else 'n'} | {s.trades} | {s.win_rate * 100:.0f} | "
                        f"{s.net_pnl:+,.2f} | {s.last_window_pnl:+,.2f}")
        return "\n".join(rows)

    def write_daily_report(self, now: datetime | None = None, email: bool = True):
        now = now or utcnow()
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        pnl = self.risk.pnl_snapshot(account, positions, now)
        report = build_report(self.settings, self.db, self.tracker, self.risk.status(), vars(pnl),
                              account={"equity": account.equity, "cash": account.cash}, positions=positions,
                              benchmark_fn=market_benchmark_fn(self.market_data), now=now)
        path = save_report(self.settings, report)
        log.info("daily report written to %s", path)
        if email:
            self.notifier.notify("DAILY_REPORT", report.to_markdown())
        return report, path
