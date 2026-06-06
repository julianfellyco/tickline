"""Signal-validation backtest for the theme state machine.

This is an *event study*, not a PnL backtest. It answers one question:

    When a theme enters a bullish state (EMERGING), does its basket
    outperform SPY over the next H days — and does that separate cleanly
    from the bearish state (ROLLING_OVER)?

If the states do not separate forward excess returns, the signal is noise
and no execution layer can save it. We validate the *market-only* states
because only the market thermometer has trustworthy history (retail RSS
is recency-biased and cannot be reconstructed point-in-time).

Anti-self-deception rules baked in:
  - Point-in-time: every signal at date D uses only data <= D. The slope
    z-score uses a TRAILING rolling std (the live code's full-sample std
    would be lookahead here).
  - Forward returns measured D+1..D+H (no overlap with the signal bar).
  - The driver also reports a non-overlapping subsample, because daily
    overlapping windows make any naive t-stat wildly overconfident.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .heat import HeatConfig, basket_returns, rel_strength_series
from .taxonomy import Theme

Z_WINDOW = 126  # ~6 months trailing window for the slope z-score


def basket_index(frames: dict[str, pd.DataFrame], tickers: tuple[str, ...]) -> pd.Series:
    """Cumulative equal-weight index (base 1.0) from constituent returns."""
    br = basket_returns(frames, tickers)
    if br.empty:
        return pd.Series(dtype=float)
    return (1.0 + br).cumprod()


def causal_slope_z(rs: pd.Series, slope_window: int, z_window: int = Z_WINDOW) -> pd.Series:
    """Slope of rel-strength, normalized by a TRAILING rolling std (PIT-safe)."""
    slope = rs.diff(slope_window)
    std = slope.rolling(z_window, min_periods=max(20, z_window // 4)).std()
    return slope / std.replace(0.0, np.nan)


def market_state_series(slope_z: pd.Series, slope_z_rise: float = 0.5) -> pd.Series:
    """Vectorized market-only classification (matches state.classify fallback)."""
    state = np.where(
        slope_z > slope_z_rise,
        "emerging",
        np.where(slope_z < -slope_z_rise, "rolling_over", "dormant"),
    )
    return pd.Series(state, index=slope_z.index, dtype=object)


def forward_excess(b_index: pd.Series, m_index: pd.Series, horizon: int) -> pd.Series:
    """Theme forward return minus benchmark forward return, over `horizon` bars."""
    bf = b_index.shift(-horizon) / b_index - 1.0
    mf = m_index.shift(-horizon) / m_index - 1.0
    idx = bf.index.intersection(mf.index)
    return (bf.reindex(idx) - mf.reindex(idx)).rename(f"fwd_{horizon}")


def build_panel(
    themes: tuple[Theme, ...],
    frames: dict[str, pd.DataFrame],
    bench_ret: pd.Series,
    cfg: HeatConfig,
    horizons: tuple[int, ...],
    z_window: int = Z_WINDOW,
) -> pd.DataFrame:
    """One row per (theme, date): state, signals, and forward excess returns."""
    m_index = (1.0 + bench_ret).cumprod()
    blocks: list[pd.DataFrame] = []
    for theme in themes:
        b_ret = basket_returns(frames, theme.tickers)
        if b_ret.empty:
            continue
        b_index = (1.0 + b_ret).cumprod()
        rs = rel_strength_series(b_ret, bench_ret, cfg.lookback)
        if rs.empty:
            continue
        sz = causal_slope_z(rs, cfg.slope_window, z_window)
        df = pd.DataFrame({"slope_z": sz, "rel_strength": rs})
        df["state"] = market_state_series(sz)
        for h in horizons:
            df[f"fwd_{h}"] = forward_excess(b_index, m_index, h)
        df = df.dropna(subset=["slope_z"])
        if df.empty:
            continue
        df["theme"] = theme.key
        df["date"] = df.index
        blocks.append(df.reset_index(drop=True))
    return pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()


def summarize_by_state(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Per-state forward-excess stats: n, mean, median, hit-rate, std."""
    col = f"fwd_{horizon}"
    g = panel.dropna(subset=[col]).groupby("state")[col]
    return pd.DataFrame(
        {
            "n": g.count(),
            "mean_excess": g.mean(),
            "median_excess": g.median(),
            "hit_rate": g.apply(lambda x: (x > 0).mean()),
            "std": g.std(),
        }
    )


def bull_minus_bear(summary: pd.DataFrame) -> float:
    """EMERGING mean forward excess minus ROLLING_OVER mean — the headline edge."""
    e = summary.loc["emerging", "mean_excess"] if "emerging" in summary.index else np.nan
    r = summary.loc["rolling_over", "mean_excess"] if "rolling_over" in summary.index else np.nan
    return float(e - r)


def quintile_monotonicity(
    panel: pd.DataFrame, horizon: int, signal: str = "slope_z", q: int = 5
) -> pd.DataFrame:
    """Bucket the signal into quantiles; do forward returns rise monotonically?"""
    col = f"fwd_{horizon}"
    d = panel.dropna(subset=[col, signal]).copy()
    if len(d) < q * 2:
        return pd.DataFrame()
    d["bucket"] = pd.qcut(d[signal], q, labels=False, duplicates="drop")
    g = d.groupby("bucket")[col]
    return pd.DataFrame(
        {"n": g.count(), "mean_excess": g.mean(), "hit_rate": g.apply(lambda x: (x > 0).mean())}
    )


def naive_tstat(panel: pd.DataFrame, horizon: int, state: str = "emerging") -> tuple[float, int]:
    """One-sample t-stat that a state's mean forward excess > 0.

    NAIVE: assumes independent samples. Overlapping daily windows violate
    that badly, so this OVERSTATES significance — read it with the
    non-overlapping subsample, never alone.
    """
    col = f"fwd_{horizon}"
    x = panel.loc[panel["state"] == state, col].dropna()
    if len(x) < 2 or x.std() == 0:
        return float("nan"), len(x)
    return float(x.mean() / (x.std() / np.sqrt(len(x)))), len(x)


def non_overlapping(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Subsample every `horizon` bars per theme so forward windows don't overlap."""
    blocks = []
    for _, d in panel.groupby("theme"):
        d = d.sort_values("date").iloc[::horizon]
        blocks.append(d)
    return pd.concat(blocks, ignore_index=True) if blocks else panel


# --- cross-sectional tests (the honest ones) ---------------------------------
# Absolute forward excess vs SPY is swamped by AI-beta: every AI theme beat SPY
# 2020-2026, so EVERY state looks positive. The signal question is RELATIVE —
# among the themes on the SAME day, do the leaders out-rotate the laggards?
# We answer that by demeaning forward excess across themes per date.

def _date_demeaned(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    col = f"fwd_{horizon}"
    p = panel.dropna(subset=[col]).copy()
    p["rel_fwd"] = p[col] - p.groupby("date")[col].transform("mean")
    return p


def cross_sectional_by_state(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Date-demeaned forward excess grouped by state (AI-beta baseline removed)."""
    p = _date_demeaned(panel, horizon)
    g = p.groupby("state")["rel_fwd"]
    return pd.DataFrame({"n": g.count(), "rel_to_peers": g.mean()})


def cross_sectional_rank_buckets(
    panel: pd.DataFrame, horizon: int, signal: str = "rel_strength", q: int = 5
) -> pd.DataFrame:
    """Rank themes cross-sectionally each day by `signal`; demeaned fwd per bucket.

    A monotone rise from Q1 (weakest) to Q_top (strongest) is the clean
    signature of a real cross-sectional momentum/rotation edge.
    """
    p = _date_demeaned(panel, horizon)

    def _rank(x: pd.Series) -> pd.Series:
        if x.nunique() < q:
            return pd.Series(np.nan, index=x.index)
        return pd.qcut(x.rank(method="first"), q, labels=False, duplicates="drop")

    p["bucket"] = p.groupby("date")[signal].transform(_rank)
    p = p.dropna(subset=["bucket"])
    g = p.groupby("bucket")["rel_fwd"]
    return pd.DataFrame({"n": g.count(), "rel_to_peers": g.mean()})


def long_short_spread(buckets: pd.DataFrame) -> float:
    """Top-bucket minus bottom-bucket demeaned forward return (the rotation edge)."""
    if buckets.empty:
        return float("nan")
    return float(buckets["rel_to_peers"].iloc[-1] - buckets["rel_to_peers"].iloc[0])
