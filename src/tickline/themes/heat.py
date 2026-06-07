"""Theme heat engine — two thermometers per theme.

MARKET thermometer (the spine, free + reliable from price/volume):
  rel_strength  basket cumulative return minus benchmark, over lookback
  breadth       fraction of constituents trading above their 50d SMA
  vol_thrust    mean(constituent volume / 20d avg volume) - 1
  flow          ETF shares-outstanding % change over lookback (or None)

RETAIL thermometer (best-effort, degradable — None when no feed):
  retail_level  normalized recent attention (sentiment message volume)
  retail_slope  change in attention over the slope window

Everything is expressed as *level + slope* in interpretable units so the
state machine can use pre-registered thresholds instead of curve-fit
magic numbers. This module is pure (no network) so it unit-tests on
synthetic frames; the driver supplies fetched data and ETF shares.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .taxonomy import Theme


@dataclass(frozen=True)
class HeatConfig:
    lookback: int = 63       # bars for relative strength
    slope_window: int = 10   # bars over which to measure acceleration
    breadth_ma: int = 50     # SMA length for breadth
    vol_window: int = 20     # avg-volume window for thrust

    @property
    def min_bars(self) -> int:
        return self.lookback + self.slope_window + 5


# Two-tier presets for opportunistic trading.
FAST = HeatConfig(lookback=21, slope_window=5, breadth_ma=20, vol_window=10)   # swing / alpha
SLOW = HeatConfig(lookback=63, slope_window=10, breadth_ma=50, vol_window=20)  # position / confirm


@dataclass(frozen=True)
class HeatComponents:
    rel_strength: float
    breadth: float
    vol_thrust: float
    flow: float | None


@dataclass(frozen=True)
class ThemeHeat:
    key: str
    label: str
    as_of: pd.Timestamp
    market_level: float            # relative-strength spread (primary, for display)
    market_slope: float            # raw change in rel-strength over slope window (display)
    market_slope_z: float          # slope normalized to the theme's own slope history
    retail_level: float | None
    retail_slope: float | None
    components: HeatComponents
    n_constituents: int


def _returns(frame: pd.DataFrame) -> pd.Series:
    return frame["close"].pct_change()


def basket_returns(frames: dict[str, pd.DataFrame], tickers: tuple[str, ...]) -> pd.Series:
    """Equal-weight daily return series across the constituents present."""
    cols = [_returns(frames[t]).rename(t) for t in tickers if t in frames]
    if not cols:
        return pd.Series(dtype=float)
    mat = pd.concat(cols, axis=1)
    return mat.mean(axis=1, skipna=True).dropna()


def _rolling_cum_return(ret: pd.Series, window: int) -> pd.Series:
    """Cumulative return over a trailing window, as a daily series."""
    return ret.rolling(window).apply(lambda x: (1.0 + x).prod() - 1.0, raw=True)


def rel_strength_series(
    basket_ret: pd.Series, bench_ret: pd.Series, lookback: int
) -> pd.Series:
    """Basket trailing return minus benchmark trailing return, per bar."""
    idx = basket_ret.index.intersection(bench_ret.index)
    b = _rolling_cum_return(basket_ret.reindex(idx), lookback)
    m = _rolling_cum_return(bench_ret.reindex(idx), lookback)
    return (b - m).dropna()


def _breadth(frames: dict[str, pd.DataFrame], tickers: tuple[str, ...], ma: int) -> float:
    above = 0
    counted = 0
    for t in tickers:
        f = frames.get(t)
        if f is None or len(f) < ma:
            continue
        sma = f["close"].rolling(ma).mean().iloc[-1]
        if pd.notna(sma):
            counted += 1
            above += int(f["close"].iloc[-1] > sma)
    return above / counted if counted else 0.0


def _vol_thrust(frames: dict[str, pd.DataFrame], tickers: tuple[str, ...], window: int) -> float:
    ratios = []
    for t in tickers:
        f = frames.get(t)
        if f is None or len(f) < window + 1:
            continue
        avg = f["volume"].iloc[-window:].mean()
        if avg > 0:
            ratios.append(f["volume"].iloc[-1] / avg)
    if not ratios:
        return 0.0
    return sum(ratios) / len(ratios) - 1.0


def _flow(etf_shares: pd.Series | None, lookback: int) -> float | None:
    """ETF shares-outstanding % change over the lookback (creation/redemption)."""
    if etf_shares is None or len(etf_shares) < 2:
        return None
    recent = etf_shares.iloc[-1]
    window = etf_shares[etf_shares.index >= etf_shares.index[-1] - pd.Timedelta(days=lookback * 2)]
    base = window.iloc[0] if len(window) else etf_shares.iloc[0]
    if base <= 0:
        return None
    return float(recent / base - 1.0)


def _retail_level_slope(
    retail_series: pd.Series | None, slope_window: int
) -> tuple[float | None, float | None]:
    """Normalize attention to its own recent history; return (level, slope).

    level: latest attention as a z-score vs its trailing mean/std.
    slope: change in that z-score over the slope window.
    """
    if retail_series is None or len(retail_series) < slope_window + 5:
        return None, None
    s = retail_series.astype(float)
    mean = s.rolling(slope_window * 3, min_periods=3).mean()
    std = s.rolling(slope_window * 3, min_periods=3).std().replace(0.0, pd.NA)
    z = ((s - mean) / std).fillna(0.0)
    level = float(z.iloc[-1])
    slope = float(z.iloc[-1] - z.iloc[-1 - slope_window])
    return level, slope


def compute_theme_heat(
    theme: Theme,
    frames: dict[str, pd.DataFrame],
    bench_ret: pd.Series,
    cfg: HeatConfig,
    retail_series: pd.Series | None = None,
    etf_shares: pd.Series | None = None,
) -> ThemeHeat | None:
    """Compute both thermometers for one theme. None if too little data."""
    b_ret = basket_returns(frames, theme.tickers)
    n = sum(1 for t in theme.tickers if t in frames)
    if b_ret.empty or n == 0:
        return None

    rs = rel_strength_series(b_ret, bench_ret, cfg.lookback)
    if len(rs) < cfg.slope_window + 1:
        return None

    market_level = float(rs.iloc[-1])
    market_slope = float(rs.iloc[-1] - rs.iloc[-1 - cfg.slope_window])

    # Normalize slope against the theme's OWN slope history so a single,
    # tier-agnostic threshold means "accelerating unusually fast for this
    # theme" — N-day cumulative rel-strength scales with N, so raw slopes
    # are not comparable across the fast/slow tiers. z-score fixes that.
    slope_hist = rs.diff(cfg.slope_window).dropna()
    slope_std = float(slope_hist.std()) if len(slope_hist) > 5 else 0.0
    market_slope_z = market_slope / slope_std if slope_std > 0 else 0.0

    retail_level, retail_slope = _retail_level_slope(retail_series, cfg.slope_window)

    components = HeatComponents(
        rel_strength=market_level,
        breadth=_breadth(frames, theme.tickers, cfg.breadth_ma),
        vol_thrust=_vol_thrust(frames, theme.tickers, cfg.vol_window),
        flow=_flow(etf_shares, cfg.lookback),
    )

    as_of = max(frames[t].index[-1] for t in theme.tickers if t in frames)
    return ThemeHeat(
        key=theme.key,
        label=theme.label,
        as_of=as_of,
        market_level=market_level,
        market_slope=market_slope,
        market_slope_z=market_slope_z,
        retail_level=retail_level,
        retail_slope=retail_slope,
        components=components,
        n_constituents=n,
    )
