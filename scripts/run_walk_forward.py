#!/usr/bin/env python3
"""Run a walk-forward validation of a strategy.

Compares in-sample (single full backtest) vs walk-forward aggregate so the
overfit gap is visible. If they diverge, the in-sample number is fiction.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest import Backtester, CostModel, run_walk_forward
from tickline.data import fetch_ohlcv, load_cached
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
   │  tick{SIGNAL}/{INK}line {INK_FAINT}walk-forward{INK}                    │
   │  {INK_FAINT}in-sample vs out-of-sample, side by side{INK}  │
   └─────────────────────────────────────────┘{RESET}
"""

FACTORIES = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}


def _color(value: float, neutral_zero: bool = True) -> str:
    if value > 0:
        return f"{SIGNAL}{value:+.2f}{RESET}"
    if value < 0:
        return f"{ALERT}{value:+.2f}{RESET}"
    return f"{INK}{0.0 if neutral_zero else value:+.2f}{RESET}"


def main() -> int:
    p = argparse.ArgumentParser(description="Walk-forward validation")
    p.add_argument("--strategy", default="sma_crossover", choices=list(FACTORIES))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--train-bars", type=int, default=2000)
    p.add_argument("--test-bars", type=int, default=1000)
    p.add_argument("--mode", choices=["anchored", "rolling"], default="anchored")
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

    print(f"{INK_FAINT}>>{RESET} {len(df)} bars from {df.index[0]} to {df.index[-1]}\n")

    # In-sample full backtest
    is_strategy = FACTORIES[args.strategy]()
    is_bt = Backtester(cost_model=CostModel()).run(df, is_strategy)
    is_metrics = compute_metrics(
        is_bt.returns, is_bt.equity_curve, is_bt.trades, args.timeframe
    )

    # Walk-forward
    print(f"{INK_FAINT}>>{RESET} Running walk-forward "
          f"({args.mode}, train={args.train_bars} test={args.test_bars})...\n")
    wf = run_walk_forward(
        df,
        strategy_factory=FACTORIES[args.strategy],
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        mode=args.mode,
        timeframe=args.timeframe,
    )

    summary = wf.summary()
    print(f"{INK}Per-window test results:{RESET}")
    if not summary.empty:
        for _, row in summary.iterrows():
            print(
                f"  w{int(row['window']):>2} "
                f"{INK_FAINT}{row['test_start']} → {row['test_end']}{RESET}  "
                f"ret={_color(row['return_pct'])}%  "
                f"sharpe={_color(row['sharpe'])}  "
                f"dd={ALERT}{row['max_dd_pct']:.1f}%{RESET}  "
                f"trades={int(row['trades']):>3}"
            )
    print()
    print(f"{INK}Comparison:{RESET}")
    print(f"  in-sample      sharpe={_color(is_metrics.sharpe)}  "
          f"return={_color(is_metrics.total_return_pct)}%")
    print(f"  walk-forward   sharpe={_color(wf.aggregate_sharpe())}  "
          f"return={_color(wf.aggregate_return_pct())}%  "
          f"(mean across {len(wf.windows)} test windows)")
    print(f"  consistency    {wf.sharpe_consistency() * 100:.0f}% of windows had positive Sharpe")

    gap = is_metrics.sharpe - wf.aggregate_sharpe()
    print()
    if gap > 0.5:
        print(f"  {ALERT}⚠ overfit gap of {gap:.2f} between in-sample and walk-forward Sharpe.{RESET}")
        print(f"  {ALERT}  The in-sample number is misleading.{RESET}")
    else:
        print(f"  {SIGNAL}✓ in-sample and walk-forward agree (gap {gap:+.2f}).{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
