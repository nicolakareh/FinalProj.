"""Headline collection from Alpaca's news API, RSS feeds and (optionally) newsapi.org.

Each `NewsItem` carries the tickers it is about. Alpaca supplies symbols directly;
RSS/NewsAPI headlines are matched against the configured universe by cashtag,
exchange tag, bare ticker or company name.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

import feedparser
import requests

from ..common import UTC, from_iso, is_crypto, utcnow
from ..config import Settings

log = logging.getLogger(__name__)

# Names that headlines use for common tickers. Extend freely in config.
COMPANY_NAMES: dict[str, tuple[str, ...]] = {
    "AAPL": ("apple",), "MSFT": ("microsoft",), "GOOGL": ("alphabet", "google"), "GOOG": ("alphabet", "google"),
    "AMZN": ("amazon",), "META": ("meta platforms", "facebook"), "NVDA": ("nvidia",), "TSLA": ("tesla",),
    "AMD": ("advanced micro devices",), "NFLX": ("netflix",), "INTC": ("intel",), "SPY": ("s&p 500", "s&p500"),
    "QQQ": ("nasdaq 100", "nasdaq-100"), "JPM": ("jpmorgan", "jp morgan"), "BAC": ("bank of america",),
    "XOM": ("exxon",), "COIN": ("coinbase",), "MSTR": ("microstrategy", "strategy inc"),
    "BTC/USD": ("bitcoin", "btc"), "ETH/USD": ("ethereum", "ether", "eth"), "SOL/USD": ("solana",),
    "DOGE/USD": ("dogecoin",), "LTC/USD": ("litecoin",), "AVAX/USD": ("avalanche",), "LINK/USD": ("chainlink",),
    "XRP/USD": ("ripple", "xrp"),
}


@dataclass
class NewsItem:
    id: str
    headline: str
    summary: str
    source: str
    url: str
    published_at: datetime
    symbols: tuple[str, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        return f"{self.headline}. {self.summary}".strip()


def _stable_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:20]


def extract_symbols(text: str, universe: Iterable[str], names: dict[str, tuple[str, ...]] | None = None) -> tuple[str, ...]:
    """Tickers from `universe` that `text` refers to."""
    names = names or COMPANY_NAMES
    lower = text.lower()
    found: list[str] = []
    for sym in universe:
        base = sym.split("/")[0]
        patterns = [rf"\${re.escape(base)}\b", rf"\((?:nasdaq|nyse|amex|otc)\s*:\s*{re.escape(base)}\)"]
        if is_crypto(sym):
            patterns.append(rf"\b{re.escape(base)}\b")
            patterns.append(rf"\b{re.escape(base)}[-/]?usd\b")
        else:
            patterns.append(rf"\b{re.escape(base)}\b(?=[^a-z]*(?:stock|shares|earnings|upgrade|downgrade|price target))")
        hit = any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)
        if not hit:
            for name in names.get(sym, ()):
                if re.search(rf"\b{re.escape(name.lower())}\b", lower):
                    hit = True
                    break
        if hit and sym not in found:
            found.append(sym)
    return tuple(found)


class NewsFetcher:
    def __init__(self, settings: Settings, universe: Iterable[str] | None = None, session: requests.Session | None = None):
        self.settings = settings
        self.universe = tuple(universe) if universe is not None else settings.all_symbols
        self.session = session or requests.Session()
        self._alpaca_client = None

    # --------------------------------------------------------------- alpaca
    def _alpaca(self):
        if self._alpaca_client is None:
            from alpaca.data.historical.news import NewsClient
            self._alpaca_client = NewsClient(self.settings.alpaca_api_key or None, self.settings.alpaca_secret_key or None)
        return self._alpaca_client

    def fetch_alpaca(self, since: datetime, limit: int = 50) -> list[NewsItem]:
        if not self.settings.alpaca_api_key:
            return []
        from alpaca.data.requests import NewsRequest
        items: list[NewsItem] = []
        try:
            req = NewsRequest(symbols=",".join(self.universe), start=since, limit=limit, include_content=False)
            res = self._alpaca().get_news(req)
            raw_items = getattr(res, "news", None) or getattr(res, "data", {}).get("news", [])
        except Exception as e:
            log.warning("alpaca news fetch failed: %s", e)
            return []
        for n in raw_items:
            get = (lambda k, d=None: n.get(k, d)) if isinstance(n, dict) else (lambda k, d=None: getattr(n, k, d))
            published = get("created_at") or get("updated_at")
            if isinstance(published, str):
                published = from_iso(published.replace("Z", "+00:00"))
            if published is None:
                published = utcnow()
            syms = tuple(s for s in (get("symbols") or []) if s in self.universe)
            # Alpaca lists crypto news under e.g. BTCUSD
            for s in (get("symbols") or []):
                for u in self.universe:
                    if is_crypto(u) and s.replace("/", "") == u.replace("/", "") and u not in syms:
                        syms = syms + (u,)
            headline = str(get("headline") or "")
            items.append(NewsItem(
                id=f"alpaca:{get('id')}", headline=headline, summary=str(get("summary") or ""),
                source=str(get("source") or "alpaca"), url=str(get("url") or ""), published_at=published,
                symbols=syms or extract_symbols(headline, self.universe),
            ))
        return items

    # ------------------------------------------------------------------ rss
    def fetch_rss(self, urls: Iterable[str] | None = None, since: datetime | None = None) -> list[NewsItem]:
        items: list[NewsItem] = []
        for url in (urls if urls is not None else self.settings.news_rss_feeds):
            try:
                resp = self.session.get(url, timeout=15, headers={"User-Agent": "tradesys/0.1"})
                resp.raise_for_status()
                parsed = feedparser.parse(resp.content)
            except Exception as e:
                log.warning("rss fetch failed for %s: %s", url, e)
                continue
            feed_title = str(getattr(parsed.feed, "title", "") or url)
            for entry in parsed.entries:
                published = utcnow()
                for key in ("published_parsed", "updated_parsed"):
                    val = getattr(entry, key, None)
                    if val:
                        published = datetime.fromtimestamp(time.mktime(val) - time.timezone, tz=UTC)
                        break
                if since and published < since:
                    continue
                headline = str(getattr(entry, "title", "") or "")
                summary = re.sub(r"<[^>]+>", " ", str(getattr(entry, "summary", "") or ""))[:500]
                link = str(getattr(entry, "link", "") or "")
                syms = extract_symbols(f"{headline} {summary}", self.universe)
                if not syms:
                    continue
                items.append(NewsItem(id=f"rss:{_stable_id(link or headline)}", headline=headline, summary=summary,
                                      source=feed_title, url=link, published_at=published, symbols=syms))
        return items

    # -------------------------------------------------------------- newsapi
    def fetch_newsapi(self, since: datetime) -> list[NewsItem]:
        if not self.settings.news_api_key:
            return []
        items: list[NewsItem] = []
        terms = []
        for sym in self.universe:
            names = COMPANY_NAMES.get(sym, ())
            terms.append(f'"{names[0]}"' if names else sym.split("/")[0])
        query = " OR ".join(terms[:20])
        try:
            resp = self.session.get(
                "https://newsapi.org/v2/everything",
                params={"q": query, "from": since.isoformat(), "language": "en", "sortBy": "publishedAt",
                        "pageSize": 100, "apiKey": self.settings.news_api_key},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("newsapi fetch failed: %s", e)
            return []
        for art in data.get("articles", []):
            headline = art.get("title") or ""
            summary = art.get("description") or ""
            syms = extract_symbols(f"{headline} {summary}", self.universe)
            if not syms:
                continue
            published = from_iso((art.get("publishedAt") or "").replace("Z", "+00:00")) or utcnow()
            items.append(NewsItem(id=f"newsapi:{_stable_id(art.get('url') or headline)}", headline=headline,
                                  summary=summary, source=(art.get("source") or {}).get("name", "newsapi"),
                                  url=art.get("url") or "", published_at=published, symbols=syms))
        return items

    # ------------------------------------------------------------------ all
    def fetch(self, since: datetime | None = None) -> list[NewsItem]:
        since = since or (utcnow() - timedelta(hours=24))
        items = self.fetch_alpaca(since) + self.fetch_rss(since=since) + self.fetch_newsapi(since)
        seen: set[str] = set()
        out: list[NewsItem] = []
        for it in items:
            key = it.url or it.id
            if key in seen or not it.symbols:
                continue
            seen.add(key)
            out.append(it)
        return out
