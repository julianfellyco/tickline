#!/usr/bin/env python3
"""Signal-validation backtest for the AI theme state machine.

Event study, NOT a PnL backtest. Tests whether the market-only rotation
states actually separate forward excess returns (theme basket minus SPY)
across ~6 years and multiple regimes.

    python scripts/run_watchlist_backtest.py            # fetch ~6y, both tiers
    python scripts/run_watchlist_backtest.py --no-fetch # use cached parquet

Read the verdict with the caveats it prints. A clean separation here is
necessary but NOT sufficient to trade — it is one validation cut.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.data import fetch_many
from tickline.themes import AI_THEMES, BENCHMARK, FAST, SLOW
from tickline.themes.backtest import (
    build_panel,
    cross_sectional_by_state,
    cross_sectional_rank_buckets,
    long_short_spread,
    summarize_by_state,
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
   │  tick{SIGNAL}/{INK}line {INK_FAINT}watchlist · backtest{INK}            │
   │  {INK_FAINT}does the state machine actually work?{INK}     │
   └─────────────────────────────────────────┘{RESET}
"""

STATE_ORDER = ["emerging", "dormant", "rolling_over"]
STATE_COLOR = {"emerging": SIGNAL, "dormant": INK_DIM, "rolling_over": ALERT}
TIERS = {"fast": (FAST, (5, 21)), "slow": (SLOW, (21, 63))}


def _pct(x) -> str:
    return f"{x * 100:+.2f}%"


def _buckets_line(buckets, label):
    if buckets.empty:
        print(f"   {INK_FAINT}{label}: (insufficient cross-section){RESET}")
        return float("nan")
    cells = []
    for b in buckets.index:
        m = buckets.loc[b, "rel_to_peers"]
        c = SIGNAL if m > 0 else ALERT
        cells.append(f"{c}Q{int(b)+1} {_pct(m)}{RESET}")
    spread = long_short_spread(buckets)
    sc = SIGNAL if spread > 0 else ALERT
    print(f"   {INK_DIM}{label}:{RESET} " + "  ".join(cells)
          + f"   {INK_DIM}L/S{RESET} {sc}{_pct(spread)}{RESET}")
    return spread


def _run_tier(name, panel):
    cfg, horizons = TIERS[name]
    print(f"\n{INK}{name.upper()} tier{RESET} {INK_FAINT}(lookback {cfg.lookback}d, "
          f"slope {cfg.slope_window}d · {len(panel):,} theme-days){RESET}")
    results = []
    for h in horizons:
        print(f"\n  {INK}▸ forward horizon {h} trading days{RESET}")

        # Absolute vs SPY — shown only to expose the AI-beta trap.
        summ = summarize_by_state(panel, h)
        abs_means = "  ".join(
            f"{STATE_COLOR.get(s, INK)}{s} {_pct(summ.loc[s, 'mean_excess'])}{RESET}"
            for s in STATE_ORDER if s in summ.index
        )
        print(f"   {INK_FAINT}absolute vs SPY (beta trap — all positive):{RESET} {abs_means}")

        # Cross-sectional — the honest test (AI-beta removed).
        xs = cross_sectional_by_state(panel, h)
        xs_line = "  ".join(
            f"{STATE_COLOR.get(s, INK)}{s} {_pct(xs.loc[s, 'rel_to_peers'])}{RESET}"
            for s in STATE_ORDER if s in xs.index
        )
        print(f"   {INK}cross-sectional, vs peers:{RESET} {xs_line}")

        slope_ls = _buckets_line(
            cross_sectional_rank_buckets(panel, h, "slope_z", 5), "by slope-z rank   (what I built)")
        level_ls = _buckets_line(
            cross_sectional_rank_buckets(panel, h, "rel_strength", 5), "by rel-str LEVEL  (momentum) ")
        results.append((h, slope_ls, level_ls))
    return results


def _verdict(all_results):
    flat = [r for rs in all_results.values() for r in rs]
    slope_pos = sum(1 for _, s, _ in flat if s > 0)
    level_pos = sum(1 for _, _, l in flat if l > 0)
    n = len(flat)
    avg_level = sum(l for _, _, l in flat) / n
    avg_slope = sum(s for _, s, _ in flat) / n
    print(f"\n{INK}{'═' * 62}{RESET}")
    print(f"{INK}VERDICT{RESET}  {INK_DIM}(cross-sectional long/short, AI-beta removed){RESET}\n")
    print(f"   slope-z (what the state machine uses): positive L/S in "
          f"{slope_pos}/{n} cuts · avg {_pct(avg_slope)}")
    print(f"   rel-str LEVEL (cross-sectional momentum): positive L/S in "
          f"{level_pos}/{n} cuts · avg {_pct(avg_level)}")
    if level_pos >= n - 1 and avg_level > avg_slope and avg_level > 0:
        print(f"\n   {SIGNAL}→ The edge lives in the LEVEL, not the acceleration. The "
              f"state machine keys off the wrong variable.{RESET}")
        print(f"   {AMBER}   FIX: classify on cross-sectional rel-strength RANK, not slope-z.{RESET}")
        print(f"   {INK_DIM}   Still needs: costs, borrow, non-overlap, regime split, OOS "
              f"before any capital.{RESET}")
    else:
        print(f"\n   {ALERT}→ no reliable cross-sectional edge in either signal.{RESET}")
    print(f"{INK}{'═' * 62}{RESET}")


def main() -> int:
    p = argparse.ArgumentParser(description="Theme state-machine signal validation")
    p.add_argument("--days", type=int, default=2200)  # ~6y, yfinance daily cap
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    print(BANNER)
    symbols = all_tickers()
    print(f"{INK_FAINT}>>{RESET} fetching {len(symbols)} symbols, ~{args.days // 252}y history…")
    frames = fetch_many(symbols, days=args.days, use_cache=not args.no_fetch)
    if BENCHMARK not in frames:
        print(f"{ALERT}benchmark {BENCHMARK} unavailable{RESET}")
        return 1
    bench_ret = frames[BENCHMARK]["close"].pct_change()
    span = frames[BENCHMARK].index
    print(f"{INK_FAINT}>>{RESET} {len(frames)} symbols · "
          f"{SIGNAL}{span[0].date()} → {span[-1].date()}{RESET} "
          f"({len(span):,} bars)\n")

    all_results = {}
    for name in TIERS:
        cfg, horizons = TIERS[name]
        panel = build_panel(AI_THEMES, frames, bench_ret, cfg, horizons)
        all_results[name] = _run_tier(name, panel)

    _verdict(all_results)
    print(f"\n{INK_FAINT}reminder: ~6y is ONE AI super-cycle + one bear. Themes share "
          f"tickers (correlated). Treat as suggestive, not proof.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
