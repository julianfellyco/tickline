#!/usr/bin/env python3
"""Fetch OHLCV data from a ccxt exchange and cache it locally."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.data import fetch_ohlcv


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch OHLCV candles")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h", choices=["1m", "5m", "15m", "1h", "4h", "1d"])
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    args = p.parse_args()

    print(f"Fetching {args.symbol} {args.timeframe} from {args.exchange} ({args.days}d)...")
    df = fetch_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        days=args.days,
        exchange=args.exchange,
    )
    print(f"\n{len(df)} candles from {df.index[0]} to {df.index[-1]}")
    print(df.tail())
    return 0


if __name__ == "__main__":
    sys.exit(main())
