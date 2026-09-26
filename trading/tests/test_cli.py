import pytest

from tradesys.cli import main


@pytest.fixture
def env(tmp_path, monkeypatch):
    for k in ["ALPACA_API_KEY", "ALPACA_SECRET_KEY", "LIVE_MODE", "TOTAL_CAPITAL_CAP", "DAILY_LOSS_LIMIT",
              "WEEKLY_LOSS_LIMIT", "DB_PATH", "REPORTS_DIR", "KILL_FILE"]:
        monkeypatch.delenv(k, raising=False)
    envf = tmp_path / ".env"
    envf.write_text(f"ALPACA_API_KEY=k\nALPACA_SECRET_KEY=s\nTOTAL_CAPITAL_CAP=5000\nDAILY_LOSS_LIMIT=100\n"
                    f"WEEKLY_LOSS_LIMIT=300\nDB_PATH={tmp_path / 'cli.db'}\nREPORTS_DIR={tmp_path / 'reports'}\n"
                    f"KILL_FILE={tmp_path / 'KILL'}\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("strategies:\n  - name: sma_crossover\n    symbols: [SPY]\n    params: {fast: 10, slow: 30}\n")
    return ["--env", str(envf), "--config", str(cfg)]


def test_offline_commands(env, capsys):
    main(env + ["check-config"])
    out = capsys.readouterr().out
    assert "PAPER" in out and "$5,000.00" in out and "placeholder" not in out
    main(env + ["strategies"])
    assert "sma_crossover" in capsys.readouterr().out
    main(env + ["parse", "Long", "$TSLA", "entry", "250", "stop", "240", "target", "270"])
    assert '"stop": 240.0' in capsys.readouterr().out
    main(env + ["status"])
    assert "killed" in capsys.readouterr().out
    main(env + ["approvals"])
    assert "no approvals" in capsys.readouterr().out
    main(env + ["backtests"])
    main(env + ["sources"])
    main(env + ["report", "--offline"])
    out = capsys.readouterr().out
    assert "daily report" in out and "saved to" in out
    with pytest.raises(SystemExit):
        main(env + ["approve", "sma_crossover"])  # needs --backtest-id
    with pytest.raises(SystemExit):
        main(env + ["approve", "sma_crossover", "--backtest-id", "missing"])
    with pytest.raises(SystemExit):
        main(env + ["approve", "discord:1"])  # needs acknowledgement flag
    main(env + ["disable-source", "discord:1"])
    main(env + ["enable-source", "discord:1"])
    main(env + ["disarm"])
    assert "disarmed" in capsys.readouterr().out


def test_arm_refused_in_paper_mode(env):
    with pytest.raises(SystemExit, match="LIVE_MODE is false"):
        main(env + ["arm"])
