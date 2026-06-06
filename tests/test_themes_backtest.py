"""Tests for the theme signal-validation backtest (deterministic, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.themes.backtest import (
    build_panel,
    causal_slope_z,
    cross_sectional_by_state,
    cross_sectional_rank_buckets,
    forward_excess,
    long_short_spread,
    market_state_series,
    non_overlapping,
    summarize_by_state,
)
from tickline.themes.heat import FAST
from tickline.themes.rotation_backtest import (
    benchmark_metrics,
    equal_weight_metrics,
    simulate_long_short,
)
from tickline.themes.taxonomy import Theme


def _series(values, start="2021-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="D", tz="UTC")
    return pd.Series(values, index=idx, dtype=float)


def _frame(daily_return: float, n: int = 400, start_price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
    close = start_price * np.cumprod(np.full(n, 1.0 + daily_return))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1e6},
        index=idx,
    )


# --- forward excess math -----------------------------------------------------
def test_forward_excess_basic():
    b = _series([1.0, 1.1, 1.21, 1.331])   # +10%/bar
    m = _series([1.0, 1.0, 1.0, 1.0])      # flat benchmark
    fe = forward_excess(b, m, horizon=1)
    # at t0: theme +10%, bench 0% -> excess +10%
    assert fe.iloc[0] == pytest.approx(0.10)
    # last bar has no future -> NaN
    assert np.isnan(fe.iloc[-1])


# --- THE critical test: no lookahead -----------------------------------------
def test_causal_slope_z_is_point_in_time():
    rng = np.random.default_rng(42)
    rs = _series(np.cumsum(rng.normal(0, 0.01, 400)))  # random-walk rel-strength
    full = causal_slope_z(rs, slope_window=5, z_window=126)
    # the value at date D must NOT change if data after D never existed
    for d in (150, 250, 399):
        truncated = causal_slope_z(rs.iloc[: d + 1], slope_window=5, z_window=126)
        assert truncated.iloc[-1] == pytest.approx(full.iloc[d], nan_ok=True)


def test_market_state_series_thresholds():
    sz = _series([1.0, -1.0, 0.0, 0.6, -0.6])
    st = market_state_series(sz, slope_z_rise=0.5)
    assert list(st) == ["emerging", "rolling_over", "dormant", "emerging", "rolling_over"]


# --- aggregation plumbing ----------------------------------------------------
def test_summarize_by_state_counts_and_hitrate():
    panel = pd.DataFrame(
        {
            "state": ["emerging", "emerging", "rolling_over", "rolling_over"],
            "fwd_5": [0.02, -0.01, -0.03, 0.01],
            "theme": ["a", "a", "b", "b"],
            "date": pd.date_range("2021-01-01", periods=4, tz="UTC"),
        }
    )
    summ = summarize_by_state(panel, horizon=5)
    assert summ.loc["emerging", "n"] == 2
    assert summ.loc["emerging", "hit_rate"] == pytest.approx(0.5)
    assert summ.loc["emerging", "mean_excess"] == pytest.approx(0.005)


def test_non_overlapping_thins_per_theme():
    panel = pd.DataFrame(
        {
            "theme": ["a"] * 20,
            "date": pd.date_range("2021-01-01", periods=20, tz="UTC"),
            "fwd_5": np.arange(20, dtype=float),
            "state": ["emerging"] * 20,
        }
    )
    thinned = non_overlapping(panel, horizon=5)
    assert len(thinned) == 4  # every 5th row of 20


# --- integration on synthetic frames -----------------------------------------
def test_cross_sectional_by_state_demeans_per_date():
    dates = pd.to_datetime(["2021-01-01", "2021-01-02"], utc=True)
    panel = pd.DataFrame(
        {
            "theme": ["a", "b", "a", "b"],
            "date": [dates[0], dates[0], dates[1], dates[1]],
            "state": ["emerging", "rolling_over", "emerging", "rolling_over"],
            "rel_strength": [0.2, -0.1, 0.2, -0.1],
            "fwd_5": [0.05, 0.01, 0.03, -0.01],
        }
    )
    xs = cross_sectional_by_state(panel, horizon=5)
    # each date: emerging is above the day's mean, rolling_over below
    assert xs.loc["emerging", "rel_to_peers"] > 0
    assert xs.loc["rolling_over", "rel_to_peers"] < 0


def test_cross_sectional_rank_buckets_and_spread():
    dates = pd.to_datetime(["2021-01-01", "2021-01-02"], utc=True)
    # higher rel_strength theme also has higher forward return -> positive spread
    panel = pd.DataFrame(
        {
            "theme": ["a", "b", "a", "b"],
            "date": [dates[0], dates[0], dates[1], dates[1]],
            "state": ["emerging"] * 4,
            "rel_strength": [0.3, -0.2, 0.3, -0.2],
            "fwd_5": [0.04, -0.02, 0.05, -0.01],
        }
    )
    buckets = cross_sectional_rank_buckets(panel, horizon=5, signal="rel_strength", q=2)
    assert long_short_spread(buckets) > 0  # strong themes out-rotate weak ones


def test_build_panel_outperformer_has_positive_forward_excess():
    theme = Theme(key="x", label="X", tickers=("A",))
    frames = {"A": _frame(0.004)}                  # theme +0.4%/day
    bench_ret = _frame(0.001)["close"].pct_change()  # bench +0.1%/day
    panel = build_panel((theme,), frames, bench_ret, FAST, horizons=(10,), z_window=126)
    assert not panel.empty
    assert {"state", "slope_z", "rel_strength", "fwd_10", "theme", "date"} <= set(panel.columns)
    # a steady outperformer should have positive mean forward excess
    assert panel["fwd_10"].dropna().mean() > 0


# --- cost-aware long/short simulation -----------------------------------------
def _momentum_universe(n=420):
    """6 themes with persistent, separated trends + a flat benchmark."""
    rates = {"hi1": 0.004, "hi2": 0.0035, "mid1": 0.0015, "mid2": 0.0010,
             "lo1": -0.0005, "lo2": -0.0015}
    themes = tuple(Theme(key=k, label=k, tickers=(k.upper(),)) for k in rates)
    frames = {k.upper(): _frame(r, n=n) for k, r in rates.items()}
    bench_ret = _frame(0.0008, n=n)["close"].pct_change()
    return themes, frames, bench_ret


def test_simulate_long_short_positive_on_persistent_momentum():
    themes, frames, bench = _momentum_universe()
    r = simulate_long_short(themes, frames, bench, FAST, rebalance=21,
                            top_n=2, bottom_n=2, cost_bps=10.0, borrow_bps_annual=50.0)
    assert r.n_rebalances > 3
    assert r.net_ann > 0           # long winners / short losers makes money here
    assert r.gross_ann >= r.net_ann  # costs only ever subtract


def test_simulate_long_short_borrow_reduces_net():
    themes, frames, bench = _momentum_universe()
    cheap = simulate_long_short(themes, frames, bench, FAST, borrow_bps_annual=0.0)
    pricey = simulate_long_short(themes, frames, bench, FAST, borrow_bps_annual=2000.0)
    assert pricey.net_ann < cheap.net_ann  # borrow is charged every period


def test_long_only_ignores_borrow_and_runs():
    themes, frames, bench = _momentum_universe()
    a = simulate_long_short(themes, frames, bench, FAST, long_only=True, borrow_bps_annual=0.0)
    b = simulate_long_short(themes, frames, bench, FAST, long_only=True, borrow_bps_annual=5000.0)
    assert a.n_rebalances > 3
    assert a.net_ann == pytest.approx(b.net_ann)  # no short notional -> borrow irrelevant


def test_benchmark_metrics_produces_series():
    _, _, bench = _momentum_universe()
    r = benchmark_metrics(bench, rebalance=21)
    assert r.n_rebalances > 0
    assert r.signal == "SPY buy&hold"


def test_equal_weight_metrics_runs():
    themes, frames, bench = _momentum_universe()
    r = equal_weight_metrics(themes, frames, bench, FAST, rebalance=21)
    assert r.n_rebalances > 0
    assert r.signal == "EQ-WT all"
