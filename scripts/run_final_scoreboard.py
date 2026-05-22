#!/usr/bin/env python3
"""Final scoreboard — every strategy and wrapper combination measured.

A single CLI that exercises the full strategy library (SMA, RSI, Donchian),
all three wrappers (HTF filter, ATR exits, vol-target), and the
meta-labeler (with the expanded feature set). Sorted by Sharpe at the end
so the best system is unambiguous.
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
    DonchianBreakout,
    HigherTimeframeFilter,
    RSIMeanReversion,
    SMACrossover,
    StopAndTarget,
    VolatilityTargeted,
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
   │  tick{SIGNAL}/{INK}line {INK_FAINT}final scoreboard{INK}                │
   │  {INK_FAINT}every strategy × every wrapper{INK}           │
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
    p = argparse.ArgumentParser(description="Full scoreboard")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--meta-threshold", type=float, default=0.30)
    p.add_argument("--train-fraction", type=float, default=0.7)
    args = p.parse_args()

    print(BANNER)
    df = load_cached(args.exchange, args.symbol, args.timeframe)
    if df.empty:
        print(f"{ALERT}no cached data{RESET}")
        return 1
    print(f"{INK_FAINT}>>{RESET} {len(df)} bars  ({df.index[0].date()} → {df.index[-1].date()})\n")

    def htf(s):
        return HigherTimeframeFilter(s, multiplier=4, sma_period=50, mode="strict")

    def exits(s):
        return StopAndTarget(s, stop_atr=1.0, target_atr=3.0)

    def vt(s):
        return VolatilityTargeted(s, target_annual_vol=0.15, lookback=20)

    runs = []

    # ── full-sample strategies ────────────────────────────────────────
    full_sample = [
        ("SMA only",                      SMACrossover(20, 50)),
        ("SMA + HTF",                     htf(SMACrossover(20, 50))),
        ("SMA + HTF + exits",             exits(htf(SMACrossover(20, 50)))),
        ("SMA + HTF + vol-target",        vt(htf(SMACrossover(20, 50)))),
        ("RSI only",                      RSIMeanReversion(14, 30.0, 55.0)),
        ("RSI + exits (1.0/3.0)",         exits(RSIMeanReversion(14, 30.0, 55.0))),
        ("Donchian (20/10)",              DonchianBreakout(20, 10)),
        ("Donchian + HTF",                htf(DonchianBreakout(20, 10))),
        ("Donchian + HTF + vol-target",   vt(htf(DonchianBreakout(20, 10)))),
        ("Donchian + HTF + exits",        exits(htf(DonchianBreakout(20, 10)))),
    ]
    for name, strat in full_sample:
        runs.append(_run(name, strat, df, args.timeframe))

    # ── meta-labeler path (out-of-sample test slice) ──────────────────
    n_train = int(len(df) * args.train_fraction)
    train_df = df.iloc[:n_train]
    test_df = df.iloc[n_train:]

    primary = SMACrossover(20, 50)
    meta = MetaLabeler(primary, threshold=args.meta_threshold)
    try:
        info = meta.fit(train_df)
        meta_ok = True
        print(f"{INK_FAINT}>>{RESET} meta-labeler trained · train AUC {INK}{info.train_auc:.3f}{RESET} · test AUC {INK}{info.test_auc:.3f}{RESET}")
        print(f"{INK_FAINT}>>{RESET} top 3 features: {INK}{', '.join(info.feature_importance.head(3).index)}{RESET}\n")
    except ValueError as exc:
        print(f"{ALERT}meta-labeler skipped: {exc}{RESET}")
        meta_ok = False

    if meta_ok:
        ai_runs = [
            ("AI (OOS test)",                          meta),
            ("AI + HTF",                               htf(meta)),
            ("AI + HTF + vol-target",                  vt(htf(meta))),
            ("AI + HTF + exits",                       exits(htf(meta))),
        ]
        for name, strat in ai_runs:
            runs.append(_run(name, strat, test_df, args.timeframe))

    # ── render, sorted by sharpe ──────────────────────────────────────
    runs_sorted = sorted(runs, key=lambda r: r["sharpe"], reverse=True)
    print(f"{INK}Sorted by Sharpe (desc):{RESET}\n")
    print(
        f"   {INK_FAINT}{'#':>3}  {'strategy':<38}"
        f"{'return':>10}{'sharpe':>9}{'max dd':>9}{'trades':>8}{'win%':>8}{'PF':>8}{RESET}"
    )
    print(f"   {INK_FAINT}{'─' * 3}  {'─' * 38}{'─' * 10}{'─' * 9}{'─' * 9}{'─' * 8}{'─' * 8}{'─' * 8}{RESET}")
    for rank, r in enumerate(runs_sorted, 1):
        ret_c = _color(r["return_pct"])
        shp_c = _color(r["sharpe"])
        pf_signed = r["profit_factor"] - 1.0
        pf_c = _color(pf_signed)
        prefix_color = SIGNAL if rank == 1 else (AMBER if rank <= 3 else INK_FAINT)
        print(
            f"   {prefix_color}{rank:>3}{RESET}  {INK}{r['name']:<38}{RESET}"
            f"  {ret_c:>17}%"
            f"  {shp_c:>17}"
            f"  {ALERT}{r['max_dd_pct']:>6.1f}%{RESET}"
            f"  {INK}{r['trades']:>6}{RESET}"
            f"  {INK}{r['win_rate']:>6.1f}{RESET}"
            f"  {pf_c:>17}"
        )
    print()
    best = runs_sorted[0]
    print(f"{SIGNAL}★ best:{RESET}  {INK}{best['name']}{RESET}  ·  "
          f"sharpe {SIGNAL}{best['sharpe']:+.2f}{RESET}  ·  "
          f"PF {SIGNAL}{best['profit_factor']:.2f}{RESET}  ·  "
          f"WR {INK}{best['win_rate']:.1f}%{RESET}  ·  "
          f"return {_color(best['return_pct'])}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
