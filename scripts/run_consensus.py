#!/usr/bin/env python3
"""L6 consensus runner.

Compares four ways of combining the SMA crossover and RSI mean-reversion
strategies:

  1. SMA alone (baseline)
  2. RSI alone (baseline)
  3. Equal-weighted vote ensemble
  4. Regime-gated: SMA in trends, RSI in ranges, flat otherwise
  5. Regime-gated + drawdown circuit breaker

This is the meta-layer the framework was missing — what runs when.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.allocation import (
    DrawdownCircuitBreaker,
    Regime,
    RegimeClassifier,
    RegimeGatedStrategy,
    VoteEnsemble,
)
from tickline.backtest import Backtester, CostModel
from tickline.data import fetch_ohlcv, load_cached
from tickline.risk import compute_metrics
from tickline.strategies import RSIMeanReversion, SMACrossover

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}consensus{INK}                       │
   │  {INK_FAINT}regime gating · vote · risk overlay{INK}      │
   └─────────────────────────────────────────┘{RESET}
"""


def _color(value: float) -> str:
    if value > 0:
        return f"{SIGNAL}{value:+.2f}{RESET}"
    if value < 0:
        return f"{ALERT}{value:+.2f}{RESET}"
    return f"{INK}{value:+.2f}{RESET}"


def _run(name: str, strategy, df, timeframe: str) -> tuple[str, dict]:
    bt = Backtester(initial_capital=10_000.0, cost_model=CostModel())
    result = bt.run(df, strategy)
    metrics = compute_metrics(result.returns, result.equity_curve, result.trades, timeframe)
    return name, {
        "return": metrics.total_return_pct,
        "sharpe": metrics.sharpe,
        "max_dd": metrics.max_drawdown_pct,
        "trades": metrics.num_trades,
        "win_rate": metrics.win_rate_pct,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Consensus / regime gating comparison")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    print(BANNER)
    if args.no_fetch:
        df = load_cached(args.exchange, args.symbol, args.timeframe)
    else:
        df = fetch_ohlcv(args.symbol, args.timeframe, args.days, args.exchange)
    if df.empty:
        print(f"{ALERT}no data{RESET}")
        return 1
    print(f"{INK_FAINT}>>{RESET} {len(df)} bars  ({df.index[0].date()} → {df.index[-1].date()})\n")

    # Regime breakdown
    classifier = RegimeClassifier(lookback=50, vol_window=20)
    durations = classifier.regime_durations(df)
    print(f"{INK}Regime breakdown:{RESET}")
    for reg in [Regime.TREND_UP, Regime.RANGE, Regime.TREND_DOWN]:
        count = int(durations.get(reg, 0))
        share = count / max(1, len(df)) * 100
        bar = "█" * int(share / 2)
        color = SIGNAL if reg == Regime.TREND_UP else (
            ALERT if reg == Regime.TREND_DOWN else AMBER
        )
        print(f"   {color}{reg.value:<11}{RESET} {bar:<50} {count:>5} bars  ({share:>5.1f}%)")
    print()

    # build strategies
    sma = SMACrossover(fast=20, slow=50)
    rsi = RSIMeanReversion(period=14, lower=30.0, exit_level=55.0)

    regime_gated = RegimeGatedStrategy(
        regime_map={
            Regime.TREND_UP: SMACrossover(fast=20, slow=50),
            Regime.RANGE: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
        },
        classifier=classifier,
    )

    regime_gated_with_breaker = DrawdownCircuitBreaker(
        primary=RegimeGatedStrategy(
            regime_map={
                Regime.TREND_UP: SMACrossover(fast=20, slow=50),
                Regime.RANGE: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
            },
            classifier=classifier,
        ),
        max_drawdown=0.10,
        lookback_bars=200,
        cooldown_bars=72,
    )

    vote = VoteEnsemble([
        SMACrossover(fast=20, slow=50),
        RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
    ])

    runs = [
        _run("01 · SMA only",                sma,                          df, args.timeframe),
        _run("02 · RSI only",                rsi,                          df, args.timeframe),
        _run("03 · Vote ensemble",           vote,                         df, args.timeframe),
        _run("04 · Regime-gated",            regime_gated,                 df, args.timeframe),
        _run("05 · Regime + DD breaker",     regime_gated_with_breaker,    df, args.timeframe),
    ]

    print(f"{INK}Out-of-the-box comparison ({len(df)} bars, full sample):{RESET}\n")
    print(f"   {INK_FAINT}{'strategy':<32}{'return':>9}{'sharpe':>10}{'max dd':>9}{'trades':>8}{'win%':>7}{RESET}")
    print(f"   {INK_FAINT}{'─' * 32}{'─' * 9}{'─' * 10}{'─' * 9}{'─' * 8}{'─' * 7}{RESET}")
    for name, m in runs:
        ret_c = _color(m["return"])
        shp_c = _color(m["sharpe"])
        print(
            f"   {INK}{name:<32}{RESET}"
            f"  {ret_c:>17}%"
            f"  {shp_c:>17}"
            f"  {ALERT}{m['max_dd']:>6.1f}%{RESET}"
            f"  {INK}{m['trades']:>6}{RESET}"
            f"  {INK}{m['win_rate']:>5.1f}{RESET}"
        )
    print()

    best = max(runs, key=lambda r: r[1]["sharpe"])
    worst = min(runs, key=lambda r: r[1]["sharpe"])
    print(f"  {SIGNAL}best   {best[0]} (sharpe {best[1]['sharpe']:+.2f}){RESET}")
    print(f"  {ALERT}worst  {worst[0]} (sharpe {worst[1]['sharpe']:+.2f}){RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
