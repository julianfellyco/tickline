"""Tests for the sentiment layer."""

from __future__ import annotations

import pandas as pd
import pytest

from tickline.sentiment import (
    LexiconScorer,
    SentimentEvent,
    SentimentFeed,
    build_sentiment_features,
    score_text,
)


def test_lexicon_positive_score():
    s = score_text("Massive rally — BTC breakout to a new ATH, strong adoption")
    assert s > 0.5


def test_lexicon_negative_score():
    s = score_text("Brutal crash, plunge continues, panic selling, lawsuit fears")
    assert s < -0.5


def test_lexicon_neutral_score():
    assert score_text("") == 0.0
    assert abs(score_text("the market opened today and traded sideways")) < 0.1


def test_lexicon_breakdown():
    breakdown = LexiconScorer().breakdown("Rally and breakout — sec investigation lingers")
    assert "rally" in breakdown["pos"]
    assert "breakout" in breakdown["pos"]
    assert "sec" in breakdown["neg"] or "investigation" in breakdown["neg"]


def test_feed_roundtrip(tmp_path):
    feed = SentimentFeed()
    feed.add(SentimentEvent(
        ts=pd.Timestamp("2025-01-01", tz="UTC"),
        source="news",
        text="BTC breaks out",
        score=0.8,
        symbol="BTC",
    ))
    feed.add(SentimentEvent(
        ts=pd.Timestamp("2025-01-02", tz="UTC"),
        source="news",
        text="ETH crash",
        score=-0.6,
        symbol="ETH",
    ))
    path = tmp_path / "feed.jsonl"
    feed.to_jsonl(path)
    loaded = SentimentFeed.from_jsonl(path)
    assert len(loaded) == 2
    assert loaded.events[0].symbol == "BTC"
    assert loaded.events[1].score == pytest.approx(-0.6)


def test_feed_filters_by_symbol():
    feed = SentimentFeed()
    feed.add(SentimentEvent(pd.Timestamp("2025-01-01", tz="UTC"), "news", "x", 0.5, "BTC"))
    feed.add(SentimentEvent(pd.Timestamp("2025-01-02", tz="UTC"), "news", "y", -0.3, "ETH"))
    feed.add(SentimentEvent(pd.Timestamp("2025-01-03", tz="UTC"), "news", "z", 0.7, None))

    s_btc = feed.to_series("BTC")
    assert len(s_btc) == 2  # BTC-specific + general


def test_build_features_on_empty_feed():
    idx = pd.date_range("2025-01-01", periods=20, freq="1h", tz="UTC")
    feats = build_sentiment_features(SentimentFeed(), idx, window_bars=10)
    assert (feats["sentiment_count_10"] == 0).all()
    assert (feats["sentiment_mean_10"] == 0.0).all()


def test_build_features_with_events():
    idx = pd.date_range("2025-01-01", periods=48, freq="1h", tz="UTC")
    feed = SentimentFeed()
    feed.add(SentimentEvent(idx[5], "news", "bullish ATH rally", 0.9, None))
    feed.add(SentimentEvent(idx[10], "news", "crash plunge dump", -0.9, None))
    feed.add(SentimentEvent(idx[20], "news", "neutral update", 0.0, None))

    feats = build_sentiment_features(feed, idx, window_bars=12)
    # before any event, count is 0
    assert feats["sentiment_count_12"].iloc[0] == 0
    # after first event, count >= 1
    assert feats["sentiment_count_12"].iloc[6] >= 1
    # last event score forward-fills
    assert feats["sentiment_last"].iloc[15] == pytest.approx(-0.9)
    # age increases between events
    assert feats["sentiment_age_bars"].iloc[15] > feats["sentiment_age_bars"].iloc[11]
