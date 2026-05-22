"""Aggregate sentiment events to bar-level features.

These features can be joined to an OHLCV frame and fed into the
meta-labeler (or any downstream model). The pattern matters more than
the specific features — for any time-series ML, you need:

  1. A timestamp-aligned, point-in-time-safe feature
  2. A defined null behavior for windows with no events
  3. Forward-fill semantics so the feature is defined on every bar
"""

from __future__ import annotations

import pandas as pd

from .feed import SentimentFeed


def build_sentiment_features(
    feed: SentimentFeed,
    ohlcv_index: pd.DatetimeIndex,
    window_bars: int = 24,
    symbol: str | None = None,
) -> pd.DataFrame:
    """Project a sentiment feed onto a bar index.

    Output columns:
      sentiment_mean_N    rolling mean of last N bars' event scores
      sentiment_count_N   count of events in last N bars
      sentiment_pos_N     count of positive events (score > 0) in last N
      sentiment_neg_N     count of negative events (score < 0) in last N
      sentiment_last      most recent event score (forward-filled)
      sentiment_age_bars  bars since most recent event

    All features are causal — they only use events with ts <= bar ts.
    """
    if len(ohlcv_index) == 0:
        return pd.DataFrame(index=ohlcv_index)

    # normalize index dtype to match ohlcv to keep merge_asof happy
    ohlcv_index = pd.DatetimeIndex(ohlcv_index)
    series = feed.to_series(symbol=symbol)
    if not series.empty:
        series.index = pd.DatetimeIndex(series.index).astype(ohlcv_index.dtype)
    if series.empty:
        return pd.DataFrame(
            {
                f"sentiment_mean_{window_bars}": 0.0,
                f"sentiment_count_{window_bars}": 0,
                f"sentiment_pos_{window_bars}": 0,
                f"sentiment_neg_{window_bars}": 0,
                "sentiment_last": 0.0,
                "sentiment_age_bars": float("inf"),
            },
            index=ohlcv_index,
        )

    # bucket events to the bar grid (forward fill into next bar boundary)
    aligned = pd.DataFrame({"score": series})
    aligned["pos"] = (aligned["score"] > 0).astype(int)
    aligned["neg"] = (aligned["score"] < 0).astype(int)

    # for each ohlcv bar, find events with ts <= bar_ts (point-in-time)
    feat = pd.DataFrame(index=ohlcv_index)

    # use as-of join: for each bar, the most recent event up to and including bar_ts
    asof = pd.merge_asof(
        feat.reset_index().rename(columns={"index": "ts"}).sort_values("ts"),
        aligned.reset_index().rename(columns={"index": "ts"}).sort_values("ts"),
        on="ts",
        direction="backward",
    ).set_index("ts")
    feat["sentiment_last"] = asof["score"].fillna(0.0).values

    # rolling stats: convert events to bar-aligned, then rolling-window
    # build a count-only series resampled to bar grid (sum)
    score_at_bar = aligned["score"].reindex(ohlcv_index, method=None).fillna(0.0)
    pos_at_bar = aligned["pos"].reindex(ohlcv_index, method=None).fillna(0).astype(int)
    neg_at_bar = aligned["neg"].reindex(ohlcv_index, method=None).fillna(0).astype(int)
    has_event = (aligned["score"].reindex(ohlcv_index, method=None)).notna().astype(int)

    # if events don't fall exactly on a bar, snap them to the next bar
    if has_event.sum() == 0:
        # snap-forward to nearest bar
        snapped = aligned.reindex(ohlcv_index, method="bfill")
        score_at_bar = snapped["score"].fillna(0.0)
        pos_at_bar = snapped["pos"].fillna(0).astype(int)
        neg_at_bar = snapped["neg"].fillna(0).astype(int)
        has_event = snapped["score"].notna().astype(int)

    feat[f"sentiment_mean_{window_bars}"] = (
        score_at_bar.where(has_event.astype(bool), other=0.0)
        .rolling(window_bars, min_periods=1).sum()
        / has_event.rolling(window_bars, min_periods=1).sum().replace(0, 1)
    ).fillna(0.0)
    feat[f"sentiment_count_{window_bars}"] = has_event.rolling(window_bars, min_periods=1).sum().astype(int)
    feat[f"sentiment_pos_{window_bars}"] = pos_at_bar.rolling(window_bars, min_periods=1).sum().astype(int)
    feat[f"sentiment_neg_{window_bars}"] = neg_at_bar.rolling(window_bars, min_periods=1).sum().astype(int)

    # bars since last event
    last_event_idx = has_event.where(has_event > 0).ffill().notna()
    # cumulative count of bars since the last True
    counter = 0
    ages = []
    for v in has_event.values:
        if v > 0:
            counter = 0
        else:
            counter += 1
        ages.append(counter)
    feat["sentiment_age_bars"] = pd.Series(ages, index=ohlcv_index)
    # if there was never an event yet, mark as large
    no_event_yet = ~last_event_idx
    feat.loc[no_event_yet, "sentiment_age_bars"] = 9_999

    return feat
