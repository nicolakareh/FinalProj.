import os
from pathlib import Path

import pytest

os.environ.setdefault("TZ", "UTC")

REPO = Path(__file__).resolve().parents[1]


def make_settings(tmp_path: Path, **overrides):
    """Build a Settings object for tests without touching a real .env."""
    from tradesys.config import Settings, StrategyConfig

    base = dict(
        alpaca_api_key="test-key", alpaca_secret_key="test-secret", live_mode=False, data_feed="iex",
        total_capital_cap=10_000.0, max_risk_per_trade_pct=2.0, daily_loss_limit=200.0, weekly_loss_limit=500.0,
        max_open_positions=10, max_orders_per_day=40, default_stop_pct=3.0,
        stock_symbols=("SPY", "AAPL"), crypto_symbols=("BTC/USD",),
        strategies=(StrategyConfig(name="sma_crossover", symbols=("SPY",), timeframe="1Day",
                                   params={"fast": 5, "slow": 20}),),
        alert_email_to="", smtp_host="", smtp_port=587, smtp_user="", smtp_password="",
        twilio_account_sid="", twilio_auth_token="", twilio_from_number="", alert_sms_to="",
        discord_bot_token="", discord_signal_channel_ids=(123,), discord_owner_user_id=42,
        news_api_key="", news_rss_feeds=(), news_poll_seconds=300, news_unusual_k=2.5, news_unusual_min_count=4,
        db_path=str(tmp_path / "test.db"), kill_file=str(tmp_path / "KILL"), reports_dir=str(tmp_path / "reports"),
        backtests_dir=str(tmp_path / "backtests"), data_dir=str(tmp_path / "data"), limits_defaulted=False,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def db(tmp_path):
    from tradesys.storage import Database
    d = Database(tmp_path / "test.db")
    yield d
    d.close()
