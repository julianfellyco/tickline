"""Risk overlays — last-line-of-defense controls that override signals.

These wrap any Strategy and can force flatten when conditions trigger.
The pattern: a great strategy with bad sizing still blows up. Position
sizing comes *before* finding the next clever idea. Survival first,
then alpha.

DrawdownCircuitBreaker forces flat when the simulated portfolio's
rolling drawdown exceeds a threshold. The drawdown is computed from
the primary strategy's own returns at zero cost (a conservative
estimate — real costs would deepen the drawdown).
"""

from __future__ import annotations

import pandas as pd

from ..strategies.base import Strategy


class DrawdownCircuitBreaker(Strategy):
    """Force flat when simulated drawdown exceeds `max_drawdown`.

    `cooldown_bars`: after the breaker trips, stay flat for this many
    bars before re-arming. Without a cooldown the strategy whipsaws
    in and out at the trip threshold.
    """

    def __init__(
        self,
        primary: Strategy,
        max_drawdown: float = 0.15,
        lookback_bars: int = 200,
        cooldown_bars: int = 100,
    ):
        if not 0.0 < max_drawdown < 1.0:
            raise ValueError("max_drawdown must be in (0, 1)")
        if lookback_bars <= 0:
            raise ValueError("lookback_bars must be positive")
        self.primary = primary
        self.max_drawdown = max_drawdown
        self.lookback_bars = lookback_bars
        self.cooldown_bars = max(0, cooldown_bars)
        self.name = f"dd_breaker+{primary.name}"

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        positions = self.primary.generate_positions(ohlcv).fillna(0.0)
        # simulate equity at zero cost (conservative — under-states real DD)
        bar_returns = ohlcv["close"].pct_change().fillna(0.0)
        strategy_returns = positions.shift(1).fillna(0.0) * bar_returns
        equity = (1.0 + strategy_returns).cumprod()
        rolling_max = equity.rolling(self.lookback_bars, min_periods=1).max()
        drawdown = equity / rolling_max - 1.0

        # initial breaker mask: where drawdown breaches threshold
        tripped = drawdown <= -self.max_drawdown

        # extend each trip for `cooldown_bars` after
        if self.cooldown_bars > 0:
            # forward-roll: any position within cooldown of a trip stays killed
            cooldown_mask = tripped.rolling(self.cooldown_bars + 1, min_periods=1).max().astype(bool)
        else:
            cooldown_mask = tripped

        out = positions.copy()
        out[cooldown_mask] = 0.0
        return out
