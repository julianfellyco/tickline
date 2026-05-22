#!/usr/bin/env python3
"""ATR-exit comparison.

Runs each baseline strategy with and without ATR-scaled stop-loss /
take-profit, then runs the algo+AI meta-labeler the same way. Prints
a single side-by-side table so the lift (if any) from explicit exits
is unambiguous.

Intent: prove or disprove the claim that adding stops+targets to a
mediocre signal is the single biggest profit-factor lever on offer.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest import Backtester, CostModel
from tickline.data import load_cached
from tickline.intelligence import MetaLabeler
from tickline.risk import compute_metrics
from tickline.strategies import RSIMeanReversion, SMACrossover, StopAndTarget

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}exit comparison{INK}                │
   │  {INK_FAINT}does ATR stop+target lift profit factor?{INK} │
   └─────────────────────────────────────────┘{RESET}
"""


def _color(v: float) -> str:
    if v > 0:
        return f"{SIGNAL}{v:+.2f}{RESET}"
    if v < 0:
        return f"{ALERT}{v:+.2f}{RESET}"
    return f"{INK}{v:+.2f}{RESET}"


def _run(name, strategy, df, timeframe):
    bt = Backtester(initial_capital=10_000.0, cost_model=CostModel())
    result = bt.run(df, strategy)
    m = compute_metrics(result.returns, result.equity_curve, result.trades, timeframe)
    return {
        "name": name,
        "return_pct": m.total_return_pct,
        "sharpe": m.sharpe,
        "max_dd_pct": m.max_drawdown_pct,
        "trades": m.num_trades,
        "win_rate": m.win_rate_pct,
        "profit_factor": m.profit_factor,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Compare strategies with/without ATR exits")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--stop-atr", type=float, default=2.0)
    p.add_argument("--target-atr", type=float, default=3.0)
    p.add_argument("--atr-window", type=int, default=14)
    p.add_argument("--meta-threshold", type=float, default=0.30)
    p.add_argument("--train-fraction", type=float, default=0.7)
    args = p.parse_args()

    print(BANNER)

    df = load_cached(args.exchange, args.symbol, args.timeframe)
    if df.empty:
        print(f"{ALERT}no cached data{RESET}")
        return 1
    print(f"{INK_FAINT}>>{RESET} {len(df)} bars  ({df.index[0].date()} → {df.index[-1].date()})")
    print(f"{INK_FAINT}>>{RESET} ATR exits: stop={args.stop_atr}× · target={args.target_atr}× · window={args.atr_window}\n")

    runs = []

    def factory(strat):
        return StopAndTarget(strat, args.stop_atr, args.target_atr, args.atr_window)

    # baselines
    runs.append(_run("01 · SMA only",               SMACrossover(20, 50),                      df, args.timeframe))
    runs.append(_run("02 · SMA + exits",            factory(SMACrossover(20, 50)),             df, args.timeframe))
    runs.append(_run("03 · RSI only",               RSIMeanReversion(14, 30.0, 55.0),          df, args.timeframe))
    runs.append(_run("04 · RSI + exits",            factory(RSIMeanReversion(14, 30.0, 55.0)), df, args.timeframe))

    # meta-labeler train/test split
    n_train = int(len(df) * args.train_fraction)
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]

    primary = SMACrossover(20, 50)
    meta = MetaLabeler(primary, threshold=args.meta_threshold)
    try:
        meta.fit(train_df)
        meta_runs_ok = True
    except ValueError as e:
        print(f"{ALERT}meta-labeler skipped: {e}{RESET}")
        meta_runs_ok = False

    if meta_runs_ok:
        runs.append(_run("05 · algo+AI (test 30%)",          meta,           test_df, args.timeframe))
        runs.append(_run("06 · algo+AI + exits (test 30%)",  factory(meta),  test_df, args.timeframe))

    # render
    print(f"{INK}Side-by-side ({args.symbol} {args.timeframe}):{RESET}\n")
    print(
        f"   {INK_FAINT}{'strategy':<34}"
        f"{'return':>9}{'sharpe':>9}{'max dd':>9}{'trades':>8}{'win%':>8}{'PF':>8}{RESET}"
    )
    print(f"   {INK_FAINT}{'─' * 34}{'─' * 9}{'─' * 9}{'─' * 9}{'─' * 8}{'─' * 8}{'─' * 8}{RESET}")
    for r in runs:
        ret_c = _color(r["return_pct"])
        shp_c = _color(r["sharpe"])
        pf_c = _color(r["profit_factor"] - 1.0)  # color relative to break-even
        pf_str = f"{r['profit_factor']:.2f}" if r["profit_factor"] != float("inf") else "∞"
        print(
            f"   {INK}{r['name']:<34}{RESET}"
            f"  {ret_c:>17}%"
            f"  {shp_c:>17}"
            f"  {ALERT}{r['max_dd_pct']:>6.1f}%{RESET}"
            f"  {INK}{r['trades']:>6}{RESET}"
            f"  {INK}{r['win_rate']:>6.1f}{RESET}"
            f"  {pf_c:>17}"
        )
    print()

    # pairwise lifts
    def lift(a, b, key):
        return runs[b][key] - runs[a][key]

    def line(label, a, b):
        d_pf = lift(a, b, "profit_factor")
        d_wr = lift(a, b, "win_rate")
        d_ret = lift(a, b, "return_pct")
        pf_color = SIGNAL if d_pf > 0 else ALERT
        print(
            f"  {INK_FAINT}{label:<28}{RESET}"
            f"  ΔPF {pf_color}{d_pf:+.2f}{RESET}"
            f"  ΔWR {INK}{d_wr:+.1f}pp{RESET}"
            f"  Δreturn {_color(d_ret)}pp"
        )

    print(f"{INK}Lift from adding ATR exits:{RESET}")
    line("SMA  →  SMA + exits", 0, 1)
    line("RSI  →  RSI + exits", 2, 3)
    if meta_runs_ok:
        line("AI   →  AI + exits", 4, 5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
