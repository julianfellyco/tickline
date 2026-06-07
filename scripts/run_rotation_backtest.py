#!/usr/bin/env python3
"""Cost-aware long/short validation of theme rotation.

Trades the validated signal (cross-sectional rel-strength LEVEL): long the
strongest themes, short the weakest, dollar-neutral, net of transaction
costs and short borrow. Compares against the slope/acceleration signal,
splits performance by year (regime robustness), and sweeps costs to show
where the edge dies.

    python scripts/run_rotation_backtest.py            # fetch ~6y
    python scripts/run_rotation_backtest.py --no-fetch # cached parquet

A positive NET Sharpe that survives 2022 and realistic costs is the bar.
Anything less is not tradeable, however pretty the gross number.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.data import fetch_many
from tickline.themes import AI_THEMES, ALL_THEMES, BENCHMARK, SLOW
from tickline.themes.rotation_backtest import (
    benchmark_metrics,
    equal_weight_metrics,
    simulate_long_short,
)
from tickline.themes.taxonomy import all_tickers

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}rotation L/S · net of costs{INK}      │
   │  {INK_FAINT}does it survive costs and 2022?{INK}           │
   └─────────────────────────────────────────┘{RESET}
"""


def _pct(x) -> str:
    return f"{x * 100:+.1f}%"


def _col(x) -> str:
    return f"{SIGNAL if x > 0 else ALERT}{_pct(x)}{RESET}"


def _row(label, r):
    print(
        f"   {INK}{label:<22}{RESET}"
        f"{INK_DIM}gross{RESET} {_col(r.gross_ann):>16}   "
        f"{INK}net{RESET} {_col(r.net_ann):>16}   "
        f"{INK_DIM}Sharpe{RESET} {INK}{r.net_sharpe:>5.2f}{RESET}   "
        f"{INK_DIM}maxDD{RESET} {ALERT}{r.net_max_dd * 100:>5.0f}%{RESET}   "
        f"{INK_DIM}hit{RESET} {INK}{r.hit_rate * 100:>3.0f}%{RESET}"
    )


def _per_year(label, r):
    cells = []
    for y in sorted(r.per_year):
        cells.append(f"{INK_DIM}{y}{RESET} {_col(r.per_year[y])}")
    print(f"   {INK_FAINT}{label} by year:{RESET} " + "  ".join(cells))


def main() -> int:
    p = argparse.ArgumentParser(description="Cost-aware rotation long/short")
    p.add_argument("--days", type=int, default=2200)
    p.add_argument("--rebalance", type=int, default=21)
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--bottom", type=int, default=3)
    p.add_argument("--universe", choices=["ai", "all"], default="all",
                   help="ai = validated 10-theme subset · all = full US universe")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    universe = ALL_THEMES if args.universe == "all" else AI_THEMES
    print(BANNER)
    symbols = all_tickers(universe)
    print(f"{INK_FAINT}>>{RESET} universe={SIGNAL}{args.universe}{RESET} "
          f"({len(universe)} themes) · fetching {len(symbols)} symbols, ~{args.days // 252}y…")
    frames = fetch_many(symbols, days=args.days, use_cache=not args.no_fetch)
    if BENCHMARK not in frames:
        print(f"{ALERT}benchmark unavailable{RESET}")
        return 1
    bench_ret = frames[BENCHMARK]["close"].pct_change()
    span = frames[BENCHMARK].index
    print(f"{INK_FAINT}>>{RESET} {len(frames)} symbols · {SIGNAL}{span[0].date()} → "
          f"{span[-1].date()}{RESET} · rebalance {args.rebalance}d · "
          f"long {args.top} / short {args.bottom}\n")

    base = dict(rebalance=args.rebalance, top_n=args.top, bottom_n=args.bottom,
                cost_bps=10.0, borrow_bps_annual=50.0)

    print(f"{INK}Strategy comparison{RESET} {INK_FAINT}(SLOW tier · 10bps/turn cost · "
          f"50bps/yr borrow){RESET}\n")
    level = simulate_long_short(universe, frames, bench_ret, SLOW, signal="level", **base)
    slope = simulate_long_short(universe, frames, bench_ret, SLOW, signal="slope", **base)
    longonly = simulate_long_short(universe, frames, bench_ret, SLOW, signal="level",
                                   long_only=True, **base)
    eqwt = equal_weight_metrics(universe, frames, bench_ret, SLOW, rebalance=args.rebalance)
    spy = benchmark_metrics(bench_ret, rebalance=args.rebalance)
    _row("LONG-ONLY top3", longonly)
    _row("EQ-WT all 37", eqwt)
    _row("SPY buy & hold", spy)
    _row("L/S (short book)", level)
    print(f"\n   {INK_FAINT}long-only turnover {longonly.avg_turnover:.2f} · "
          f"the EQ-WT row is the survivorship-beta control{RESET}\n")

    _per_year("LONG-ONLY net", longonly)
    _per_year("EQ-WT all   ", eqwt)
    _per_year("SPY hold    ", spy)
    print()

    # --- cost sensitivity: where does the LEVEL edge die? --------------------
    print(f"{INK}Cost sensitivity{RESET} {INK_FAINT}(LEVEL signal · net annualized){RESET}\n")
    print(f"   {INK_FAINT}{'cost / borrow':<22}{'net ann':>12}{'Sharpe':>10}{RESET}")
    print(f"   {INK_FAINT}{'─' * 44}{RESET}")
    for cb, bb in [(0.0, 0.0), (5.0, 50.0), (10.0, 50.0), (25.0, 200.0), (50.0, 400.0)]:
        r = simulate_long_short(
            universe, frames, bench_ret, SLOW, signal="level",
            rebalance=args.rebalance, top_n=args.top, bottom_n=args.bottom,
            cost_bps=cb, borrow_bps_annual=bb,
        )
        lbl = f"{cb:.0f}bps / {bb:.0f}bps/yr"
        print(f"   {INK}{lbl:<22}{RESET}{_col(r.net_ann):>20}{INK}{r.net_sharpe:>10.2f}{RESET}")

    # --- verdict: does SELECTION beat the survivorship-beta basket? ----------
    print(f"\n{INK}{'═' * 62}{RESET}")
    print(f"{INK}VERDICT{RESET}  {INK_DIM}— does top-3 SELECTION beat owning all 37?{RESET}\n")
    sel_alpha = longonly.net_ann - eqwt.net_ann
    ppy = 252 / args.rebalance
    nr = longonly.net_returns

    def _ann(s):
        return float(s.mean() * ppy) if len(s) else float("nan")

    def _shp(s):
        return float((s.mean() * ppy) / (s.std() * (ppy ** 0.5))) if len(s) > 1 and s.std() > 0 else float("nan")

    mid = len(nr) // 2
    h1, h2 = nr.iloc[:mid], nr.iloc[mid:]

    print(f"   long-only top3 {_col(longonly.net_ann)}  vs  EQ-WT all 37 {_col(eqwt.net_ann)}  "
          f"vs  SPY {_col(spy.net_ann)}")
    print(f"   {INK}selection alpha (top3 − all): {_col(sel_alpha)}/yr{RESET}  "
          f"{INK_FAINT}Sharpe {longonly.net_sharpe:.2f} vs {eqwt.net_sharpe:.2f}{RESET}")
    print(f"   {INK_DIM}walk-forward:{RESET} 1st half {_col(_ann(h1))} (Sh {_shp(h1):.2f})  ·  "
          f"2nd half {_col(_ann(h2))} (Sh {_shp(h2):.2f})")

    if sel_alpha > 0.10 and longonly.net_sharpe > eqwt.net_sharpe and _shp(h2) > 0.5:
        print(f"\n   {SIGNAL}→ selection beats the winner-basket and holds up out-of-sample. "
              f"The momentum edge is real ON TOP of survivorship (level still inflated).{RESET}")
    elif sel_alpha > 0:
        print(f"\n   {AMBER}→ selection edges the basket but thinly/inconsistently. Most of the "
              f"return is survivorship beta, not skill. Don't trust the headline.{RESET}")
    else:
        print(f"\n   {ALERT}→ picking top-3 does NOT beat owning all 37. The whole '+114%' is "
              f"survivorship — momentum selection adds nothing here.{RESET}")
    print(f"{INK}{'═' * 62}{RESET}")
    print(f"\n{INK_FAINT}EQ-WT all 37 = own every theme equal-weight (captures 'owning the "
          f"winners'). still hindsight universe · no slippage/impact · same-close entry.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
