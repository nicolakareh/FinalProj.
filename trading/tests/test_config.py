import pytest

from tradesys.config import ConfigError, load_settings


def _write_env(tmp_path, **kv):
    p = tmp_path / ".env"
    p.write_text("\n".join(f"{k}={v}" for k, v in kv.items()))
    return p


def _clear(monkeypatch):
    for k in ["ALPACA_API_KEY", "ALPACA_SECRET_KEY", "LIVE_MODE", "TOTAL_CAPITAL_CAP", "DAILY_LOSS_LIMIT",
              "WEEKLY_LOSS_LIMIT", "MAX_RISK_PER_TRADE_PCT", "DISCORD_SIGNAL_CHANNEL_IDS", "ALPACA_DATA_FEED"]:
        monkeypatch.delenv(k, raising=False)


def test_paper_defaults_when_limits_missing(tmp_path, monkeypatch):
    _clear(monkeypatch)
    env = _write_env(tmp_path, ALPACA_API_KEY="k", ALPACA_SECRET_KEY="s", LIVE_MODE="false")
    s = load_settings(env_file=env, config_file=tmp_path / "missing.yaml")
    assert s.paper and s.limits_defaulted
    assert s.max_risk_per_trade_pct == 2.0


def test_live_mode_requires_limits(tmp_path, monkeypatch):
    _clear(monkeypatch)
    env = _write_env(tmp_path, ALPACA_API_KEY="k", ALPACA_SECRET_KEY="s", LIVE_MODE="true")
    with pytest.raises(ConfigError, match="LIVE_MODE=true requires"):
        load_settings(env_file=env, config_file=tmp_path / "missing.yaml")


def test_risk_pct_hard_ceiling(tmp_path, monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setenv("TOTAL_CAPITAL_CAP", "5000")
    monkeypatch.setenv("DAILY_LOSS_LIMIT", "100")
    monkeypatch.setenv("WEEKLY_LOSS_LIMIT", "300")
    monkeypatch.setenv("MAX_RISK_PER_TRADE_PCT", "5")
    with pytest.raises(ConfigError, match="hard ceiling"):
        load_settings(env_file=tmp_path / "none.env", config_file=tmp_path / "missing.yaml")
    monkeypatch.setenv("MAX_RISK_PER_TRADE_PCT", "1")
    s = load_settings(env_file=tmp_path / "none.env", config_file=tmp_path / "missing.yaml")
    assert s.max_risk_per_trade_pct == 1.0


def test_daily_cannot_exceed_weekly(tmp_path, monkeypatch):
    _clear(monkeypatch)
    env = _write_env(tmp_path, ALPACA_API_KEY="k", ALPACA_SECRET_KEY="s", TOTAL_CAPITAL_CAP=5000,
                     DAILY_LOSS_LIMIT=400, WEEKLY_LOSS_LIMIT=300)
    with pytest.raises(ConfigError, match="DAILY_LOSS_LIMIT must not exceed"):
        load_settings(env_file=env, config_file=tmp_path / "missing.yaml")


def test_strategy_yaml_loads(tmp_path, monkeypatch):
    _clear(monkeypatch)
    env = _write_env(tmp_path, ALPACA_API_KEY="k", ALPACA_SECRET_KEY="s", TOTAL_CAPITAL_CAP=5000,
                     DAILY_LOSS_LIMIT=100, WEEKLY_LOSS_LIMIT=300, DISCORD_SIGNAL_CHANNEL_IDS="1,2")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("strategies:\n  - name: sma_crossover\n    symbols: [spy, btc-usd]\n    params: {fast: 10}\n")
    s = load_settings(env_file=env, config_file=cfg)
    assert s.strategies[0].symbols == ("SPY", "BTC/USD")
    assert s.strategies[0].params == {"fast": 10}
    assert s.discord_signal_channel_ids == (1, 2)
    assert "BTC/USD" in s.all_symbols
