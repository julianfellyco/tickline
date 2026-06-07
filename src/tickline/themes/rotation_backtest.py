"""Cost-aware cross-sectional long/short backtest for theme rotation.

Turns the validated event-study finding (rel-strength LEVEL separates
winners from losers) into a tradeable, honest simulation:

  - Every `rebalance` bars (non-overlapping holds), rank themes by the
    point-in-time signal, go long the top `top_n`, short the bottom
    `bottom_n`, equal-weight, dollar-neutral within the AI universe.
  - Charge transaction costs on turnover and borrow on the short book.
  - Report gross vs NET metrics and a per-year regime split — because a
    number that only works in the 2023-26 mania is not an edge.

Point-in-time: the signal at rebalance date D uses only data <= D
(rel_strength_series is causal); returns are measured D -> next rebalance.
No lookahead. The honest knobs (cost_bps, borrow) are parameters so you
can see the edge's sensitivity, not a single flattering number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import basket_index
from .heat import HeatConfig, basket_returns, rel_strength_series
from .taxonomy import Theme

TRADING_DAYS = 252


@dataclass(frozen=True)
class LongShortResult:
    signal: str
    rebalance: int
    top_n: int
    bottom_n: int
    cost_bps: float
    borrow_bps_annual: float
    n_rebalances: int
    gross_ann: float
    net_ann: float
    net_vol: float
    net_sharpe: float
    net_max_dd: float
    hit_rate: float
    avg_turnover: float
    avg_cost_drag_ann: float
    per_year: dict = field(default_factory=dict)        # year -> net return
    net_returns: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))


def _signal_series(theme: Theme, frames, bench_ret, cfg: HeatConfig, signal: str) -> pd.Series:
    b_ret = basket_returns(frames, theme.tickers)
    if b_ret.empty:
        return pd.Series(dtype=float)
    rs = rel_strength_series(b_ret, bench_ret, cfg.lookback)
    if signal == "slope":
        return rs.diff(cfg.slope_window).dropna()
    return rs  # "level"


def _metrics(net: pd.Series, gross: pd.Series, turnover: float,
             cost_drag: float, **params) -> LongShortResult:
    ppy = TRADING_DAYS / params["rebalance"]
    net_ann = float(net.mean() * ppy)
    net_vol = float(net.std(ddof=1) * np.sqrt(ppy)) if len(net) > 1 else 0.0
    equity = (1.0 + net).cumprod()
    max_dd = float((equity / equity.cummax() - 1.0).min()) if len(equity) else 0.0
    per_year = {
        int(y): float((1.0 + g).prod() - 1.0)
        for y, g in net.groupby(net.index.year)
    }
    return LongShortResult(
        n_rebalances=len(net),
        gross_ann=float(gross.mean() * ppy),
        net_ann=net_ann,
        net_vol=net_vol,
        net_sharpe=net_ann / net_vol if net_vol > 0 else float("nan"),
        net_max_dd=max_dd,
        hit_rate=float((net > 0).mean()) if len(net) else float("nan"),
        avg_turnover=turnover,
        avg_cost_drag_ann=cost_drag * ppy,
        per_year=per_year,
        net_returns=net,
        **params,
    )


def simulate_long_short(
    themes: tuple[Theme, ...],
    frames: dict[str, pd.DataFrame],
    bench_ret: pd.Series,
    cfg: HeatConfig,
    *,
    rebalance: int = 21,
    top_n: int = 3,
    bottom_n: int = 3,
    cost_bps: float = 10.0,
    borrow_bps_annual: float = 50.0,
    signal: str = "level",
    long_only: bool = False,
) -> LongShortResult:
    """Run the rotation long/short (or long-only) and return net metrics."""
    rel = {t.key: _signal_series(t, frames, bench_ret, cfg, signal) for t in themes}
    idx = {t.key: basket_index(frames, t.tickers) for t in themes}
    rel = {k: v for k, v in rel.items() if not v.empty and not idx[k].empty}

    dates = bench_ret.index
    rdates = dates[cfg.lookback + cfg.slope_window:: rebalance]

    prev_w: dict[str, float] = {}
    gross_rows: list[float] = []
    net_rows: list[float] = []
    hold_dates: list[pd.Timestamp] = []
    turnovers: list[float] = []
    cost_drags: list[float] = []

    for i in range(len(rdates) - 1):
        d, nxt = rdates[i], rdates[i + 1]
        scores = {k: rel[k].asof(d) for k in rel}
        scores = {k: v for k, v in scores.items() if pd.notna(v)}
        if len(scores) < top_n + bottom_n:
            continue
        ranked = sorted(scores, key=scores.get, reverse=True)
        longs = ranked[:top_n]
        shorts = [] if long_only else ranked[-bottom_n:]
        w = {k: 1.0 / top_n for k in longs}
        for k in shorts:
            w[k] = w.get(k, 0.0) - 1.0 / bottom_n

        turnover = sum(abs(w.get(k, 0.0) - prev_w.get(k, 0.0)) for k in set(w) | set(prev_w))

        def hold_ret(k: str) -> float:
            s = idx[k]
            a, b = s.asof(d), s.asof(nxt)
            if pd.isna(a) or pd.isna(b) or a == 0:
                return 0.0
            return b / a - 1.0

        gross = sum(wt * hold_ret(k) for k, wt in w.items())
        hold_days = max(1, (nxt - d).days)
        cost = turnover * cost_bps / 1e4
        short_notional = 0.0 if long_only else 1.0
        borrow = short_notional * borrow_bps_annual / 1e4 * hold_days / 365.0
        net = gross - cost - borrow

        gross_rows.append(gross)
        net_rows.append(net)
        hold_dates.append(d)
        turnovers.append(turnover)
        cost_drags.append(cost + borrow)
        prev_w = w

    if not net_rows:
        return LongShortResult(
            signal=signal, rebalance=rebalance, top_n=top_n, bottom_n=bottom_n,
            cost_bps=cost_bps, borrow_bps_annual=borrow_bps_annual, n_rebalances=0,
            gross_ann=0.0, net_ann=0.0, net_vol=0.0, net_sharpe=float("nan"),
            net_max_dd=0.0, hit_rate=float("nan"), avg_turnover=0.0, avg_cost_drag_ann=0.0,
        )

    idx_dt = pd.DatetimeIndex(hold_dates)
    net = pd.Series(net_rows, index=idx_dt)
    gross = pd.Series(gross_rows, index=idx_dt)
    return _metrics(
        net, gross,
        turnover=float(np.mean(turnovers)),
        cost_drag=float(np.mean(cost_drags)),
        signal=signal, rebalance=rebalance, top_n=top_n, bottom_n=bottom_n,
        cost_bps=cost_bps, borrow_bps_annual=borrow_bps_annual,
    )


def equal_weight_metrics(
    themes: tuple[Theme, ...],
    frames: dict[str, pd.DataFrame],
    bench_ret: pd.Series,
    cfg: HeatConfig,
    rebalance: int = 21,
    cost_bps: float = 10.0,
) -> LongShortResult:
    """Own ALL available themes equal-weight — the survivorship-beta control.

    The universe is hindsight-selected winners, so this baseline already
    captures "owning the winners." If top-N momentum can't beat THIS, the
    apparent edge is pure survivorship, not theme selection.
    """
    idx = {t.key: basket_index(frames, t.tickers) for t in themes}
    idx = {k: v for k, v in idx.items() if not v.empty}
    rdates = bench_ret.index[cfg.lookback + cfg.slope_window:: rebalance]
    rows, dts = [], []
    for i in range(len(rdates) - 1):
        d, nxt = rdates[i], rdates[i + 1]
        rets = []
        for s in idx.values():
            a, b = s.asof(d), s.asof(nxt)
            if pd.notna(a) and pd.notna(b) and a != 0:
                rets.append(b / a - 1.0)
        if not rets:
            continue
        rows.append(sum(rets) / len(rets) - cost_bps / 1e4)  # nominal rebalance cost
        dts.append(d)
    net = pd.Series(rows, index=pd.DatetimeIndex(dts))
    return _metrics(net, net, turnover=1.0, cost_drag=cost_bps / 1e4,
                    signal="EQ-WT all", rebalance=rebalance, top_n=0, bottom_n=0,
                    cost_bps=cost_bps, borrow_bps_annual=0.0)


def benchmark_metrics(bench_ret: pd.Series, rebalance: int = 21, warmup: int = 73) -> LongShortResult:
    """Buy-and-hold benchmark (e.g. SPY) over the same rebalance grid.

    The honest yardstick for a long-only strategy: does rotating into the
    leaders beat just holding the index? Same period, same compounding.
    """
    idx = (1.0 + bench_ret).cumprod()
    rdates = bench_ret.index[warmup::rebalance]
    rows, dts = [], []
    for i in range(len(rdates) - 1):
        a, b = idx.asof(rdates[i]), idx.asof(rdates[i + 1])
        if pd.notna(a) and pd.notna(b) and a != 0:
            rows.append(b / a - 1.0); dts.append(rdates[i])
    net = pd.Series(rows, index=pd.DatetimeIndex(dts))
    return _metrics(
        net, net, turnover=0.0, cost_drag=0.0,
        signal="SPY buy&hold", rebalance=rebalance, top_n=0, bottom_n=0,
        cost_bps=0.0, borrow_bps_annual=0.0,
    )
