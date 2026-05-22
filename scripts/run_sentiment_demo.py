#!/usr/bin/env python3
"""Sentiment layer demo.

Generates a synthetic event feed (or loads one from JSONL), projects
it onto an OHLCV bar index, and reports the correlation between each
sentiment feature and the *forward* return of the next N bars.

If a real news feed is plugged in (NewsAPI, X firehose, on-chain), the
shape of the output stays identical — only the source changes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from tickline.data import fetch_ohlcv, load_cached
from tickline.sentiment import (
    SentimentEvent,
    SentimentFeed,
    build_sentiment_features,
    score_text,
)

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}sentiment{INK}                       │
   │  {INK_FAINT}news → bar features → forward returns{INK}    │
   └─────────────────────────────────────────┘{RESET}
"""

# Synthetic feed for demo purposes — real use would plug in a NewsAPI / X feed.
_SYNTHETIC = [
    ("2025-05-22 12:00:00", "news", "BTC rally continues as ETF inflows hit ATH"),
    ("2025-06-05 09:30:00", "news", "Regulatory crackdown announced; SEC investigation underway"),
    ("2025-06-18 15:00:00", "news", "Major exchange hack drains liquidity, panic selling"),
    ("2025-07-02 11:00:00", "news", "Bullish breakout, partnership upgrade announced"),
    ("2025-07-15 14:30:00", "news", "Lawsuit and contagion fears spread across the market"),
    ("2025-08-01 10:00:00", "news", "Strong adoption metrics, mainnet milestone reached"),
    ("2025-08-20 16:00:00", "news", "Plunge accelerates, liquidations cascade"),
    ("2025-09-05 12:30:00", "news", "Bullish recovery; institutional accumulation strong"),
    ("2025-09-22 13:00:00", "news", "Bearish dump; weak support levels broken"),
    ("2025-10-10 11:30:00", "news", "ATH approached; rally and momentum building"),
    ("2025-11-01 09:00:00", "news", "Crash and bankruptcy fears as major exchange halts withdrawals"),
    ("2025-11-20 15:30:00", "news", "Breakthrough innovation drives bullish optimism"),
    ("2025-12-08 14:00:00", "news", "Sec ban on tokens triggers fud and sell-off"),
    ("2026-01-05 10:30:00", "news", "Etf approval announcement, breakout above resistance"),
    ("2026-01-25 12:00:00", "news", "Plunge after lawsuit filed against major firm"),
    ("2026-02-15 13:30:00", "news", "Rally and recovery; bullish accumulation visible"),
    ("2026-03-08 11:00:00", "news", "Bear market deepens, panic and fear dominate"),
    ("2026-03-28 16:00:00", "news", "Strong ETF inflows, growth surges"),
    ("2026-04-18 09:30:00", "news", "Crash and dump after sec investigation reveal"),
    ("2026-05-05 14:00:00", "news", "Bullish breakout, ATH set"),
]


def _synthetic_feed() -> SentimentFeed:
    feed = SentimentFeed()
    for ts_str, source, text in _SYNTHETIC:
        ts = pd.Timestamp(ts_str, tz="UTC")
        feed.add(SentimentEvent(ts=ts, source=source, text=text, score=score_text(text)))
    return feed


def main() -> int:
    p = argparse.ArgumentParser(description="Sentiment layer demo")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--forward-bars", type=int, default=12, help="forward return horizon")
    p.add_argument("--window", type=int, default=24, help="sentiment rolling window in bars")
    p.add_argument("--feed", default=None, help="optional JSONL sentiment feed")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    print(BANNER)
    if args.no_fetch:
        df = load_cached(args.exchange, args.symbol, args.timeframe)
    else:
        df = fetch_ohlcv(args.symbol, args.timeframe, 365, args.exchange)
    if df.empty:
        print("no data")
        return 1
    print(f"{INK_FAINT}>>{RESET} {len(df)} bars from {df.index[0].date()} to {df.index[-1].date()}")

    if args.feed:
        feed = SentimentFeed.from_jsonl(args.feed)
        print(f"{INK_FAINT}>>{RESET} loaded {len(feed)} events from {args.feed}")
    else:
        feed = _synthetic_feed()
        print(f"{INK_FAINT}>>{RESET} generated {len(feed)} synthetic events")

    print(f"\n{INK}Sample events:{RESET}")
    for e in feed.events[:5]:
        color = SIGNAL if e.score > 0.2 else (ALERT if e.score < -0.2 else AMBER)
        print(f"   {INK_FAINT}{e.ts.strftime('%Y-%m-%d')}{RESET}  {color}{e.score:+.2f}{RESET}  {INK_DIM}{e.text[:64]}{RESET}")
    print(f"   {INK_FAINT}...{RESET}\n")

    feats = build_sentiment_features(feed, df.index, window_bars=args.window)
    print(f"{INK}Bar-level features built ({feats.shape[1]} columns, {len(feats)} rows):{RESET}")
    for col in feats.columns:
        print(f"   {INK_FAINT}{col}{RESET}")
    print()

    # forward return as the target
    fwd_ret = df["close"].pct_change(args.forward_bars).shift(-args.forward_bars)
    print(f"{INK}Correlation of sentiment feature → forward {args.forward_bars}-bar return:{RESET}")
    for col in feats.columns:
        feat_series = feats[col].replace([np.inf, -np.inf], np.nan)
        valid = feat_series.notna() & fwd_ret.notna()
        if valid.sum() < 50:
            continue
        corr = float(feat_series[valid].corr(fwd_ret[valid]))
        magnitude = abs(corr)
        bar = "█" * min(20, int(magnitude * 200))
        sign_color = SIGNAL if corr > 0 else (ALERT if corr < 0 else INK_DIM)
        print(f"   {INK}{col:<24}{RESET} {sign_color}{bar:<20}{RESET}  {sign_color}{corr:+.4f}{RESET}")
    print()
    print(f"{INK_FAINT}note: these are correlations on a synthetic feed against real BTC returns.{RESET}")
    print(f"{INK_FAINT}      a real feed would join NewsAPI / X / on-chain data the same way.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
