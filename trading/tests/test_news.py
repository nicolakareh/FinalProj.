from datetime import timedelta

from tradesys.common import utcnow
from tradesys.news.feed import NewsItem, extract_symbols
from tradesys.news.monitor import NEWS_SOURCE_ID, NewsMonitor
from tradesys.news.sentiment import SentimentScorer
from tradesys.alerts import Notifier
from tradesys.signals.models import Direction


UNIVERSE = ("AAPL", "TSLA", "SPY", "BTC/USD", "ETH/USD")


def test_extract_symbols_variants():
    assert extract_symbols("Apple beats on earnings, $AAPL up 5%", UNIVERSE) == ("AAPL",)
    assert extract_symbols("Tesla (NASDAQ: TSLA) recalls vehicles", UNIVERSE) == ("TSLA",)
    assert extract_symbols("Bitcoin surges past $70k while ether lags", UNIVERSE) == ("BTC/USD", "ETH/USD")
    assert extract_symbols("Nothing about any ticker here", UNIVERSE) == ()
    # a bare 'SPY' word only counts when it looks like a market reference
    assert extract_symbols("SPY shares fall", UNIVERSE) == ("SPY",)
    assert extract_symbols("I spy with my little eye", UNIVERSE) == ()


def test_sentiment_direction():
    s = SentimentScorer()
    assert s.score("Apple beats estimates, shares surge to record high") > 0.3
    assert s.score("SEC charges company with fraud; stock plunges after guidance cut") < -0.3
    assert abs(s.score("Company to hold annual meeting on Tuesday")) < 0.2
    assert s.label(0.5) == "positive" and s.label(-0.5) == "negative" and s.label(0.0) == "neutral"


def _item(i, sym, headline, when):
    return NewsItem(id=f"t{i}", headline=headline, summary="", source="test", url=f"http://x/{i}",
                    published_at=when, symbols=(sym,))


def test_monitor_flags_unusual_volume_and_alerts(settings, db):
    notifier = Notifier(settings, db, sync=True)
    mon = NewsMonitor(settings, db, notifier=notifier, fetcher=None, universe=UNIVERSE) if False else \
        NewsMonitor.__new__(NewsMonitor)
    # build without a network fetcher
    NewsMonitor.__init__(mon, settings, db, notifier=notifier, fetcher=object(), universe=UNIVERSE)
    now = utcnow()
    # quiet baseline: one headline a day for a week
    baseline = [_item(f"b{d}", "AAPL", "Apple holds event", now - timedelta(days=d, hours=3)) for d in range(1, 8)]
    assert mon.poll(now=now - timedelta(hours=2), items=baseline) == []
    # burst: six positive headlines in the last hour
    burst = [_item(f"x{i}", "AAPL", "Apple beats estimates, shares surge to record", now - timedelta(minutes=5 * i))
             for i in range(6)]
    alerts = mon.poll(now=now, items=burst)
    assert len(alerts) == 1 and alerts[0].symbol == "AAPL"
    assert alerts[0].volume.unusual and alerts[0].volume.count_last_hour == 6
    assert alerts[0].sentiment.label == "positive"
    assert notifier.sent and notifier.sent[-1][0] == "NEWS_ALERT"
    # cooldown: a second poll inside the hour does not re-alert
    assert mon.poll(now=now + timedelta(minutes=1), items=[_item("y", "AAPL", "Apple again", now)]) == []
    # signals: long only, with stop and target attached
    sigs = mon.signals(alerts, price_lookup=lambda s: 200.0, now=now)
    assert len(sigs) == 1
    sig = sigs[0]
    assert sig.source_id == NEWS_SOURCE_ID and sig.direction == Direction.LONG
    assert sig.stop == 194.0 and sig.target == 212.0
    # negative sentiment bursts never produce a signal
    bad = [_item(f"n{i}", "TSLA", "Tesla plunges after fraud probe and recall", now - timedelta(minutes=i))
           for i in range(6)]
    bad_alerts = mon.poll(now=now, items=bad)
    assert bad_alerts and bad_alerts[0].sentiment.label == "negative"
    assert mon.signals(bad_alerts, price_lookup=lambda s: 100.0, now=now) == []


def test_ingest_dedupes(settings, db):
    mon = NewsMonitor.__new__(NewsMonitor)
    NewsMonitor.__init__(mon, settings, db, fetcher=object(), universe=UNIVERSE)
    now = utcnow()
    item = _item("dup", "AAPL", "Apple beats", now)
    assert len(mon.ingest([item])) == 1
    assert len(mon.ingest([item])) == 0
