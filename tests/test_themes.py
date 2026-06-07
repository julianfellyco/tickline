"""Tests for the AI theme-rotation watchlist (deterministic, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.themes.heat import (
    FAST,
    HeatComponents,
    ThemeHeat,
    basket_returns,
    compute_theme_heat,
    rel_strength_series,
)
from tickline.themes.rotation import (
    detect_transitions,
    next_trend_candidates,
    rank_by_rotation,
)
from tickline.themes.state import (
    RankState,
    StateConfig,
    ThemeState,
    classify,
    rank_states,
)
from tickline.themes.taxonomy import (
    AI_THEMES,
    ALL_THEMES,
    GROUPS,
    Theme,
    all_tickers,
    themes_in_group,
)


# --- helpers -----------------------------------------------------------------
def _frame(daily_return: float, n: int = 90, start: float = 100.0, vol: float = 1e6) -> pd.DataFrame:
    idx = pd.date_range("2025-09-01", periods=n, freq="D", tz="UTC")
    close = start * np.cumprod(np.full(n, 1.0 + daily_return))
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": vol},
        index=idx,
    )


def _heat(key="t", ml=0.05, ms=0.0, msz=None, rl=None, rsl=None) -> ThemeHeat:
    return ThemeHeat(
        key=key,
        label=key,
        as_of=pd.Timestamp("2026-01-01", tz="UTC"),
        market_level=ml,
        market_slope=ms,
        market_slope_z=ms if msz is None else msz,
        retail_level=rl,
        retail_slope=rsl,
        components=HeatComponents(ml, 0.5, 0.0, None),
        n_constituents=2,
    )


# --- taxonomy ----------------------------------------------------------------
def test_all_tickers_includes_benchmark_and_dedupes():
    tickers = all_tickers()
    assert "SPY" in tickers
    assert "NVDA" in tickers
    assert len(tickers) == len(set(tickers))  # no dupes despite NVDA in two themes


# --- state machine (slope expressed as a z-score, threshold 0.5) -------------
def test_state_emerging_market_leads_crowd_asleep():
    assert classify(_heat(msz=1.0, rl=0.0, rsl=0.0)) == ThemeState.EMERGING


def test_state_confirming_both_rising_not_hot():
    assert classify(_heat(msz=1.0, rl=0.2, rsl=0.8)) == ThemeState.CONFIRMING


def test_state_crowded_both_rising_retail_hot():
    assert classify(_heat(msz=1.0, rl=1.5, rsl=0.8)) == ThemeState.CROWDED


def test_state_exhausting_crowd_hot_price_stalled():
    assert classify(_heat(msz=0.0, rl=1.5, rsl=0.1)) == ThemeState.EXHAUSTING


def test_state_rolling_over_market_falling():
    assert classify(_heat(msz=-1.0, rl=0.0, rsl=0.0)) == ThemeState.ROLLING_OVER


def test_state_dormant_flat():
    assert classify(_heat(msz=0.0, rl=0.0, rsl=0.0)) == ThemeState.DORMANT


def test_state_market_only_fallback():
    # no retail feed -> classify on market alone
    assert classify(_heat(msz=1.0, rl=None, rsl=None)) == ThemeState.EMERGING
    assert classify(_heat(msz=-1.0, rl=None, rsl=None)) == ThemeState.ROLLING_OVER
    assert classify(_heat(msz=0.0, rl=None, rsl=None)) == ThemeState.DORMANT


def test_state_config_thresholds_respected():
    cfg = StateConfig(slope_z_rise=2.0)  # demand a bigger z-move to call "rising"
    assert classify(_heat(msz=1.0, rl=None, rsl=None), cfg) == ThemeState.DORMANT


# --- heat engine -------------------------------------------------------------
def test_basket_returns_equal_weight():
    frames = {"A": _frame(0.01), "B": _frame(0.03)}
    br = basket_returns(frames, ("A", "B"))
    assert br.iloc[-1] == pytest.approx(0.02, abs=1e-9)  # mean of 1% and 3%


def test_rel_strength_positive_when_theme_outperforms():
    theme = _frame(0.004)
    bench = _frame(0.001)
    rs = rel_strength_series(theme["close"].pct_change(), bench["close"].pct_change(), 21)
    assert rs.iloc[-1] > 0


def test_compute_theme_heat_outperformer():
    theme = Theme(key="x", label="X", tickers=("A", "B"))
    frames = {"A": _frame(0.004), "B": _frame(0.005)}
    bench_ret = _frame(0.001)["close"].pct_change()
    heat = compute_theme_heat(theme, frames, bench_ret, FAST)
    assert heat is not None
    assert heat.market_level > 0          # outperforms benchmark
    assert heat.components.breadth == 1.0  # steady uptrend -> all above SMA
    assert heat.retail_level is None       # no retail series supplied
    assert heat.n_constituents == 2


def test_compute_theme_heat_underperformer():
    theme = Theme(key="x", label="X", tickers=("A",))
    frames = {"A": _frame(-0.002)}
    bench_ret = _frame(0.002)["close"].pct_change()
    heat = compute_theme_heat(theme, frames, bench_ret, FAST)
    assert heat is not None
    assert heat.market_level < 0


def test_compute_theme_heat_none_on_no_data():
    theme = Theme(key="x", label="X", tickers=("A",))
    bench_ret = _frame(0.001)["close"].pct_change()
    assert compute_theme_heat(theme, {}, bench_ret, FAST) is None


# --- rotation + transitions --------------------------------------------------
def test_rank_by_rotation_orders_by_slope():
    a = _heat("a", ms=0.05)
    b = _heat("b", ms=-0.01)
    c = _heat("c", ms=0.02)
    ranked = rank_by_rotation([b, c, a])
    assert [h.key for h in ranked] == ["a", "c", "b"]


def test_detect_transitions_fires_only_on_change():
    curr = {"a": _heat("a", ms=0.03), "b": _heat("b", ms=0.03)}
    states = {"a": ThemeState.EMERGING, "b": ThemeState.EMERGING}
    prev = {"a": "dormant", "b": "emerging"}  # a changed, b did not
    trans = detect_transitions(prev, curr, states, "fast")
    keys = {t.key for t in trans}
    assert "a" in keys
    assert "b" not in keys


def test_detect_transitions_suppresses_new_nonactionable():
    curr = {"new": _heat("new", ms=0.0)}
    states = {"new": ThemeState.DORMANT}
    trans = detect_transitions({}, curr, states, "fast")
    assert trans == []  # brand-new + dormant -> no alert


def test_detect_transitions_alerts_new_actionable():
    curr = {"new": _heat("new", ms=0.03)}
    states = {"new": ThemeState.EMERGING}
    trans = detect_transitions({}, curr, states, "fast")
    assert len(trans) == 1
    assert trans[0].from_state is None
    assert trans[0].to_state == "emerging"


def test_next_trend_candidates_picks_early_accelerating():
    heats = [_heat("a", ms=0.05), _heat("b", ms=-0.02), _heat("c", ms=0.01)]
    states = {
        "a": ThemeState.EMERGING,
        "b": ThemeState.ROLLING_OVER,
        "c": ThemeState.CONFIRMING,
    }
    cands = next_trend_candidates(heats, states)
    keys = [h.key for h in cands]
    assert keys == ["a", "c"]  # both early + positive slope, ranked by slope


def test_rank_states_tags_leaders_and_laggards():
    heats = [
        _heat("a", ml=0.30),
        _heat("b", ml=0.10),
        _heat("c", ml=0.00),
        _heat("d", ml=-0.10),
        _heat("e", ml=-0.30),
    ]
    states = rank_states(heats, top_frac=0.2, bottom_frac=0.2)
    assert states["a"] == RankState.LEADER       # strongest
    assert states["e"] == RankState.LAGGARD       # weakest
    assert states["c"] == RankState.NEUTRAL       # middle


def test_rank_states_no_overlap_on_tiny_universe():
    states = rank_states([_heat("a", ml=0.2), _heat("b", ml=-0.2)], 0.5, 0.5)
    assert set(states.values()) == {RankState.LEADER, RankState.LAGGARD}
    assert states["a"] == RankState.LEADER


def test_themes_registry_nonempty_and_keyed():
    assert len(AI_THEMES) == 10                       # validated-backtest subset is fixed
    assert all(t.key and t.tickers for t in AI_THEMES)


def test_all_themes_universe_is_comprehensive_and_grouped():
    assert len(ALL_THEMES) >= 30                       # full US rotation universe
    keys = [t.key for t in ALL_THEMES]
    assert len(keys) == len(set(keys))                 # unique keys
    # every AI subset theme is present in the full universe
    assert set(t.key for t in AI_THEMES) <= set(keys)
    # every theme is assigned to a known display group
    assert all(t.group in GROUPS for t in ALL_THEMES)
    # groups partition the universe with no orphans
    assert sum(len(themes_in_group(g)) for g in GROUPS) == len(ALL_THEMES)
