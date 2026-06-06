"""Live retail-attention ingesters (free, best-effort, degradable).

Feeds the existing SentimentFeed / build_sentiment_features pipeline.

Sources, in order of usefulness for a *daily history*:
  - Google News RSS: items carry pubDate, so one request yields a short
    per-day attention series — the closest thing to free retail history.
  - StockTwits: ~30 most-recent messages per symbol with Bullish/Bearish
    tags. A point-in-time snapshot (no history depth) used for tone, not
    slope. Accumulate daily via the scheduled agent to build history.

Every fetch is wrapped: network failure returns an empty list so the
market thermometer never blocks on the crowd thermometer.
"""

from __future__ import annotations

import json
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree

import pandas as pd
import requests

from .feed import SentimentEvent, SentimentFeed
from .lexicon import LexiconScorer

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) tickline-watchlist/0.1"
_TIMEOUT = 10


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA})
    return s


def fetch_news(
    query: str,
    symbol: str | None = None,
    scorer: LexiconScorer | None = None,
    session: requests.Session | None = None,
) -> list[SentimentEvent]:
    """Google News RSS headlines for a query. Empty list on any failure."""
    scorer = scorer or LexiconScorer()
    sess = session or _session()
    url = (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        resp = sess.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        root = ElementTree.fromstring(resp.content)
    except (requests.RequestException, ElementTree.ParseError) as exc:
        print(f"  [news] {query!r}: {exc} — skipped")
        return []

    events: list[SentimentEvent] = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        pub = item.findtext("pubDate")
        if not title or not pub:
            continue
        try:
            ts = pd.Timestamp(parsedate_to_datetime(pub)).tz_convert("UTC")
        except (TypeError, ValueError):
            continue
        events.append(
            SentimentEvent(
                ts=ts, source="news", text=title, score=scorer.score(title), symbol=symbol
            )
        )
    return events


def fetch_stocktwits(
    symbol: str, session: requests.Session | None = None
) -> list[SentimentEvent]:
    """StockTwits recent messages for a symbol. Empty list on any failure."""
    sess = session or _session()
    url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
    try:
        resp = sess.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as exc:
        print(f"  [stocktwits] {symbol}: {exc} — skipped")
        return []

    events: list[SentimentEvent] = []
    for msg in data.get("messages", []):
        created = msg.get("created_at")
        body = (msg.get("body") or "").strip()
        if not created or not body:
            continue
        try:
            ts = pd.Timestamp(created).tz_convert("UTC")
        except (TypeError, ValueError):
            continue
        basic = ((msg.get("entities") or {}).get("sentiment") or {}).get("basic")
        score = {"Bullish": 1.0, "Bearish": -1.0}.get(basic, 0.0)
        events.append(
            SentimentEvent(ts=ts, source="stocktwits", text=body, score=score, symbol=symbol)
        )
    return events


def build_theme_feed(
    query_terms: tuple[str, ...],
    tickers: tuple[str, ...] = (),
    use_stocktwits: bool = True,
    session: requests.Session | None = None,
) -> SentimentFeed:
    """Aggregate news (per term) + StockTwits (per ticker) into one feed."""
    sess = session or _session()
    feed = SentimentFeed()
    for term in query_terms:
        for ev in fetch_news(term, session=sess):
            feed.add(ev)
    if use_stocktwits:
        for sym in tickers:
            for ev in fetch_stocktwits(sym, session=sess):
                feed.add(ev)
    return feed


def retail_attention_series(feed: SentimentFeed, freq: str = "D") -> pd.Series:
    """Daily attention = message count per period. Empty Series if no events.

    Attention *volume* (how loud the crowd is) is the level the state
    machine reads; tone matters less for the crowd thermometer.
    """
    if len(feed) == 0:
        return pd.Series(dtype=float)
    ts = pd.DatetimeIndex([e.ts for e in feed.events], tz="UTC").sort_values()
    counts = pd.Series(1, index=ts).resample(freq).sum()
    return counts.asfreq(freq, fill_value=0).astype(float)
