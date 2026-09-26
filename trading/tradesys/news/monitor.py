"""Polls news sources, scores sentiment per ticker, stores items, flags unusual news
volume and raises real-time alerts. Also emits `news:momentum` trade signals that are
tracked like any other source (shadow first, real orders only once you approve it).
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterable

from ..alerts import Notifier
from ..common import to_iso, utcnow
from ..config import Settings
from ..signals.models import Direction, Signal
from ..storage import Database
from .feed import NewsFetcher, NewsItem
from .sentiment import SentimentScorer

log = logging.getLogger(__name__)

NEWS_SOURCE_ID = "news:momentum"


@dataclass
class VolumeCheck:
    symbol: str
    count_last_hour: int
    baseline_mean: float
    baseline_std: float
    threshold: float
    unusual: bool


@dataclass
class SentimentSnapshot:
    symbol: str
    mean: float
    n: int
    positive: int
    negative: int

    @property
    def label(self) -> str:
        return SentimentScorer.label(self.mean)


@dataclass
class NewsAlert:
    symbol: str
    message: str
    volume: VolumeCheck
    sentiment: SentimentSnapshot


class NewsMonitor:
    def __init__(self, settings: Settings, db: Database, notifier: Notifier | None = None,
                 fetcher: NewsFetcher | None = None, scorer: SentimentScorer | None = None,
                 universe: Iterable[str] | None = None, alert_cooldown_minutes: int = 60,
                 signal_sentiment_threshold: float = 0.35):
        self.settings = settings
        self.db = db
        self.notifier = notifier
        self.universe = tuple(universe) if universe is not None else settings.all_symbols
        self.fetcher = fetcher or NewsFetcher(settings, self.universe)
        self.scorer = scorer or SentimentScorer()
        self.alert_cooldown = timedelta(minutes=alert_cooldown_minutes)
        self.signal_sentiment_threshold = signal_sentiment_threshold
        self._last_alert: dict[str, datetime] = {}
        self._last_signal: dict[str, datetime] = {}

    # --------------------------------------------------------------- ingest
    def ingest(self, items: Iterable[NewsItem]) -> list[tuple[NewsItem, float]]:
        """Score and persist items; returns the ones that were new."""
        new: list[tuple[NewsItem, float]] = []
        for item in items:
            score = self.scorer.score(item.text)
            inserted_any = False
            for sym in item.symbols:
                if self.db.insert_news(f"{item.id}:{sym}", item.id, sym, item.headline, item.source, item.url,
                                       item.published_at, score):
                    inserted_any = True
            if inserted_any:
                new.append((item, score))
        return new

    # ------------------------------------------------------------- analysis
    def unusual_volume(self, symbol: str, now: datetime | None = None, baseline_days: int = 7) -> VolumeCheck:
        now = now or utcnow()
        counts = self.db.news_counts_by_hour(symbol, to_iso(now - timedelta(days=baseline_days)))
        last_hour = len(self.db.news_since(symbol, to_iso(now - timedelta(hours=1))))
        current_bucket = to_iso(now)[:13]
        hourly = [n for hour, n in counts.items() if hour != current_bucket]
        total_hours = baseline_days * 24
        hourly = hourly + [0] * max(0, total_hours - len(hourly))  # quiet hours count as zero
        mean = statistics.fmean(hourly) if hourly else 0.0
        std = statistics.pstdev(hourly) if len(hourly) > 1 else 0.0
        threshold = max(float(self.settings.news_unusual_min_count), mean + self.settings.news_unusual_k * std)
        return VolumeCheck(symbol, last_hour, mean, std, threshold, last_hour >= threshold)

    def sentiment(self, symbol: str, hours: float = 6.0, now: datetime | None = None) -> SentimentSnapshot:
        now = now or utcnow()
        rows = self.db.news_since(symbol, to_iso(now - timedelta(hours=hours)))
        scores = [float(r["sentiment"]) for r in rows if r["sentiment"] is not None]
        if not scores:
            return SentimentSnapshot(symbol, 0.0, 0, 0, 0)
        return SentimentSnapshot(symbol, statistics.fmean(scores), len(scores),
                                 sum(1 for s in scores if s >= 0.2), sum(1 for s in scores if s <= -0.2))

    # ----------------------------------------------------------------- poll
    def poll(self, now: datetime | None = None, items: Iterable[NewsItem] | None = None) -> list[NewsAlert]:
        """Fetch, ingest and alert. `items` lets tests/replays bypass the network."""
        now = now or utcnow()
        if items is None:
            items = self.fetcher.fetch(since=now - timedelta(hours=6))
        new = self.ingest(items)
        if new:
            log.info("news: %d new headline(s)", len(new))
        alerts: list[NewsAlert] = []
        touched = {sym for item, _ in new for sym in item.symbols}
        for sym in sorted(touched):
            vol = self.unusual_volume(sym, now)
            if not vol.unusual:
                continue
            last = self._last_alert.get(sym)
            if last and now - last < self.alert_cooldown:
                continue
            snap = self.sentiment(sym, now=now)
            recent = self.db.news_since(sym, to_iso(now - timedelta(hours=1)))
            headlines = "\n".join(f"  [{SentimentScorer.label(float(r['sentiment'] or 0))[:3]}] {r['headline'][:110]}"
                                  for r in recent[-5:])
            msg = (f"Unusual news volume for {sym}: {vol.count_last_hour} headlines in the last hour "
                   f"(baseline {vol.baseline_mean:.2f}/h, threshold {vol.threshold:.1f}). "
                   f"6h sentiment {snap.mean:+.2f} ({snap.label}, {snap.n} items, +{snap.positive}/-{snap.negative}).\n"
                   f"{headlines}")
            alert = NewsAlert(sym, msg, vol, snap)
            alerts.append(alert)
            self._last_alert[sym] = now
            if self.notifier:
                self.notifier.notify("NEWS_ALERT", msg)
        return alerts

    # -------------------------------------------------------------- signals
    def signals(self, alerts: Iterable[NewsAlert], price_lookup: Callable[[str], float | None],
                now: datetime | None = None, stop_pct: float | None = None, target_r: float = 2.0) -> list[Signal]:
        """Turn unusual-volume + clearly positive sentiment into long signals (never shorts)."""
        now = now or utcnow()
        stop_pct = stop_pct if stop_pct is not None else self.settings.default_stop_pct
        out: list[Signal] = []
        for alert in alerts:
            if alert.sentiment.mean < self.signal_sentiment_threshold or alert.sentiment.n < 2:
                continue
            last = self._last_signal.get(alert.symbol)
            if last and now - last < timedelta(hours=12):
                continue
            price = price_lookup(alert.symbol)
            if not price or price <= 0:
                continue
            stop = round(price * (1 - stop_pct / 100.0), 4)
            target = round(price + (price - stop) * target_r, 4)
            out.append(Signal(
                source_id=NEWS_SOURCE_ID, source_kind="news", source_name="News momentum", symbol=alert.symbol,
                direction=Direction.LONG, entry=price, stop=stop, target=target, timestamp=now,
                raw_text=alert.message.splitlines()[0],
            ))
            self._last_signal[alert.symbol] = now
        return out
