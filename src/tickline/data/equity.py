"""US equity / ETF data fetcher.

Mirrors the contract of `fetcher.py` (ccxt/crypto) but sources from
yfinance, so the rest of the framework — strategies, backtester,
portfolio, dashboard — operates on US stocks and ETFs unchanged.

Output schema is identical to `fetcher.fetch_ohlcv`:
  columns = [open, high, low, close, volume], UTC DatetimeIndex.

Data is cached to the same `data/` directory as Parquet. Daily bars are
small, so re-fetches pull the full window and merge (dedupe on index)
rather than doing ccxt-style incremental paging.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OHLCV_COLS = ["open", "high", "low", "close", "volume"]

# yfinance `period` strings we accept; daily/weekly bars only (free, reliable).
_VALID_INTERVALS = {"1d", "1wk", "1mo"}


def _cache_path(symbol: str, interval: str) -> Path:
    safe = symbol.replace("/", "-").replace("^", "_").lower()
    return DATA_DIR / f"yf_{safe}_{interval}.parquet"


def load_cached(symbol: str, interval: str = "1d") -> pd.DataFrame:
    """Load cached bars. Returns an empty OHLCV frame if no cache exists."""
    path = _cache_path(symbol, interval)
    if not path.exists():
        return pd.DataFrame(columns=OHLCV_COLS)
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index, utc=True)
    return df


def _normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Map a yfinance history frame to the canonical OHLCV schema."""
    if raw.empty:
        return pd.DataFrame(columns=OHLCV_COLS)
    df = raw.rename(columns={c: c.lower() for c in raw.columns})
    df = df[[c for c in OHLCV_COLS if c in df.columns]].copy()
    # yfinance daily index is tz-naive or exchange-local; force UTC midnight.
    idx = pd.to_datetime(df.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df.index = idx
    df.index.name = "timestamp"
    return df.dropna(how="all").sort_index()


def fetch_equity(
    symbol: str,
    days: int = 400,
    interval: str = "1d",
    use_cache: bool = True,
) -> pd.DataFrame:
    """Fetch daily OHLCV for a US equity or ETF, caching to disk.

    Args:
        symbol: Yahoo ticker, e.g. "NVDA", "SMH", "^GSPC".
        days: how many calendar days of history to return.
        interval: "1d" (default), "1wk", or "1mo".
        use_cache: merge with and refresh the on-disk Parquet cache.

    Returns:
        OHLCV DataFrame in canonical schema, trimmed to the last `days`.
    """
    if interval not in _VALID_INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}")

    import yfinance as yf  # local import: keeps crypto path dependency-free

    # over-fetch a little so moving averages have warm-up room
    period_days = max(days + 60, 90)
    raw = yf.Ticker(symbol).history(
        period=f"{period_days}d", interval=interval, auto_adjust=True
    )
    fresh = _normalize(raw)

    if use_cache:
        cached = load_cached(symbol, interval)
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        if not combined.empty:
            combined.to_parquet(_cache_path(symbol, interval))
    else:
        combined = fresh

    if combined.empty:
        return combined
    cutoff = combined.index.max() - pd.Timedelta(days=days)
    return combined[combined.index >= cutoff]


def fetch_many(
    symbols: list[str],
    days: int = 400,
    interval: str = "1d",
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Fetch several symbols. Failures are skipped (logged), never fatal.

    Free data is flaky; one delisted/renamed ticker must not sink a run.
    """
    out: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        try:
            df = fetch_equity(sym, days=days, interval=interval, use_cache=use_cache)
            if df.empty:
                print(f"  [equity] {sym}: no data returned — skipped")
                continue
            out[sym] = df
        except Exception as exc:  # noqa: BLE001 — degrade, don't crash the run
            print(f"  [equity] {sym}: fetch failed ({exc}) — skipped")
    return out


def fetch_shares_outstanding(symbol: str, days: int = 400) -> pd.Series | None:
    """Best-effort shares-outstanding history for an ETF (flow proxy).

    ETF creation/redemption shows up as a change in shares outstanding —
    a clean institutional-flow signal. Returns None if unavailable so
    callers degrade gracefully to price/volume-only flow.
    """
    try:
        import yfinance as yf

        start = (pd.Timestamp.utcnow() - pd.Timedelta(days=days)).date().isoformat()
        shares = yf.Ticker(symbol).get_shares_full(start=start)
        if shares is None or len(shares) == 0:
            return None
        s = pd.Series(shares)
        s.index = pd.to_datetime(s.index, utc=True)
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception as exc:  # noqa: BLE001
        print(f"  [equity] {symbol}: shares-outstanding unavailable ({exc})")
        return None
