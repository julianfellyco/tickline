"""Performance metrics.

Sharpe, Sortino, max drawdown, Calmar, hit rate. Risk-free rate defaults
to 0 — appropriate for crypto, easy to adjust for equities.

Annualization factor depends on bar frequency. Always pass the right one;
a daily-Sharpe pretending to be annualized is a classic retail mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

PERIODS_PER_YEAR = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}


@dataclass
class PerformanceMetrics:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    calmar: float
    volatility_pct: float
    num_trades: int
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float

    def as_table(self) -> str:
        rows = [
            ("Total return", f"{self.total_return_pct:+.2f}%"),
            ("CAGR", f"{self.cagr_pct:+.2f}%"),
            ("Sharpe (ann.)", f"{self.sharpe:.2f}"),
            ("Sortino (ann.)", f"{self.sortino:.2f}"),
            ("Max drawdown", f"{self.max_drawdown_pct:.2f}%"),
            ("Calmar", f"{self.calmar:.2f}"),
            ("Volatility (ann.)", f"{self.volatility_pct:.2f}%"),
            ("Trades", str(self.num_trades)),
            ("Win rate", f"{self.win_rate_pct:.1f}%"),
            ("Avg win", f"{self.avg_win_pct:+.2f}%"),
            ("Avg loss", f"{self.avg_loss_pct:+.2f}%"),
            ("Profit factor", f"{self.profit_factor:.2f}"),
        ]
        width = max(len(k) for k, _ in rows) + 2
        return "\n".join(f"  {k.ljust(width)}{v}" for k, v in rows)


def compute_metrics(
    returns: pd.Series,
    equity: pd.Series,
    trades: pd.DataFrame,
    timeframe: str = "1h",
    risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    periods = PERIODS_PER_YEAR.get(timeframe, 8_760)
    excess = returns - (risk_free_rate / periods)

    mean = excess.mean() * periods
    std = excess.std(ddof=0) * np.sqrt(periods)
    sharpe = float(mean / std) if std > 0 else 0.0

    downside = excess[excess < 0]
    downside_std = downside.std(ddof=0) * np.sqrt(periods) if not downside.empty else 0.0
    sortino = float(mean / downside_std) if downside_std > 0 else 0.0

    running_max = equity.cummax()
    drawdown = (equity / running_max - 1.0)
    max_dd = float(drawdown.min())
    max_dd_pct = max_dd * 100.0

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max(len(equity) / periods, 1e-9)
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0
    calmar = float(cagr / abs(max_dd)) if max_dd < 0 else 0.0

    vol_ann = float(returns.std(ddof=0) * np.sqrt(periods)) * 100.0

    if not trades.empty:
        wins = trades[trades["pnl_pct"] > 0]["pnl_pct"]
        losses = trades[trades["pnl_pct"] <= 0]["pnl_pct"]
        win_rate = len(wins) / len(trades) * 100.0
        avg_win = float(wins.mean() * 100.0) if not wins.empty else 0.0
        avg_loss = float(losses.mean() * 100.0) if not losses.empty else 0.0
        gross_win = float(wins.sum()) if not wins.empty else 0.0
        gross_loss = float(abs(losses.sum())) if not losses.empty else 0.0
        profit_factor = gross_win / gross_loss if gross_loss > 0 else float("inf")
    else:
        win_rate = avg_win = avg_loss = profit_factor = 0.0

    return PerformanceMetrics(
        total_return_pct=total_return * 100.0,
        cagr_pct=cagr * 100.0,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown_pct=max_dd_pct,
        calmar=calmar,
        volatility_pct=vol_ann,
        num_trades=len(trades),
        win_rate_pct=win_rate,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        profit_factor=profit_factor,
    )
