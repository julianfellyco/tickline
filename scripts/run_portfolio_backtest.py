#!/usr/bin/env python3
"""Multi-asset portfolio backtest.

Runs the same primary strategy across multiple symbols, then combines
the sleeves into a portfolio using a sizing method (equal, inverse-vol,
vol-target, or fractional Kelly). Reports per-sleeve contributions and
the realized correlation matrix — the latter is the silent killer of
naive diversification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest import CostModel
from tickline.data import fetch_ohlcv, load_cached
from tickline.portfolio import Portfolio, Sleeve, SizingMethod
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
   │  tick{SIGNAL}/{INK}line {INK_FAINT}portfolio{INK}                       │
   │  {INK_FAINT}multi-asset · sizing · correlation{INK}       │
   └─────────────────────────────────────────┘{RESET}
"""

STRATEGIES = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}


def _color(value: float) -> str:
    if value > 0:
        return f"{SIGNAL}{value:+.2f}{RESET}"
    if value < 0:
        return f"{ALERT}{value:+.2f}{RESET}"
    return f"{INK}{value:+.2f}{RESET}"


def main() -> int:
    p = argparse.ArgumentParser(description="Portfolio backtest")
    p.add_argument(
        "--symbols", nargs="+",
        default=["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        help="symbols to run as sleeves",
    )
    p.add_argument("--strategy", default="sma_crossover", choices=list(STRATEGIES))
    p.add_argument("--method", default="inverse_vol",
                   choices=[m.value for m in SizingMethod])
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--lookback", type=int, default=30)
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    print(BANNER)

    sleeves: list[Sleeve] = []
    for symbol in args.symbols:
        if args.no_fetch:
            df = load_cached(args.exchange, symbol, args.timeframe)
        else:
            df = fetch_ohlcv(symbol, args.timeframe, args.days, args.exchange)
        if df.empty:
            print(f"{ALERT}no data for {symbol} — skipping{RESET}")
            continue
        sleeves.append(Sleeve(symbol, df, STRATEGIES[args.strategy]()))
        print(f"{INK_FAINT}>>{RESET} {symbol:<12} {INK}{len(df)}{RESET} bars")

    if not sleeves:
        print(f"{ALERT}no sleeves loaded{RESET}")
        return 1

    # align sleeves to common index
    common_idx = sleeves[0].ohlcv.index
    for s in sleeves[1:]:
        common_idx = common_idx.intersection(s.ohlcv.index)
    for s in sleeves:
        s.ohlcv = s.ohlcv.loc[common_idx]

    print(f"\n{INK_FAINT}>>{RESET} aligned to {len(common_idx)} common bars\n")

    portfolio = Portfolio(sleeves, initial_capital=args.capital, cost_model=CostModel())
    result = portfolio.run(method=args.method, lookback=args.lookback)
    metrics = compute_metrics(
        result.returns, result.equity_curve,
        # portfolio doesn't have a single trade ledger — pass empty
        __import__("pandas").DataFrame(columns=["pnl_pct"]),
        args.timeframe,
    )

    print(f"{INK}Portfolio result ({args.method}, lookback {args.lookback}):{RESET}")
    print(f"   start    ${args.capital:>10,.2f}")
    print(f"   end      ${result.final_equity:>10,.2f}")
    print(f"   return   {_color(result.total_return_pct)}%")
    print(f"   sharpe   {_color(metrics.sharpe)}")
    print(f"   max dd   {ALERT}{metrics.max_drawdown_pct:.2f}%{RESET}")
    print(f"   vol ann  {INK}{metrics.volatility_pct:.2f}%{RESET}")
    print()

    contribs = result.contributions()
    print(f"{INK}Sleeve contributions to portfolio return (pp):{RESET}")
    for name, contrib in contribs.items():
        sleeve_result = result.sleeve_results[name]
        sleeve_ret = sleeve_result.total_return_pct
        print(
            f"   {INK_FAINT}{name:<12}{RESET} "
            f"standalone {_color(sleeve_ret)}%  "
            f"contribution {_color(float(contrib))}pp"
        )
    print()

    print(f"{INK}Realized sleeve correlation:{RESET}")
    corr = result.correlation
    names = list(corr.columns)
    header_pad = max(len(n) for n in names) + 2
    print(" " * header_pad, end="")
    for n in names:
        print(f"{n:>10}", end="")
    print()
    for row_name in names:
        print(f"  {INK_FAINT}{row_name:<{header_pad - 2}}{RESET}", end="")
        for col_name in names:
            v = corr.loc[row_name, col_name]
            color = AMBER if v > 0.7 and row_name != col_name else INK_DIM
            print(f"{color}{v:>10.2f}{RESET}", end="")
        print()
    print()

    max_off = corr.where(~__import__("numpy").eye(len(names), dtype=bool)).abs().max().max()
    if max_off > 0.7:
        print(f"  {AMBER}⚠ highest off-diagonal correlation = {max_off:.2f}.{RESET}")
        print(f"  {AMBER}  These sleeves move together — diversification is weaker than it looks.{RESET}")
    else:
        print(f"  {SIGNAL}✓ all pairwise correlations < 0.7 — diversification looks real.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
