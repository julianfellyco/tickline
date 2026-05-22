"""Sentiment event feed.

`SentimentEvent` is a single timestamped data point: a headline, a
tweet, an on-chain event. `SentimentFeed` is a collection of events
loadable from CSV / JSONL and emittable as a sentiment time series.

Production sources you'd plug in:
  - NewsAPI / GDELT (headlines)
  - X/Twitter API (tweets)
  - Reddit (pushshift)
  - Glassnode (on-chain events)
  - Funding rates (sentiment proxy)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .lexicon import LexiconScorer


@dataclass(frozen=True)
class SentimentEvent:
    ts: pd.Timestamp
    source: str             # 'news', 'twitter', 'reddit', 'onchain', etc.
    text: str
    score: float            # in [-1, 1]
    symbol: str | None = None  # 'BTC', 'ETH', or None for general market

    @classmethod
    def from_dict(cls, d: dict, scorer: LexiconScorer | None = None) -> "SentimentEvent":
        ts = pd.Timestamp(d["ts"], tz="UTC")
        text = d.get("text", "")
        if "score" in d:
            score = float(d["score"])
        else:
            score = (scorer or LexiconScorer()).score(text)
        return cls(
            ts=ts,
            source=d.get("source", "unknown"),
            text=text,
            score=score,
            symbol=d.get("symbol"),
        )

    def to_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(),
            "source": self.source,
            "text": self.text,
            "score": self.score,
            "symbol": self.symbol,
        }


@dataclass
class SentimentFeed:
    events: list[SentimentEvent] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.events)

    def add(self, event: SentimentEvent) -> None:
        self.events.append(event)

    def to_series(self, symbol: str | None = None) -> pd.Series:
        """Return scores as a UTC-indexed pandas Series."""
        filtered = [
            e for e in self.events
            if symbol is None or e.symbol is None or e.symbol == symbol
        ]
        if not filtered:
            return pd.Series(dtype=float, name="sentiment")
        ts = [e.ts for e in filtered]
        scores = [e.score for e in filtered]
        s = pd.Series(scores, index=pd.DatetimeIndex(ts, tz="UTC"), name="sentiment")
        return s.sort_index()

    @classmethod
    def from_jsonl(cls, path: str | Path, scorer: LexiconScorer | None = None) -> "SentimentFeed":
        feed = cls()
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                feed.add(SentimentEvent.from_dict(json.loads(line), scorer))
        return feed

    def to_jsonl(self, path: str | Path) -> None:
        with open(path, "w") as f:
            for e in self.events:
                f.write(json.dumps(e.to_dict()) + "\n")
