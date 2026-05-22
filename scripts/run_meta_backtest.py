#!/usr/bin/env python3
"""Run the algo-only vs algo+AI backtest comparison.

Trains the meta-labeler on the first 70% of data, then evaluates two
strategies on the held-out 30%:

  1. Primary algo (e.g. SMA crossover) alone
  2. Primary algo + meta-labeler gate (algo + ML filter)

The diff is the AI overlay's contribution — could be positive, zero,
or negative. Either answer is honest.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest import Backtester, CostModel
from tickline.data import fetch_ohlcv, load_cached
from tickline.intelligence import MetaLabeler
from tickline.risk import compute_metrics
from tickline.strategies import RSIMeanReversion, SMACrossover

RESET = "\033[0m"
SIGNAL = "\033[38;2;0;255;157m"
ALERT = "\033[38;2;255;77;109m"
INK_DIM = "\033[38;2;139;150;165m"
INK_FAINT = "\033[38;2;90;101;115m"
INK = "\033[38;2;232;238;245m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}meta-label{INK}                      │
   │  {INK_FAINT}algo only  vs  algo + AI gate{INK}            │
   └─────────────────────────────────────────┘{RESET}
"""

FACTORIES = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}


def _color(value: float) -> str:
    if value > 0:
        return f"{SIGNAL}{value:+.2f}{RESET}"
    if value < 0:
        return f"{ALERT}{value:+.2f}{RESET}"
    return f"{INK}{value:+.2f}{RESET}"


def _print_metrics(label: str, metrics) -> None:
    print(f"  {INK}{label}{RESET}")
    print(f"    return     {_color(metrics.total_return_pct)}%")
    print(f"    sharpe     {_color(metrics.sharpe)}")
    print(f"    max dd     {ALERT}{metrics.max_drawdown_pct:.2f}%{RESET}")
    print(f"    trades     {metrics.num_trades}")
    print(f"    win rate   {metrics.win_rate_pct:.1f}%")
    print(f"    profit fac {metrics.profit_factor:.2f}")


def main() -> int:
    p = argparse.ArgumentParser(description="Algo vs algo+AI backtest")
    p.add_argument("--primary", default="sma_crossover", choices=list(FACTORIES))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--train-fraction", type=float, default=0.7)
    p.add_argument("--threshold", type=float, default=0.55,
                   help="ML probability threshold to take a trade (0-1)")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    print(BANNER)
    if args.no_fetch:
        df = load_cached(args.exchange, args.symbol, args.timeframe)
        if df.empty:
            print("no cached data — run scripts/fetch_data.py first")
            return 1
    else:
        df = fetch_ohlcv(args.symbol, args.timeframe, args.days, args.exchange)

    n = len(df)
    n_train = int(n * args.train_fraction)
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]
    print(f"{INK_FAINT}>>{RESET} train: {len(train_df)} bars "
          f"({train_df.index[0].date()} → {train_df.index[-1].date()})")
    print(f"{INK_FAINT}>>{RESET} test:  {len(test_df)} bars "
          f"({test_df.index[0].date()} → {test_df.index[-1].date()})\n")

    # Fit meta-labeler
    primary_for_meta = FACTORIES[args.primary]()
    meta = MetaLabeler(primary_for_meta, threshold=args.threshold)
    print(f"{INK_FAINT}>>{RESET} training meta-labeler...")
    info = meta.fit(train_df)
    print(f"    train signals  {info.n_train_signals}")
    print(f"    train AUC      {info.train_auc:.3f}   (>0.5 = informative)")
    print(f"    test AUC       {info.test_auc:.3f}")
    print(f"    base win rate  {info.base_rate * 100:.1f}%")
    print(f"    top features:")
    for name, imp in info.feature_importance.head(5).items():
        bar = "█" * int(max(0, imp) * 80)
        print(f"      {INK_FAINT}{name:14}{RESET} {bar} {imp:+.4f}")
    print()

    # Evaluate both strategies on test set
    cost_model = CostModel()
    bt = Backtester(initial_capital=10_000, cost_model=cost_model)

    primary_only = FACTORIES[args.primary]()
    algo_result = bt.run(test_df, primary_only)
    algo_metrics = compute_metrics(
        algo_result.returns, algo_result.equity_curve, algo_result.trades, args.timeframe
    )

    meta_result = bt.run(test_df, meta)
    meta_metrics = compute_metrics(
        meta_result.returns, meta_result.equity_curve, meta_result.trades, args.timeframe
    )

    print(f"{INK}Out-of-sample comparison ({len(test_df)} bars):{RESET}\n")
    _print_metrics("algo only", algo_metrics)
    print()
    _print_metrics(f"algo + AI gate (threshold={args.threshold})", meta_metrics)
    print()

    diff_ret = meta_metrics.total_return_pct - algo_metrics.total_return_pct
    diff_sharpe = meta_metrics.sharpe - algo_metrics.sharpe
    diff_trades = meta_metrics.num_trades - algo_metrics.num_trades

    print(f"{INK}Delta (AI gate − algo only):{RESET}")
    print(f"  return    {_color(diff_ret)}%")
    print(f"  sharpe    {_color(diff_sharpe)}")
    print(f"  trades    {diff_trades:+d} "
          f"({INK_FAINT}AI filtered out "
          f"{max(0, -diff_trades)} signals{RESET})")
    print()
    if diff_sharpe > 0.1:
        print(f"  {SIGNAL}✓ AI gate added value out-of-sample.{RESET}")
    elif diff_sharpe < -0.1:
        print(f"  {ALERT}✗ AI gate hurt performance out-of-sample. Honest finding.{RESET}")
    else:
        print(f"  {INK_DIM}≈ AI gate was effectively neutral.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
