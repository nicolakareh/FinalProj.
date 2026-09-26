# tradesys - Alpaca trading system with code-enforced risk limits

A Python trading system for Alpaca (US stocks + crypto). It runs in **paper mode by
default**; real-money orders need `LIVE_MODE=true` **and** an explicit arming step
where you type `GO LIVE`. Every order passes through one risk module that cannot be
skipped, and every strategy or signal source must be approved by you before it may
place a real order.

```
trading/
  tradesys/
    config.py            .env + config.yaml loading, limit validation
    data/                Alpaca market data (live + historical) and indicators
    news/                headline feeds, sentiment, unusual-volume alerts, news signals
    discord_bot/         official Discord bot + trade-call parser
    signals/             Signal model and per-source track record (auto-disable rule)
    strategies/          long-only strategies with ATR stops
    backtest/            event-driven backtester with fees/slippage + buy-and-hold benchmarks
    risk/                RiskManager (all hard rules), sizing, kill switch
    execution/           Alpaca broker wrapper, approvals registry, executor, fake broker
    reporting/           daily report
    engine.py            asyncio orchestrator
    cli.py               `tradesys ...` commands
  tests/                 pytest suite (no network needed)
  config.yaml            strategy assignments
  .env.example           every setting, with comments
```

## 1. Setup

```bash
cd trading
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # fill in keys, limits, alert settings
pytest -q                     # 100+ tests, all offline
tradesys check-config
```

Alpaca paper keys and live keys are different key pairs. Put whichever pair matches
`LIVE_MODE` in `.env`. Nothing is hardcoded; `.env` is git-ignored.

## 2. Configuration

`.env` holds secrets and dollar limits:

| Variable | Meaning |
|---|---|
| `LIVE_MODE` | `false` = paper endpoint (default). `true` = real account. Flip to `false` at any time to fall back to paper instantly. |
| `TOTAL_CAPITAL_CAP` | The most the system will ever deploy, regardless of account size. |
| `MAX_RISK_PER_TRADE_PCT` | Loss at the stop as % of the cap. Hard ceiling of 2; a larger value refuses to load. |
| `DAILY_LOSS_LIMIT` | Day P&L (realized + unrealized) at which entries halt until the next trading day. |
| `WEEKLY_LOSS_LIMIT` | Week P&L at which entries halt until you run `tradesys resume --weekly`. |
| `MAX_OPEN_POSITIONS`, `MAX_ORDERS_PER_DAY` | Runaway guards. |
| `DEFAULT_STOP_PCT` | Stop used when a Discord/news signal gives none. |
| `STOCK_SYMBOLS`, `CRYPTO_SYMBOLS` | Universe for news and price monitoring. |
| `SMTP_*`, `ALERT_EMAIL_TO`, `TWILIO_*`, `ALERT_SMS_TO` | Email / SMS alerts. |
| `DISCORD_BOT_TOKEN`, `DISCORD_SIGNAL_CHANNEL_IDS`, `DISCORD_OWNER_USER_ID` | Discord bot. |
| `NEWS_API_KEY`, `NEWS_RSS_FEEDS`, `NEWS_UNUSUAL_*` | News sources and the unusual-volume threshold. |

In live mode all three dollar limits are mandatory; the process refuses to start
without them. In paper mode missing limits fall back to placeholders and are flagged
everywhere as such.

`config.yaml` assigns strategies to symbols and timeframes:

```yaml
strategies:
  - name: sma_crossover
    symbols: [SPY, AAPL]
    timeframe: 1Day
    params: {fast: 20, slow: 50, atr_period: 14, atr_mult: 2.0, target_r: 3.0}
```

Built-in strategies (`tradesys strategies`): `sma_crossover`, `rsi_reversion`,
`breakout_volume`. All are long-only and attach an ATR-based stop and a target to
every entry.

## 3. Safety model (what is enforced, and where)

All rules live in `tradesys/risk/manager.py` and run on **every** order. The broker
wrapper (`execution/broker.py`) refuses to submit anything that does not carry a
`RiskApproval` signed by the risk manager in this process, so strategies, Discord
signals and CLI commands all go through the same checks.

| Rule | Enforcement |
|---|---|
| Capital cap | `capital_cap`: positions' cost basis + open buy orders + this order must fit in `TOTAL_CAPITAL_CAP`. |
| Max 2% risk per trade, stop on every order | `stop_required` and `risk_per_trade`: buys without a stop below entry are rejected; `qty * (entry - stop) <= 2% * cap`. Sizing uses the same formula in backtests and live. Stocks are sent as bracket/OTO orders with the stop attached; crypto (no bracket support at Alpaca) gets a GTC stop-limit sell right after the fill plus a software stop monitor. |
| Daily loss limit | `check_loss_limits` every 5 s and after every fill: realized today + unrealized intraday <= -limit halts new entries until the next New York trading day. Pending entry orders are cancelled; protective stops stay. |
| Weekly loss limit | Same check on the Monday-to-date window; halt persists in SQLite until `tradesys resume --weekly` (you must type `RESUME`). |
| No leverage / margin | `no_margin`: order notional must fit in settled cash (`cash` and non-marginable buying power), never buying power. |
| No shorting | `no_short`: sells may only reduce an existing long, never exceed it. Short calls from Discord are recorded for the caller's track record but never executed. |
| No options | `asset_class`: only `us_equity` and `crypto` assets; option-style symbols and option keywords in Discord calls are rejected. |
| Kill switch | `tradesys kill [--flatten]`, Discord `!kill [flatten]` from the owner, or creating the `KILL` file: cancels all orders, optionally market-sells everything, persists a killed state that stops the engine within 5 s and blocks restarts until `tradesys resume --kill`. |
| Live gate | Real orders need `LIVE_MODE=true` **and** `tradesys arm` (type `GO LIVE`). `tradesys disarm` or flipping `LIVE_MODE` blocks them again. |
| Approval gate | A source places real orders only if approved: strategies against a 2+ year backtest whose code/params hash still matches; Discord callers and the news trigger only after you review their shadow track record. |
| Auto-disable | A source whose net P&L over its last 20 closed trades is negative is disabled automatically (`signals/tracker.py`) and stays off until `tradesys enable-source`. |
| Extra guards | One position per symbol, `MAX_OPEN_POSITIONS`, `MAX_ORDERS_PER_DAY`, no stock entries while the market is closed, no stock entries when the account is under $25k with 3 day trades used (PDT). |

Alerts (email, SMS, Discord DM to you) fire on every fill, every stop or target hit,
every halt, the kill switch, unusual news volume, a source being auto-disabled, and
errors. `tradesys test-alert` verifies the channels.

## 4. Workflow: paper -> backtest -> approve -> GO LIVE

1. **Paper first.** With `LIVE_MODE=false` run `tradesys run`. Every strategy and
   caller is shadow-tracked (simulated fills at real prices) until approved; approved
   sources trade paper money.
2. **Backtest** a strategy on 2+ years: `tradesys backtest sma_crossover --years 2`.
   The report compares it with buying and holding SPY, BTC/USD and the traded
   symbols, after fees and slippage. Backtests shorter than 2 years are saved but
   cannot be used for approval.
3. **Approve** what you like: `tradesys approve sma_crossover --backtest-id <id>`.
   Editing the strategy or its params invalidates the approval until you backtest again.
   Discord callers: `tradesys sources` shows their shadow record, then
   `tradesys approve discord:<user id> --i-reviewed-the-track-record`.
4. **Go live** only when ready: set `LIVE_MODE=true` with live keys and real dollar
   limits, run `tradesys arm`, type `GO LIVE`, then `tradesys run`.

## 5. Commands

```
tradesys check-config                 validate .env / config.yaml
tradesys account                      account, positions, open orders, market clock
tradesys data AAPL --timeframe 1Day   bars with SMA/EMA/RSI/ATR/VWAP/volume-spike columns
tradesys price AAPL BTC/USD           latest prices
tradesys news --headlines 5           poll news once: sentiment per ticker, unusual volume
tradesys parse "long $TSLA 250 sl 240 tp 270"   test the Discord parser
tradesys strategies / backtest / backtests / approve / revoke / approvals
tradesys sources                      every source's trades, win rate, net P&L, last-20 P&L
tradesys enable-source / disable-source
tradesys status [--broker]            halts, kill, armed state, open trades, day/week P&L
tradesys arm / disarm                 GO LIVE gate
tradesys kill [--flatten]             kill switch
tradesys resume --weekly|--daily|--kill
tradesys run                          start the engine
tradesys report [--email] [--offline] daily report (also written automatically after the close)
tradesys test-alert
```

The daily report (`reports/<date>-<mode>.md`) lists the day's trades, P&L, win rate,
max drawdown, fees, open trades, and each source's record against buying and
holding SPY and BTC over that source's active window.

## 6. Discord bot

Create an application at discord.com/developers, add a bot, enable the **Message
Content** intent, invite it to the servers with read-message and add-reaction
permissions, and put the bot token in `.env`. The bot reads only the channel IDs you
list, parses calls such as `Long $AAPL entry 150 stop 145 target 160`,
`Buy BTC 65k sl 63k tp 70k`, `Sold NVDA`, and reacts with a check (real order),
notebook (shadow-tracked) or cross (rejected). It never logs in with your user account.

## 7. Known limits and caveats

- Alpaca crypto orders cannot carry bracket legs, so crypto stops are separate
  stop-limit orders (limit 1% below the stop) backed by the software stop monitor,
  which market-sells if price is through the stop and no live stop order remains.
- Fees are estimated with the backtester's fee model (Alpaca stock regulatory fees on
  sells, 0.25% crypto). Check `FeeModel` against your Alpaca fee tier.
- Daily/weekly P&L combines the ledger's realized P&L with the broker's unrealized
  P&L for open positions. Trades placed outside tradesys are not counted, and the
  capital cap only governs tradesys' own orders.
- Alpaca accounts are margin accounts by default; tradesys never spends beyond
  settled cash, but a cash account removes the possibility entirely.
- Backtests use daily/hourly bars from the free IEX feed unless `ALPACA_DATA_FEED=sip`.
  IEX volume is a fraction of consolidated volume; volume-based strategies behave
  differently on SIP data.
- The news momentum trigger and Discord callers cannot be backtested; their record is
  built forward in shadow mode.
