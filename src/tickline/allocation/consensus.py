"""Consensus mechanisms for combining multiple strategies.

Two patterns from real trading shops:

  1. RegimeGatedStrategy — different strategies are authorized to
     trade in different market regimes (trend-following only in
     trends, mean-reversion only in ranges). Implemented as a meta-
     Strategy so the rest of the framework treats it identically.

  2. VoteEnsemble — N strategies generate positions independently;
     each bar's final position is the majority vote (or weighted
     average) of their signals.

Both are implemented as `Strategy` subclasses so they slot into the
existing Backtester / Portfolio / PaperRunner without any other code
changes.
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd

from ..strategies.base import Strategy
from .regime import Regime, RegimeClassifier


class RegimeGatedStrategy(Strategy):
    """Route trading to different strategies based on classified regime.

    Args:
        regime_map: dict mapping Regime → Strategy. Bars whose regime
                    is not in the map produce a flat position.
        classifier: optional custom RegimeClassifier (default config used otherwise).
    """

    def __init__(
        self,
        regime_map: Mapping[Regime, Strategy],
        classifier: RegimeClassifier | None = None,
    ):
        if not regime_map:
            raise ValueError("regime_map must contain at least one (Regime, Strategy)")
        self.regime_map = dict(regime_map)
        self.classifier = classifier or RegimeClassifier()
        self.name = "regime_gated"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        regimes = self.classifier.classify(ohlcv)
        out = pd.Series(0.0, index=ohlcv.index, name="position")
        for regime, strategy in self.regime_map.items():
            sub_positions = strategy.generate_positions(ohlcv).fillna(0.0)
            mask = regimes == regime
            out.loc[mask] = sub_positions.loc[mask].values
        return out


class VoteEnsemble(Strategy):
    """Combine N strategies by signed-vote across their positions.

    Each bar: sum of strategy positions / N. Result clipped to [-1, 1].
    A pure majority vote (3 strategies, 2 say long, 1 flat → +0.67) is
    often more robust than choosing any single strategy a priori.
    """

    def __init__(self, strategies: list[Strategy], weights: list[float] | None = None):
        if not strategies:
            raise ValueError("need at least one strategy")
        if weights is None:
            weights = [1.0] * len(strategies)
        if len(weights) != len(strategies):
            raise ValueError("len(weights) must equal len(strategies)")
        if any(w < 0 for w in weights):
            raise ValueError("weights must be non-negative")
        total = sum(weights) or 1.0
        self.strategies = strategies
        self.weights = [w / total for w in weights]
        self.name = "vote_ensemble"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        positions = pd.Series(0.0, index=ohlcv.index, name="position")
        for strategy, w in zip(self.strategies, self.weights):
            positions = positions + strategy.generate_positions(ohlcv).fillna(0.0) * w
        return positions.clip(-1.0, 1.0)
