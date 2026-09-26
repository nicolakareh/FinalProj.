"""Command line interface: `tradesys <command>` (or `python -m tradesys`)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta

from .common import setup_logging, utcnow
from .config import ConfigError, Settings, load_settings
from .storage import Database

log = logging.getLogger("tradesys.cli")


def _settings(args, require_keys: bool = True) -> Settings:
    try:
        return load_settings(env_file=args.env, config_file=args.config, require_keys=require_keys)
    except ConfigError as e:
        sys.exit(f"config error: {e}")


def _db(settings: Settings) -> Database:
    return Database(settings.db_path)


# ---------------------------------------------------------------- commands
def cmd_check_config(args) -> None:
    s = _settings(args, require_keys=False)
    from .alerts import Notifier
    n = Notifier(s)
    print(f"mode:            {s.mode.upper()}  (LIVE_MODE={s.live_mode})")
    print(f"alpaca keys:     {'set' if s.alpaca_api_key and s.alpaca_secret_key else 'MISSING'}")
    print(f"capital cap:     ${s.total_capital_cap:,.2f}{'  (placeholder default!)' if s.limits_defaulted else ''}")
    print(f"risk per trade:  {s.max_risk_per_trade_pct}% (${s.total_capital_cap * s.max_risk_per_trade_pct / 100:,.2f})")
    print(f"daily loss cap:  ${s.daily_loss_limit:,.2f}{'  (placeholder default!)' if s.limits_defaulted else ''}")
    print(f"weekly loss cap: ${s.weekly_loss_limit:,.2f}{'  (placeholder default!)' if s.limits_defaulted else ''}")
    print(f"stocks:          {', '.join(s.stock_symbols)}")
    print(f"crypto:          {', '.join(s.crypto_symbols)}")
    strat_desc = ", ".join(f"{c.name}[{c.timeframe}] on {','.join(c.symbols)}" for c in s.strategies) or "none"
    print(f"strategies:      {strat_desc}")
    print(f"alerts:          {', '.join(n.channels()) or 'NONE configured (set SMTP_* / TWILIO_*)'}")
    print(f"discord:         {'token set, channels ' + str(list(s.discord_signal_channel_ids)) if s.discord_bot_token else 'disabled'}")
    print(f"news api key:    {'set' if s.news_api_key else 'not set (Alpaca news + RSS still work)'}")
    print(f"db / kill file:  {s.db_path} / {s.kill_file}")
    if s.live_mode:
        from .risk.manager import RiskManager
        armed = RiskManager(s, _db(s)).is_armed()
        print(f"live armed:      {armed}  {'' if armed else '(run `tradesys arm` and type GO LIVE to allow real orders)'}")


def cmd_account(args) -> None:
    s = _settings(args)
    from .execution.broker import AlpacaBroker
    b = AlpacaBroker(s)
    a = b.get_account()
    print(f"[{s.mode}] equity ${a.equity:,.2f} cash ${a.cash:,.2f} buying power ${a.buying_power:,.2f} "
          f"multiplier {a.multiplier} daytrades {a.daytrade_count} PDT={a.pattern_day_trader} blocked={a.trading_blocked}")
    for p in b.get_positions():
        print(f"  position {p.symbol} x{p.qty:g} @ {p.avg_entry_price:,.4f} now {p.current_price:,.4f} "
              f"unrealized {p.unrealized_pl:+,.2f}")
    for o in b.get_open_orders():
        print(f"  order {o.id} {o.side} {o.symbol} x{o.qty:g} {o.order_type} {o.status} stop={o.stop_price} limit={o.limit_price}")
    c = b.get_clock()
    print(f"market open: {c.is_open} (next open {c.next_open}, next close {c.next_close})")


def cmd_data(args) -> None:
    s = _settings(args)
    from .data import MarketData, add_indicators
    import pandas as pd
    md = MarketData(s)
    df = md.get_recent_bars(args.symbol, args.timeframe, max(args.bars, 220))
    df = add_indicators(df)
    with pd.option_context("display.width", 200, "display.max_columns", 30, "display.float_format", "{:.4f}".format):
        print(df.tail(args.bars)[["open", "high", "low", "close", "volume", "sma_20", "sma_50", "rsi_14", "atr_14",
                                  "vwap_rolling", "volume_ratio", "volume_spike"]])
    print(f"latest price {args.symbol}: {md.get_latest_price(args.symbol)}")


def cmd_price(args) -> None:
    s = _settings(args)
    from .data import MarketData
    for sym, px in MarketData(s).get_latest_prices(args.symbols).items():
        print(f"{sym}: {px}")


def cmd_news(args) -> None:
    s = _settings(args)
    from .news import NewsMonitor
    db = _db(s)
    mon = NewsMonitor(s, db)
    alerts = mon.poll()
    for sym in s.all_symbols:
        snap = mon.sentiment(sym, hours=args.hours)
        vol = mon.unusual_volume(sym)
        print(f"{sym:8} {snap.label:8} mean {snap.mean:+.2f} n={snap.n} (+{snap.positive}/-{snap.negative}) | "
              f"last hour {vol.count_last_hour} vs threshold {vol.threshold:.1f}{'  <-- UNUSUAL' if vol.unusual else ''}")
    for a in alerts:
        print("\nALERT:", a.message)
    if args.headlines:
        since = utcnow() - timedelta(hours=args.hours)
        from .common import to_iso
        for sym in s.all_symbols:
            for r in db.news_since(sym, to_iso(since))[-args.headlines:]:
                print(f"  {sym:8} {r['published_at'][:16]} {r['sentiment']:+.2f} {r['headline'][:100]}")


def cmd_parse(args) -> None:
    from .discord_bot.parser import parse_trade_call
    p = parse_trade_call(" ".join(args.text))
    print("not a trade call" if p is None else json.dumps(p.__dict__, indent=2, default=str))


def cmd_strategies(args) -> None:
    from .strategies import list_strategies
    for name, desc, params in list_strategies():
        print(f"{name}: {desc}\n    defaults: {params}")


def cmd_backtest(args) -> None:
    s = _settings(args)
    from .backtest.runner import format_result, run_backtest, save_backtest
    from .config import StrategyConfig
    from .data import MarketData
    try:
        cfg = s.strategy(args.strategy)
    except ConfigError:
        cfg = StrategyConfig(args.strategy, tuple(), "1Day", {})
    symbols = tuple(x.upper() for x in args.symbols) if args.symbols else cfg.symbols
    if not symbols:
        sys.exit("no symbols: add the strategy to config.yaml or pass --symbols")
    params = dict(cfg.params)
    for kv in args.param or []:
        k, v = kv.split("=", 1)
        params[k] = json.loads(v) if v.replace(".", "", 1).lstrip("-").isdigit() else v
    cfg = StrategyConfig(cfg.name, symbols, args.timeframe or cfg.timeframe, params)
    md = MarketData(s)
    res = run_backtest(s, md, cfg, years=args.years)
    db = _db(s)
    bt_id = save_backtest(s, db, res, cfg)
    print(format_result(res, bt_id))
    print(f"\nsaved as {bt_id} -> {s.backtests_dir}/{bt_id}.json")
    if res.sufficient_history:
        print(f"approve for live trading with:  tradesys approve {cfg.source_id} --backtest-id {bt_id}")
    else:
        print("NOT eligible for approval: fewer than 2 years of data")


def cmd_backtests(args) -> None:
    s = _settings(args, require_keys=False)
    for row in _db(s).list_backtests(args.strategy):
        m = row["results"].get("metrics", {})
        print(f"{row['id']:40} {row['symbols']:20} ret {m.get('total_return_pct', 0):+7.2f}%  dd {m.get('max_drawdown_pct', 0):6.2f}%  "
              f"trades {m.get('n_trades', 0):4}  {'2y+' if row['results'].get('sufficient_history') else '<2y'}")


def cmd_approve(args) -> None:
    s = _settings(args, require_keys=False)
    from .execution.approvals import ApprovalError, ApprovalRegistry
    reg = ApprovalRegistry(_db(s))
    source = args.source if ":" in args.source else f"strategy:{args.source}"
    try:
        if source.startswith("strategy:"):
            if not args.backtest_id:
                sys.exit("strategies need --backtest-id <id from `tradesys backtest`>")
            row = reg.approve_strategy(s.strategy(source.split(":", 1)[1]), args.backtest_id)
        else:
            row = reg.approve_source(source, args.note or "", acknowledged=args.i_reviewed_the_track_record)
    except (ApprovalError, ConfigError) as e:
        sys.exit(f"not approved: {e}")
    print(f"approved {source}: {row}")


def cmd_revoke(args) -> None:
    s = _settings(args, require_keys=False)
    from .execution.approvals import ApprovalRegistry
    source = args.source if ":" in args.source else f"strategy:{args.source}"
    ApprovalRegistry(_db(s)).revoke(source)
    print(f"revoked {source}")


def cmd_approvals(args) -> None:
    s = _settings(args, require_keys=False)
    from .execution.approvals import ApprovalRegistry
    from .strategies import strategy_code_hash
    reg = ApprovalRegistry(_db(s))
    rows = reg.list()
    if not rows:
        print("no approvals: every source is shadow-tracked only")
    for r in rows:
        note = ""
        if r["source_id"].startswith("strategy:"):
            try:
                cfg = s.strategy(r["source_id"].split(":", 1)[1])
                ok, why = reg.is_approved(r["source_id"], strategy_code_hash(cfg.name, cfg.params))
                note = "" if ok else f"  ** {why}"
            except ConfigError:
                note = "  ** not in config.yaml"
        print(f"{r['source_id']:32} backtest={r['backtest_id']} at {r['approved_at']}{note}")


def cmd_sources(args) -> None:
    s = _settings(args, require_keys=False)
    from .signals import SourceTracker
    stats = SourceTracker(_db(s)).all_stats()
    print(f"{'source':34} {'kind':9} {'status':9} {'appr':5} {'trades':>6} {'win%':>6} {'net':>11} {'last20':>10} {'maxDD':>10} {'fees':>8}")
    for st in stats:
        print(f"{st.source_id:34} {st.kind:9} {st.status:9} {'yes' if st.approved else 'no':5} {st.trades:6} "
              f"{st.win_rate * 100:6.1f} {st.net_pnl:11,.2f} {st.last_window_pnl:10,.2f} {st.max_drawdown:10,.2f} {st.fees:8,.2f}"
              + (f"   [{st.disabled_reason}]" if st.disabled_reason else ""))


def cmd_source_toggle(args) -> None:
    s = _settings(args, require_keys=False)
    from .signals import SourceTracker
    tr = SourceTracker(_db(s))
    if args.action == "enable":
        tr.enable(args.source)
    else:
        tr.disable(args.source, "disabled manually")
    print(f"{args.source}: {args.action}d")


def cmd_status(args) -> None:
    s = _settings(args, require_keys=False)
    from .risk.manager import RiskManager
    db = _db(s)
    rm = RiskManager(s, db)
    for k, v in rm.status().items():
        print(f"{k:22} {v}")
    for t in db.open_trades():
        print(f"trade #{t['id']} {t['mode']} {t['symbol']} x{t['qty']:g} @ {t['entry_price']} stop {t['stop_price']} "
              f"target {t['target_price']} [{t['status']}] {t['source_id']}")
    if s.alpaca_api_key and args.broker:
        from .execution.broker import AlpacaBroker
        b = AlpacaBroker(s)
        p = rm.pnl_snapshot(b.get_account(), b.get_positions())
        print(f"day P&L {p.daily:+,.2f} (realized {p.realized_today:+,.2f}) | week {p.weekly:+,.2f} "
              f"(realized {p.realized_week:+,.2f}) | account day change {p.account_daily:+,.2f}")


def cmd_arm(args) -> None:
    s = _settings(args)
    from .risk.manager import GO_LIVE_PHRASE, RiskManager, RiskViolation
    if not s.live_mode:
        sys.exit("LIVE_MODE is false in .env; nothing to arm (paper trading needs no arming)")
    print("You are about to allow REAL-MONEY orders with these limits:")
    print(f"  capital cap ${s.total_capital_cap:,.2f} | risk/trade {s.max_risk_per_trade_pct}% | "
          f"daily loss ${s.daily_loss_limit:,.2f} | weekly loss ${s.weekly_loss_limit:,.2f}")
    print(f"Type {GO_LIVE_PHRASE} to confirm (anything else aborts): ", end="", flush=True)
    answer = sys.stdin.readline().strip()
    try:
        RiskManager(s, _db(s)).arm_live(answer)
    except RiskViolation as e:
        sys.exit(f"not armed: {e}")
    print("ARMED. Live orders are now allowed for approved sources. `tradesys disarm` reverses this.")


def cmd_disarm(args) -> None:
    s = _settings(args, require_keys=False)
    from .risk.manager import RiskManager
    RiskManager(s, _db(s)).disarm()
    print("disarmed: no real orders will be placed")


def cmd_kill(args) -> None:
    s = _settings(args)
    from .alerts import Notifier
    from .execution.broker import AlpacaBroker
    from .risk.kill_switch import KillSwitch
    from .risk.manager import RiskManager
    db = _db(s)
    ks = KillSwitch(s, db, AlpacaBroker(s), RiskManager(s, db), Notifier(s, db, sync=True))
    res = ks.trigger(args.reason or "manual kill from CLI", flatten=args.flatten)
    print(json.dumps(res, indent=2))
    print("A running engine stops within 5 seconds. Clear with: tradesys resume --kill")


def cmd_resume(args) -> None:
    s = _settings(args, require_keys=False)
    from .risk.manager import RiskManager
    rm = RiskManager(s, _db(s))
    if not (args.weekly or args.kill or args.daily):
        sys.exit("say what to resume: --weekly, --daily and/or --kill")
    print("Type RESUME to confirm: ", end="", flush=True)
    if sys.stdin.readline().strip() != "RESUME":
        sys.exit("aborted")
    if args.weekly:
        rm.resume_weekly()
        print("weekly halt cleared")
    if args.daily:
        rm.db.set_state(rm.K_DAILY_HALT, None)
        rm.db.set_state(rm.K_DAILY_REASON, None)
        print("daily halt cleared")
    if args.kill:
        rm.clear_kill()
        print("kill state cleared")


def cmd_run(args) -> None:
    s = _settings(args)
    from .engine import TradingEngine
    engine = TradingEngine(s)
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        pass


def cmd_report(args) -> None:
    s = _settings(args, require_keys=not args.offline)
    from .reporting.daily_report import build_report, save_report
    from .risk.manager import RiskManager
    from .signals import SourceTracker
    db = _db(s)
    rm = RiskManager(s, db)
    tracker = SourceTracker(db)
    report_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    account, positions, bench = {}, [], None
    pnl = {"daily": 0.0, "weekly": 0.0, "realized_today": 0.0, "realized_week": 0.0, "unrealized_intraday": 0.0,
           "unrealized_total": 0.0}
    if not args.offline:
        from .data import MarketData
        from .execution.broker import AlpacaBroker
        from .reporting.daily_report import market_benchmark_fn
        b = AlpacaBroker(s)
        acct, positions = b.get_account(), b.get_positions()
        account = {"equity": acct.equity, "cash": acct.cash}
        pnl = vars(rm.pnl_snapshot(acct, positions))
        bench = market_benchmark_fn(MarketData(s))
    else:
        from .common import NY
        now = utcnow()
        pnl["realized_today"], _ = db.realized_pnl_since(rm._day_start_iso(now), (s.mode,))
        pnl["realized_week"], _ = db.realized_pnl_since(rm._week_start_iso(now), (s.mode,))
        pnl["daily"], pnl["weekly"] = pnl["realized_today"], pnl["realized_week"]
    report = build_report(s, db, tracker, rm.status(), pnl, account=account, positions=positions,
                          report_date=report_date, benchmark_fn=bench)
    path = save_report(s, report)
    print(report.to_markdown())
    print(f"\nsaved to {path}")
    if args.email:
        from .alerts import Notifier
        Notifier(s, db, sync=True).notify("DAILY_REPORT", report.to_markdown())
        print("emailed/sent via configured alert channels")


def cmd_test_alert(args) -> None:
    s = _settings(args, require_keys=False)
    from .alerts import Notifier
    n = Notifier(s, sync=True)
    if not n.channels():
        sys.exit("no alert channels configured; set SMTP_* / ALERT_EMAIL_TO and/or TWILIO_* / ALERT_SMS_TO")
    n.notify("TEST", "tradesys test alert: if you can read this, alerts work.")
    print(f"sent via {n.channels()}")


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tradesys", description="Alpaca trading system with hard risk limits")
    p.add_argument("--env", default=".env", help="path to .env")
    p.add_argument("--config", default="config.yaml", help="path to config.yaml")
    p.add_argument("--log-level", default="INFO")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check-config", help="validate .env / config.yaml").set_defaults(fn=cmd_check_config)
    sub.add_parser("account", help="show the Alpaca account, positions and open orders").set_defaults(fn=cmd_account)
    d = sub.add_parser("data", help="recent bars with indicators")
    d.add_argument("symbol"); d.add_argument("--timeframe", default="1Day"); d.add_argument("--bars", type=int, default=20)
    d.set_defaults(fn=cmd_data)
    pr = sub.add_parser("price", help="latest prices"); pr.add_argument("symbols", nargs="+"); pr.set_defaults(fn=cmd_price)
    n = sub.add_parser("news", help="poll news once and show sentiment / unusual volume")
    n.add_argument("--hours", type=float, default=6); n.add_argument("--headlines", type=int, default=0); n.set_defaults(fn=cmd_news)
    pa = sub.add_parser("parse", help="test the Discord trade-call parser"); pa.add_argument("text", nargs="+"); pa.set_defaults(fn=cmd_parse)
    sub.add_parser("strategies", help="list strategies").set_defaults(fn=cmd_strategies)
    b = sub.add_parser("backtest", help="backtest a strategy on 2+ years of data")
    b.add_argument("strategy"); b.add_argument("--years", type=float, default=2.0); b.add_argument("--symbols", nargs="*")
    b.add_argument("--timeframe"); b.add_argument("--param", action="append", help="override, e.g. --param fast=10")
    b.set_defaults(fn=cmd_backtest)
    bl = sub.add_parser("backtests", help="list saved backtests"); bl.add_argument("--strategy"); bl.set_defaults(fn=cmd_backtests)
    ap = sub.add_parser("approve", help="approve a source for real orders")
    ap.add_argument("source", help="strategy name, strategy:<name>, discord:<user id> or news:momentum")
    ap.add_argument("--backtest-id"); ap.add_argument("--i-reviewed-the-track-record", action="store_true"); ap.add_argument("--note")
    ap.set_defaults(fn=cmd_approve)
    rv = sub.add_parser("revoke", help="revoke an approval"); rv.add_argument("source"); rv.set_defaults(fn=cmd_revoke)
    sub.add_parser("approvals", help="list approvals").set_defaults(fn=cmd_approvals)
    sub.add_parser("sources", help="track record of every signal source").set_defaults(fn=cmd_sources)
    for action in ("enable", "disable"):
        t = sub.add_parser(f"{action}-source", help=f"{action} a signal source"); t.add_argument("source")
        t.set_defaults(fn=cmd_source_toggle, action=action)
    st = sub.add_parser("status", help="risk state and open trades"); st.add_argument("--broker", action="store_true")
    st.set_defaults(fn=cmd_status)
    sub.add_parser("arm", help="allow real orders (asks you to type GO LIVE)").set_defaults(fn=cmd_arm)
    sub.add_parser("disarm", help="block real orders again").set_defaults(fn=cmd_disarm)
    k = sub.add_parser("kill", help="KILL SWITCH: cancel all orders, stop the engine")
    k.add_argument("--flatten", action="store_true", help="also market-sell every position"); k.add_argument("--reason")
    k.set_defaults(fn=cmd_kill)
    r = sub.add_parser("resume", help="clear a halt / kill state")
    r.add_argument("--weekly", action="store_true"); r.add_argument("--daily", action="store_true"); r.add_argument("--kill", action="store_true")
    r.set_defaults(fn=cmd_resume)
    sub.add_parser("run", help="start the trading engine").set_defaults(fn=cmd_run)
    rp = sub.add_parser("report", help="daily report")
    rp.add_argument("--date"); rp.add_argument("--email", action="store_true"); rp.add_argument("--offline", action="store_true",
                                                                                                 help="no broker/data calls")
    rp.set_defaults(fn=cmd_report)
    sub.add_parser("test-alert", help="send a test email/SMS").set_defaults(fn=cmd_test_alert)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level, log_dir="logs" if args.command == "run" else None)
    args.fn(args)


if __name__ == "__main__":
    main()
