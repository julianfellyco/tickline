#!/usr/bin/env python3
"""Stack improvements one at a time and measure each layer's lift.

For SMA crossover (the strategy that's been failing the hardest):

   01  SMA only                                  ← baseline
   02  SMA + HTF trend filter                    ← only trade with 4h trend
   03  SMA + ATR exits                           ← stop-loss + take-profit
   04  SMA + HTF filter + ATR exits              ← stacked
   05  Algo+AI                                   ← ML gate baseline (OOS test set)
   06  Algo+AI + HTF filter                      ← gated AI
   07  Algo+AI + HTF filter + ATR exits          ← every lever stacked

This is the honest scoreboard for "lever #1 + lever #2".
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
from tickline.strategies import (
    HigherTimeframeFilter,
    RSIMeanReversion,
    SMACrossover,
    StopAndTarget,
)

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}layer stack{INK}                     │
   │  {INK_FAINT}does adding levers actually compound?{INK}    │
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
    p = argparse.ArgumentParser(description="Stacked-layer comparison")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--htf-multiplier", type=int, default=4, help="bars per HTF bar (1h × 4 = 4h)")
    p.add_argument("--htf-sma", type=int, default=50)
    p.add_argument("--htf-mode", default="strict", choices=["strict", "long-only"])
    p.add_argument("--stop-atr", type=float, default=1.0)
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
    print(f"{INK_FAINT}>>{RESET} HTF: {args.htf_multiplier}× · sma={args.htf_sma} · mode={args.htf_mode}")
    print(f"{INK_FAINT}>>{RESET} ATR: stop={args.stop_atr}× · target={args.target_atr}× · win={args.atr_window}\n")

    def htf(s):
        return HigherTimeframeFilter(s, args.htf_multiplier, args.htf_sma, args.htf_mode)

    def exits(s):
        return StopAndTarget(s, args.stop_atr, args.target_atr, args.atr_window)

    runs = []

    runs.append(_run("01 · SMA only",                        SMACrossover(20, 50),                                     df, args.timeframe))
    runs.append(_run("02 · SMA + HTF filter",                htf(SMACrossover(20, 50)),                                df, args.timeframe))
    runs.append(_run("03 · SMA + ATR exits",                 exits(SMACrossover(20, 50)),                              df, args.timeframe))
    runs.append(_run("04 · SMA + HTF + exits",               exits(htf(SMACrossover(20, 50))),                         df, args.timeframe))

    # AI path on the out-of-sample slice
    n_train = int(len(df) * args.train_fraction)
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]
    meta = MetaLabeler(SMACrossover(20, 50), threshold=args.meta_threshold)
    try:
        meta.fit(train_df)
        ai_ok = True
    except ValueError as exc:
        print(f"{ALERT}meta-labeler skipped: {exc}{RESET}")
        ai_ok = False

    if ai_ok:
        runs.append(_run("05 · algo+AI (OOS test)",          meta,                                                  test_df, args.timeframe))
        runs.append(_run("06 · algo+AI + HTF",               htf(meta),                                             test_df, args.timeframe))
        runs.append(_run("07 · algo+AI + HTF + exits",       exits(htf(meta)),                                      test_df, args.timeframe))

    # also a RSI lane for completeness
    runs.append(_run("08 · RSI only",                        RSIMeanReversion(14, 30.0, 55.0),                         df, args.timeframe))
    runs.append(_run("09 · RSI + ATR exits",                 exits(RSIMeanReversion(14, 30.0, 55.0)),                  df, args.timeframe))

    # render
    print(f"{INK}Side-by-side ({args.symbol} {args.timeframe}):{RESET}\n")
    print(
        f"   {INK_FAINT}{'strategy':<38}"
        f"{'return':>9}{'sharpe':>9}{'max dd':>9}{'trades':>8}{'win%':>8}{'PF':>8}{RESET}"
    )
    print(f"   {INK_FAINT}{'─' * 38}{'─' * 9}{'─' * 9}{'─' * 9}{'─' * 8}{'─' * 8}{'─' * 8}{RESET}")
    for r in runs:
        ret_c = _color(r["return_pct"])
        shp_c = _color(r["sharpe"])
        pf_signed = r["profit_factor"] - 1.0
        pf_c = _color(pf_signed)
        pf_str = f"{r['profit_factor']:.2f}" if r["profit_factor"] != float("inf") else "∞"
        print(
            f"   {INK}{r['name']:<38}{RESET}"
            f"  {ret_c:>17}%"
            f"  {shp_c:>17}"
            f"  {ALERT}{r['max_dd_pct']:>6.1f}%{RESET}"
            f"  {INK}{r['trades']:>6}{RESET}"
            f"  {INK}{r['win_rate']:>6.1f}{RESET}"
            f"  {pf_c:>17}"
        )
    print()

    print(f"{INK}Lifts:{RESET}")
    def lift(label, a, b):
        d_pf = runs[b]["profit_factor"] - runs[a]["profit_factor"]
        d_wr = runs[b]["win_rate"] - runs[a]["win_rate"]
        d_ret = runs[b]["return_pct"] - runs[a]["return_pct"]
        pf_color = SIGNAL if d_pf > 0 else ALERT
        print(
            f"  {INK_FAINT}{label:<36}{RESET}"
            f"  ΔPF {pf_color}{d_pf:+.2f}{RESET}"
            f"  ΔWR {INK}{d_wr:+.1f}pp{RESET}"
            f"  Δret {_color(d_ret)}pp"
        )

    lift("SMA → +HTF",                   0, 1)
    lift("SMA → +exits",                 0, 2)
    lift("SMA → +HTF +exits",            0, 3)
    if ai_ok:
        lift("AI → +HTF",                4, 5)
        lift("AI → +HTF +exits",         4, 6)
        lift("RSI → +exits",             7, 8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
