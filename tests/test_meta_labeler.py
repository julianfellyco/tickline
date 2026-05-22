"""Tests for the meta-labeler."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.intelligence import MetaLabeler, build_features
from tickline.strategies import SMACrossover


def _trendy_market(n: int = 4000, seed: int = 17) -> pd.DataFrame:
    """Synthetic price with a learnable regime: high vol → bad, low vol → good."""
    rng = np.random.default_rng(seed)
    # alternating regimes every 250 bars
    regime = (np.arange(n) // 250) % 2
    drift = np.where(regime == 0, 0.0008, -0.0005)
    vol = np.where(regime == 0, 0.006, 0.014)
    returns = drift + rng.normal(0.0, vol)
    close = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    volume = rng.uniform(100, 1000, n) * (1 + regime * 1.5)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.004,
            "low": close * 0.996,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def test_build_features_columns_and_no_lookahead():
    df = _trendy_market(500)
    feats = build_features(df)
    expected = {
        "vol_20", "rsi_14", "ret_5", "ret_20", "volume_z",
        "sma_dist", "sma_slope", "drawdown_20", "atr_rel",
        "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    }
    assert expected <= set(feats.columns)
    # warmup region has NaN, later region must be clean
    assert feats.iloc[100:].notna().all().all()


def test_meta_labeler_requires_fit_before_inference():
    primary = SMACrossover(10, 30)
    meta = MetaLabeler(primary)
    df = _trendy_market(500)
    with pytest.raises(RuntimeError):
        meta.generate_positions(df)


def test_meta_labeler_rejects_bad_threshold():
    primary = SMACrossover(10, 30)
    with pytest.raises(ValueError):
        MetaLabeler(primary, threshold=0.0)
    with pytest.raises(ValueError):
        MetaLabeler(primary, threshold=1.0)


def test_meta_labeler_fits_and_filters():
    df = _trendy_market(4000)
    primary = SMACrossover(10, 30)
    meta = MetaLabeler(primary, threshold=0.50, min_train_signals=10)
    info = meta.fit(df)

    assert info.n_train_signals > 0
    assert 0.0 <= info.train_auc <= 1.0
    assert 0.0 <= info.test_auc <= 1.0
    assert 0.0 <= info.base_rate <= 1.0
    assert not info.feature_importance.empty


def test_meta_filtered_positions_are_subset_of_primary():
    df = _trendy_market(4000)
    primary = SMACrossover(10, 30)
    primary_pos = primary.generate_positions(df).fillna(0.0)
    meta = MetaLabeler(primary, threshold=0.5, min_train_signals=10)
    meta.fit(df.iloc[: int(len(df) * 0.7)])
    filtered_pos = meta.generate_positions(df)

    # whenever meta is long, primary must also have been long at that bar
    long_when_meta_long = ((filtered_pos > 0) & (primary_pos == 0)).sum()
    assert long_when_meta_long == 0, (
        "meta-labeler invented positions the primary didn't authorize"
    )


def test_too_few_signals_raises():
    df = _trendy_market(200)
    primary = SMACrossover(50, 100)
    meta = MetaLabeler(primary, min_train_signals=200)
    with pytest.raises(ValueError):
        meta.fit(df)
