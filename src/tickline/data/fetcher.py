"""Market data fetcher.

Pulls OHLCV candles from any ccxt-supported exchange and caches them
locally as Parquet files. Re-fetches are incremental: we only ask the
exchange for candles newer than what's already on disk.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def _cache_path(exchange: str, symbol: str, timeframe: str) -> Path:
    safe_symbol = symbol.replace("/", "-")
    return DATA_DIR / f"{exchange}_{safe_symbol}_{timeframe}.parquet"


def load_cached(exchange: str, symbol: str, timeframe: str) -> pd.DataFrame:
    """Load cached candles. Returns empty DataFrame if no cache exists."""
    path = _cache_path(exchange, symbol, timeframe)
    if not path.exists():
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def fetch_ohlcv(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    days: int = 365,
    exchange: str = "binance",
    limit_per_request: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV candles, caching to disk.

    Re-running with the same args will only fetch new candles since last run.
    """
    if timeframe not in TIMEFRAME_MS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    ex = getattr(ccxt, exchange)({"enableRateLimit": True})
    ex.load_markets()
    if symbol not in ex.markets:
        raise ValueError(f"{symbol} not listed on {exchange}")

    cached = load_cached(exchange, symbol, timeframe)
    now_ms = int(time.time() * 1000)
    requested_start = now_ms - days * 86_400_000

    if not cached.empty:
        last_ts_ms = int(cached.index[-1].timestamp() * 1000)
        since = max(requested_start, last_ts_ms + TIMEFRAME_MS[timeframe])
    else:
        since = requested_start

    all_rows: list[list[float]] = []
    while since < now_ms:
        try:
            batch = ex.fetch_ohlcv(symbol, timeframe, since=since, limit=limit_per_request)
        except ccxt.NetworkError as exc:
            print(f"  network error: {exc} — retrying in 5s")
            time.sleep(5)
            continue
        if not batch:
            break
        all_rows.extend(batch)
        last_batch_ts = batch[-1][0]
        if last_batch_ts <= since:
            break
        since = last_batch_ts + TIMEFRAME_MS[timeframe]
        print(f"  fetched {len(batch)} candles up to {datetime.fromtimestamp(last_batch_ts/1000, tz=timezone.utc)}")
        time.sleep(ex.rateLimit / 1000)

    if all_rows:
        new_df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        new_df["timestamp"] = pd.to_datetime(new_df["timestamp"], unit="ms", utc=True)
        new_df = new_df.set_index("timestamp")
        combined = pd.concat([cached, new_df])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = cached

    path = _cache_path(exchange, symbol, timeframe)
    combined.to_parquet(path)
    print(f"  saved {len(combined)} total candles to {path.name}")

    cutoff = pd.Timestamp(requested_start, unit="ms", tz="UTC")
    return combined[combined.index >= cutoff]
