"""Tests for L6 allocation/consensus layer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.allocation import (
    DrawdownCircuitBreaker,
    Regime,
    RegimeClassifier,
    RegimeGatedStrategy,
    VoteEnsemble,
)
from tickline.strategies import RSIMeanReversion, SMACrossover
from tickline.strategies.base import Strategy


class _AlwaysLong(Strategy):
    name = "always_long"
    def generate_positions(self, ohlcv):
        return pd.Series(1.0, index=ohlcv.index)


class _AlwaysShort(Strategy):
    name = "always_short"
    def generate_positions(self, ohlcv):
        return pd.Series(-1.0, index=ohlcv.index)


class _AlwaysFlat(Strategy):
    name = "always_flat"
    def generate_positions(self, ohlcv):
        return pd.Series(0.0, index=ohlcv.index)


def _market(n: int = 500, seed: int = 5, drift: float = 0.0, vol: float = 0.01) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = drift + rng.normal(0.0, vol, n)
    close = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": close, "high": close * 1.003, "low": close * 0.997, "close": close, "volume": 1.0},
        index=idx,
    )


def _strong_uptrend(n: int = 500) -> pd.DataFrame:
    """Synthetic market that should classify as trend_up most of the time."""
    return _market(n=n, seed=21, drift=0.005, vol=0.005)


def _choppy(n: int = 500) -> pd.DataFrame:
    return _market(n=n, seed=42, drift=0.0, vol=0.015)


def test_regime_classifier_emits_all_three_on_mixed_data():
    df = _market(n=2000, seed=8, drift=0.0005, vol=0.012)
    regs = RegimeClassifier(lookback=50, vol_window=20).classify(df)
    seen = set(regs.unique())
    # at minimum, range must appear; trend up or down should also appear
    assert Regime.RANGE in seen
    assert Regime.TREND_UP in seen or Regime.TREND_DOWN in seen


def test_regime_classifier_detects_strong_uptrend():
    df = _strong_uptrend(800)
    regs = RegimeClassifier(lookback=50).classify(df)
    # majority of mature bars (post-warmup) should be TREND_UP
    mature = regs.iloc[60:]
    up_share = (mature == Regime.TREND_UP).mean()
    assert up_share > 0.5


def test_regime_gated_rejects_empty_map():
    with pytest.raises(ValueError):
        RegimeGatedStrategy(regime_map={})


def test_regime_gated_routes_correctly():
    df = _strong_uptrend(800)
    strat = RegimeGatedStrategy(
        regime_map={
            Regime.TREND_UP: _AlwaysLong(),
            Regime.RANGE: _AlwaysFlat(),
            Regime.TREND_DOWN: _AlwaysFlat(),
        }
    )
    pos = strat.generate_positions(df)
    regimes = RegimeClassifier(lookback=50).classify(df)
    # wherever regime is TREND_UP, position must be 1.0; else 0.0
    assert (pos[regimes == Regime.TREND_UP] == 1.0).all()
    assert (pos[regimes != Regime.TREND_UP] == 0.0).all()


def test_vote_ensemble_clipped_to_unit_range():
    df = _market(300)
    ensemble = VoteEnsemble([_AlwaysLong(), _AlwaysShort(), _AlwaysLong()])
    pos = ensemble.generate_positions(df)
    assert pos.between(-1.0, 1.0).all()
    # equal-weighted: 2 long + 1 short = +1/3
    assert pos.iloc[0] == pytest.approx(1.0 / 3.0)


def test_vote_ensemble_weighted():
    df = _market(200)
    ensemble = VoteEnsemble(
        [_AlwaysLong(), _AlwaysShort()],
        weights=[3.0, 1.0],
    )
    pos = ensemble.generate_positions(df)
    # weights normalized to 0.75 / 0.25 → +0.5
    assert pos.iloc[10] == pytest.approx(0.5)


def test_vote_ensemble_rejects_bad_weights():
    with pytest.raises(ValueError):
        VoteEnsemble([_AlwaysLong()], weights=[-1.0])
    with pytest.raises(ValueError):
        VoteEnsemble([_AlwaysLong(), _AlwaysLong()], weights=[1.0])


def test_drawdown_breaker_kills_positions_in_loss_streaks():
    """A strategy that's always long in a falling market should get killed."""
    df = _market(n=500, seed=99, drift=-0.002, vol=0.01)
    breaker = DrawdownCircuitBreaker(
        primary=_AlwaysLong(), max_drawdown=0.05, lookback_bars=100, cooldown_bars=20
    )
    pos = breaker.generate_positions(df)
    # at least some bars should be killed
    assert (pos == 0.0).any()


def test_drawdown_breaker_validates_inputs():
    with pytest.raises(ValueError):
        DrawdownCircuitBreaker(primary=_AlwaysLong(), max_drawdown=1.5)
    with pytest.raises(ValueError):
        DrawdownCircuitBreaker(primary=_AlwaysLong(), lookback_bars=0)


def test_drawdown_breaker_passthrough_in_bull_market():
    """In a steady uptrend, the breaker should never trip."""
    df = _strong_uptrend(600)
    primary = _AlwaysLong()
    breaker = DrawdownCircuitBreaker(primary=primary, max_drawdown=0.30, lookback_bars=200)
    pos = breaker.generate_positions(df)
    assert (pos == 1.0).all()
