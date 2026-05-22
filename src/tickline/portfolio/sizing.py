"""Position sizing methods.

Each function takes a returns DataFrame (one column per sleeve) and a
lookback in bars, and returns a weight DataFrame aligned to the same
index. Weights are applied to *target positions*, not to capital
directly — the sleeve's strategy already returned a target in [-1, 1].

These functions assume rows are time-ordered. Lookback windows are
right-aligned (only past data informs each weight) to preserve the
no-lookahead invariant.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd


class SizingMethod(str, Enum):
    EQUAL = "equal"
    INVERSE_VOL = "inverse_vol"
    VOL_TARGET = "vol_target"
    KELLY = "kelly"


def equal_weight(returns: pd.DataFrame, lookback: int = 30) -> pd.DataFrame:
    """1/N weights — the dumb baseline. Lookback is unused."""
    n = returns.shape[1]
    if n == 0:
        return pd.DataFrame(index=returns.index)
    weight = 1.0 / n
    return pd.DataFrame(weight, index=returns.index, columns=returns.columns)


def inverse_vol(returns: pd.DataFrame, lookback: int = 30) -> pd.DataFrame:
    """Weight each sleeve inversely to its realized rolling volatility.

    Risk-equalizes the sleeves: a noisy sleeve gets a smaller share
    than a quiet one. Sums to 1.0 per row.
    """
    vol = returns.rolling(lookback).std()
    inv = 1.0 / vol.replace(0, np.nan)
    weights = inv.div(inv.sum(axis=1), axis=0)
    return weights.fillna(0.0)


def vol_target(
    returns: pd.DataFrame,
    target_annual_vol: float = 0.15,
    lookback: int = 30,
    bars_per_year: int = 8_760,
    max_leverage: float = 2.0,
) -> pd.DataFrame:
    """Scale total portfolio exposure to hit a fixed annualized vol.

    Starts from inverse-vol allocation across sleeves, then multiplies
    the *row sum* of weights by a leverage factor that targets
    `target_annual_vol`. Caps leverage at `max_leverage` to prevent
    insane sizing when realized vol is near zero.
    """
    iv = inverse_vol(returns, lookback)
    # estimate portfolio vol under iv weights
    realized = (iv * returns).sum(axis=1)
    port_vol_ann = realized.rolling(lookback).std() * np.sqrt(bars_per_year)
    lev = (target_annual_vol / port_vol_ann.replace(0, np.nan)).clip(upper=max_leverage)
    return iv.mul(lev, axis=0).fillna(0.0)


def fractional_kelly(
    returns: pd.DataFrame,
    fraction: float = 0.25,
    lookback: int = 90,
    max_leverage: float = 1.0,
) -> pd.DataFrame:
    """Fractional Kelly weights per sleeve.

    For a single asset, Kelly = mean / variance of returns. We use
    *fraction × Kelly* (default ¼) — full Kelly is famously a
    confidence trap. Negative-expectancy sleeves get zero weight.
    """
    mu = returns.rolling(lookback).mean()
    var = returns.rolling(lookback).var().replace(0, np.nan)
    raw = (mu / var) * fraction
    raw = raw.clip(lower=0.0, upper=max_leverage)
    return raw.fillna(0.0)
