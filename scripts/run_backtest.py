#!/usr/bin/env python3
"""Run a strategy backtest against cached data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest import Backtester, CostModel
from tickline.data import fetch_ohlcv
from tickline.risk import compute_metrics
from tickline.strategies import RSIMeanReversion, SMACrossover, StopAndTarget

# ANSI palette aligned with BRAND.md
RESET = "\033[0m"
SIGNAL = "\033[38;2;0;255;157m"
ALERT = "\033[38;2;255;77;109m"
INK_DIM = "\033[38;2;139;150;165m"
INK_FAINT = "\033[38;2;90;101;115m"
INK = "\033[38;2;232;238;245m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line                                 │
   │  {INK_FAINT}honest curves from real ticks{INK}          │
   └─────────────────────────────────────────┘{RESET}
"""

STRATEGY_REGISTRY = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}


def _color_pct(value: float) -> str:
    if value > 0:
        return f"{SIGNAL}{value:+.2f}%{RESET}"
    if value < 0:
        return f"{ALERT}{value:+.2f}%{RESET}"
    return f"{INK}{value:+.2f}%{RESET}"


def main() -> int:
    p = argparse.ArgumentParser(description="Run a backtest")
    p.add_argument("--strategy", default="sma_crossover", choices=list(STRATEGY_REGISTRY))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--fee-bps", type=float, default=10.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--no-fetch", action="store_true", help="use cache only, never hit exchange")
    p.add_argument("--atr-stop", type=float, default=None,
                   help="wrap strategy with ATR-scaled stop-loss (e.g. 2.0)")
    p.add_argument("--atr-target", type=float, default=None,
                   help="wrap strategy with ATR-scaled take-profit (e.g. 3.0)")
    p.add_argument("--atr-window", type=int, default=14)
    args = p.parse_args()

    print(BANNER)
    print(f"{INK_FAINT}>>{RESET} Loading {INK}{args.symbol}{RESET} {INK_DIM}{args.timeframe}{RESET} data...")
    if args.no_fetch:
        from tickline.data import load_cached
        df = load_cached(args.exchange, args.symbol, args.timeframe)
        if df.empty:
            print("no cached data, run scripts/fetch_data.py first")
            return 1
    else:
        df = fetch_ohlcv(args.symbol, args.timeframe, args.days, args.exchange)

    print(f"   {len(df)} candles, {df.index[0]} -> {df.index[-1]}")

    strategy = STRATEGY_REGISTRY[args.strategy]()
    if args.atr_stop is not None or args.atr_target is not None:
        strategy = StopAndTarget(
            primary=strategy,
            stop_atr=args.atr_stop if args.atr_stop is not None else 2.0,
            target_atr=args.atr_target if args.atr_target is not None else 3.0,
            atr_window=args.atr_window,
        )
    print(f"\n>> Running strategy: {strategy.name}")

    bt = Backtester(
        initial_capital=args.capital,
        cost_model=CostModel(fee_bps=args.fee_bps, slippage_bps=args.slippage_bps),
    )
    result = bt.run(df, strategy)

    metrics = compute_metrics(result.returns, result.equity_curve, result.trades, args.timeframe)

    print(f"\n>> Results")
    print(f"   Start capital: ${args.capital:,.2f}")
    print(f"   End capital:   ${result.final_equity:,.2f}")
    print(f"   Net pnl:       ${result.final_equity - args.capital:+,.2f}")
    print(f"\n>> Performance metrics")
    print(metrics.as_table())

    buy_hold_return = (df["close"].iloc[-1] / df["close"].iloc[0] - 1.0) * 100.0
    print(f"\n{INK_FAINT}>>{RESET} Benchmark")
    print(f"   Buy-and-hold: {_color_pct(buy_hold_return)}   Strategy: {_color_pct(metrics.total_return_pct)}")

    if metrics.total_return_pct > buy_hold_return:
        print(f"   {SIGNAL}✓ Strategy outperformed buy-and-hold (after costs){RESET}")
    else:
        print(f"   {ALERT}✗ Strategy underperformed buy-and-hold{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
