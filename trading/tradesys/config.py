"""Settings loaded from .env (secrets, limits) and config.yaml (strategies).

Rules that the user's spec fixes are validated here so that a bad .env cannot
weaken them: risk per trade can never exceed HARD_MAX_RISK_PER_TRADE_PCT and a
live-mode run refuses to start without every dollar limit set.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .common import normalize_symbol

HARD_MAX_RISK_PER_TRADE_PCT = 2.0

DEFAULT_RSS_FEEDS = (
    "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
)


class ConfigError(ValueError):
    pass


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return default if v is None or v.strip() == "" else v.strip()


def _env_bool(name: str, default: bool = False) -> bool:
    v = _env(name)
    if v == "":
        return default
    return v.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float | None = None) -> float | None:
    v = _env(name)
    if v == "":
        return default
    try:
        return float(v.replace(",", "").replace("$", ""))
    except ValueError as e:
        raise ConfigError(f"{name} must be a number, got {v!r}") from e


def _env_int(name: str, default: int) -> int:
    v = _env(name)
    if v == "":
        return default
    try:
        return int(v)
    except ValueError as e:
        raise ConfigError(f"{name} must be an integer, got {v!r}") from e


def _env_list(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    v = _env(name)
    if v == "":
        return tuple(default)
    return tuple(x.strip() for x in v.split(",") if x.strip())


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    symbols: tuple[str, ...]
    timeframe: str = "1Day"
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        return f"strategy:{self.name}"


@dataclass(frozen=True)
class Settings:
    # broker
    alpaca_api_key: str
    alpaca_secret_key: str
    live_mode: bool
    data_feed: str
    # limits
    total_capital_cap: float
    max_risk_per_trade_pct: float
    daily_loss_limit: float
    weekly_loss_limit: float
    max_open_positions: int
    max_orders_per_day: int
    default_stop_pct: float
    # markets
    stock_symbols: tuple[str, ...]
    crypto_symbols: tuple[str, ...]
    strategies: tuple[StrategyConfig, ...]
    # alerts
    alert_email_to: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_from_number: str
    alert_sms_to: str
    # discord
    discord_bot_token: str
    discord_signal_channel_ids: tuple[int, ...]
    discord_owner_user_id: int | None
    # news
    news_api_key: str
    news_rss_feeds: tuple[str, ...]
    news_poll_seconds: int
    news_unusual_k: float
    news_unusual_min_count: int
    # paths
    db_path: str
    kill_file: str
    reports_dir: str
    backtests_dir: str
    data_dir: str
    # misc
    limits_defaulted: bool = False

    @property
    def paper(self) -> bool:
        return not self.live_mode

    @property
    def mode(self) -> str:
        return "live" if self.live_mode else "paper"

    @property
    def all_symbols(self) -> tuple[str, ...]:
        seen: list[str] = []
        for s in self.stock_symbols + self.crypto_symbols:
            if s not in seen:
                seen.append(s)
        for sc in self.strategies:
            for s in sc.symbols:
                if s not in seen:
                    seen.append(s)
        return tuple(seen)

    def strategy(self, name: str) -> StrategyConfig:
        for sc in self.strategies:
            if sc.name == name:
                return sc
        raise ConfigError(f"strategy {name!r} is not listed in config.yaml")


def _load_strategy_configs(config_file: Path | None) -> tuple[StrategyConfig, ...]:
    if config_file is None or not config_file.exists():
        return ()
    raw = yaml.safe_load(config_file.read_text()) or {}
    out = []
    for entry in raw.get("strategies", []) or []:
        if "name" not in entry:
            raise ConfigError("every strategy in config.yaml needs a name")
        symbols = tuple(normalize_symbol(s) for s in entry.get("symbols", []))
        if not symbols:
            raise ConfigError(f"strategy {entry['name']} has no symbols")
        out.append(StrategyConfig(
            name=str(entry["name"]),
            symbols=symbols,
            timeframe=str(entry.get("timeframe", "1Day")),
            params=dict(entry.get("params", {}) or {}),
        ))
    return tuple(out)


def load_settings(env_file: str | Path | None = None, config_file: str | Path | None = None,
                  require_keys: bool = True) -> Settings:
    """Load and validate settings. Raises ConfigError on anything unsafe."""
    if env_file is None:
        env_file = Path(".env")
    if Path(env_file).exists():
        load_dotenv(env_file, override=False)
    if config_file is None:
        config_file = Path("config.yaml")

    live_mode = _env_bool("LIVE_MODE", False)
    api_key = _env("ALPACA_API_KEY")
    secret = _env("ALPACA_SECRET_KEY")
    if require_keys and (not api_key or not secret):
        raise ConfigError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")

    cap = _env_float("TOTAL_CAPITAL_CAP")
    daily = _env_float("DAILY_LOSS_LIMIT")
    weekly = _env_float("WEEKLY_LOSS_LIMIT")
    limits_defaulted = False
    missing = [n for n, v in (("TOTAL_CAPITAL_CAP", cap), ("DAILY_LOSS_LIMIT", daily),
                              ("WEEKLY_LOSS_LIMIT", weekly)) if v is None]
    if missing:
        if live_mode:
            raise ConfigError("LIVE_MODE=true requires " + ", ".join(missing) + " to be set in .env")
        # Paper mode: conservative placeholders so the pipeline can be exercised.
        cap = cap if cap is not None else 10_000.0
        daily = daily if daily is not None else 200.0
        weekly = weekly if weekly is not None else 500.0
        limits_defaulted = True

    risk_pct = _env_float("MAX_RISK_PER_TRADE_PCT", HARD_MAX_RISK_PER_TRADE_PCT) or HARD_MAX_RISK_PER_TRADE_PCT
    if risk_pct <= 0:
        raise ConfigError("MAX_RISK_PER_TRADE_PCT must be positive")
    if risk_pct > HARD_MAX_RISK_PER_TRADE_PCT:
        raise ConfigError(
            f"MAX_RISK_PER_TRADE_PCT={risk_pct} exceeds the hard ceiling of {HARD_MAX_RISK_PER_TRADE_PCT}%")
    for name, val in (("TOTAL_CAPITAL_CAP", cap), ("DAILY_LOSS_LIMIT", daily), ("WEEKLY_LOSS_LIMIT", weekly)):
        if val is None or val <= 0:
            raise ConfigError(f"{name} must be a positive dollar amount")
    if daily > cap or weekly > cap:
        raise ConfigError("DAILY_LOSS_LIMIT and WEEKLY_LOSS_LIMIT must not exceed TOTAL_CAPITAL_CAP")
    if daily > weekly:
        raise ConfigError("DAILY_LOSS_LIMIT must not exceed WEEKLY_LOSS_LIMIT")

    default_stop_pct = _env_float("DEFAULT_STOP_PCT", 3.0) or 3.0
    if not (0 < default_stop_pct < 50):
        raise ConfigError("DEFAULT_STOP_PCT must be between 0 and 50")

    channel_ids: list[int] = []
    for c in _env_list("DISCORD_SIGNAL_CHANNEL_IDS"):
        try:
            channel_ids.append(int(c))
        except ValueError as e:
            raise ConfigError(f"DISCORD_SIGNAL_CHANNEL_IDS contains a non-integer: {c!r}") from e
    owner_raw = _env("DISCORD_OWNER_USER_ID")
    owner_id = int(owner_raw) if owner_raw.isdigit() else None

    feed = _env("ALPACA_DATA_FEED", "iex").lower()
    if feed not in {"iex", "sip"}:
        raise ConfigError("ALPACA_DATA_FEED must be iex or sip")

    settings = Settings(
        alpaca_api_key=api_key,
        alpaca_secret_key=secret,
        live_mode=live_mode,
        data_feed=feed,
        total_capital_cap=float(cap),
        max_risk_per_trade_pct=float(risk_pct),
        daily_loss_limit=float(daily),
        weekly_loss_limit=float(weekly),
        max_open_positions=_env_int("MAX_OPEN_POSITIONS", 10),
        max_orders_per_day=_env_int("MAX_ORDERS_PER_DAY", 40),
        default_stop_pct=float(default_stop_pct),
        stock_symbols=tuple(normalize_symbol(s) for s in _env_list("STOCK_SYMBOLS", ("SPY",))),
        crypto_symbols=tuple(normalize_symbol(s) for s in _env_list("CRYPTO_SYMBOLS", ("BTC/USD",))),
        strategies=_load_strategy_configs(Path(config_file)),
        alert_email_to=_env("ALERT_EMAIL_TO"),
        smtp_host=_env("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_env_int("SMTP_PORT", 587),
        smtp_user=_env("SMTP_USER"),
        smtp_password=_env("SMTP_PASSWORD"),
        twilio_account_sid=_env("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_env("TWILIO_AUTH_TOKEN"),
        twilio_from_number=_env("TWILIO_FROM_NUMBER"),
        alert_sms_to=_env("ALERT_SMS_TO"),
        discord_bot_token=_env("DISCORD_BOT_TOKEN"),
        discord_signal_channel_ids=tuple(channel_ids),
        discord_owner_user_id=owner_id,
        news_api_key=_env("NEWS_API_KEY"),
        news_rss_feeds=tuple(DEFAULT_RSS_FEEDS) + _env_list("NEWS_RSS_FEEDS"),
        news_poll_seconds=_env_int("NEWS_POLL_SECONDS", 300),
        news_unusual_k=_env_float("NEWS_UNUSUAL_K", 2.5) or 2.5,
        news_unusual_min_count=_env_int("NEWS_UNUSUAL_MIN_COUNT", 4),
        db_path=_env("DB_PATH", "data/tradesys.db"),
        kill_file=_env("KILL_FILE", "KILL"),
        reports_dir=_env("REPORTS_DIR", "reports"),
        backtests_dir=_env("BACKTESTS_DIR", "backtests"),
        data_dir=_env("DATA_DIR", "data"),
        limits_defaulted=limits_defaulted,
    )
    return settings
