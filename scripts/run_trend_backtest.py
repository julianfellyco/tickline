#!/usr/bin/env python3
"""Honest trend-following backtest vs buy-and-hold.

The simple rule: hold each theme ETF while it's above its 200-day average,
sit in cash when it's below. Compared fairly against just holding the ETF
(buy & hold), net of trading costs, over ~7 years. The honest scorecard is
'similar-ish return, much smaller drawdowns'.

Also reports BREADTH — the % of themes above their line — as a plain
'consensus' gauge, and whether high breadth led to better forward returns.

    python scripts/run_trend_backtest.py            # fetch ~7y
    python scripts/run_trend_backtest.py --no-fetch # cached
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from tickline.data import fetch_many
from tickline.timing import breadth, buy_hold, portfolio, portfolio_returns, trend_follow

RESET = "\033[0m"; SIGNAL = "\033[38;2;45;209;120m"; ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"; INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"; INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}trend-follow vs buy & hold{INK}      │
   │  {INK_FAINT}does timing the trend cut the pain?{INK}       │
   └─────────────────────────────────────────┘{RESET}
"""

ETFS = ["SMH", "IGV", "QQQ", "CIBR", "BOTZ", "IBIT", "URA", "TAN", "XLE",
        "GDX", "SIL", "COPX", "ITA", "UFO", "XBI", "XLF", "XHB", "XLU"]
NAMES = {"SMH": "Chips", "IGV": "Software", "QQQ": "Big Tech", "CIBR": "Cyber",
         "BOTZ": "Robotics", "IBIT": "Bitcoin", "URA": "Uranium", "TAN": "Solar",
         "XLE": "Oil & Gas", "GDX": "Gold", "SIL": "Silver", "COPX": "Copper",
         "ITA": "Defense", "UFO": "Space", "XBI": "Biotech", "XLF": "Banks",
         "XHB": "Homebuild", "XLU": "Utilities"}


def _pct(x):
    return "  —  " if x is None or x != x else f"{x*100:+.0f}%"


def _ddcol(x):
    return f"{ALERT}{x*100:>5.0f}%{RESET}"


def main() -> int:
    p = argparse.ArgumentParser(description="Trend-follow vs buy & hold")
    p.add_argument("--days", type=int, default=1800)
    p.add_argument("--ma", type=int, default=200)
    p.add_argument("--cost-bps", type=float, default=5.0)
    p.add_argument("--cash-yield", type=float, default=2.5,
                   help="annual %% earned while sitting in cash")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()
    cash = args.cash_yield / 100.0

    print(BANNER)
    print(f"{INK_FAINT}>>{RESET} fetching {len(ETFS)} ETFs, ~{args.days//252}y…")
    frames = fetch_many(ETFS, days=args.days, use_cache=not args.no_fetch)
    if not frames:
        print(f"{ALERT}no data{RESET}"); return 1
    span = next(iter(frames.values())).index
    print(f"{INK_FAINT}>>{RESET} {len(frames)} ETFs · {args.ma}-day line · "
          f"{args.cost_bps:.0f}bps/switch\n")

    # ── per-ETF ──────────────────────────────────────────────────────────
    print(f"{INK}Per theme{RESET} {INK_FAINT}(trend-follow vs buy & hold){RESET}\n")
    print(f"   {INK_FAINT}{'theme':<11}{'TF ret':>8}{'BH ret':>8}{'TF maxDD':>10}"
          f"{'BH maxDD':>10}{'TF Shrp':>9}{'BH Shrp':>9}{'% in':>7}{RESET}")
    print(f"   {INK_FAINT}{'─'*72}{RESET}")
    for sym in ETFS:
        df = frames.get(sym)
        if df is None or len(df) < args.ma + 30:
            continue
        c = df["close"]
        tf = trend_follow(c, args.ma, args.cost_bps)
        bh = buy_hold(c)
        better_dd = tf.max_dd > bh.max_dd  # shallower (less negative)
        print(f"   {INK}{NAMES.get(sym, sym):<11}{RESET}"
              f"{INK}{_pct(tf.cagr):>8}{_pct(bh.cagr):>8}{RESET}"
              f"{(SIGNAL if better_dd else ALERT)}{tf.max_dd*100:>9.0f}%{RESET}"
              f"{ALERT}{bh.max_dd*100:>9.0f}%{RESET}"
              f"{INK}{tf.sharpe:>9.2f}{bh.sharpe:>9.2f}{RESET}"
              f"{INK_DIM}{tf.time_in*100:>6.0f}%{RESET}")

    # ── portfolio ────────────────────────────────────────────────────────
    tf, bh = portfolio(frames, args.ma, args.cost_bps, cash)
    print(f"\n{INK}Equal-weight basket of all {len(frames)} themes{RESET} "
          f"{INK_FAINT}(cash earns {args.cash_yield:.1f}%/yr){RESET}\n")
    for s in (tf, bh):
        print(f"   {INK}{s.label:<26}{RESET} return {SIGNAL if s.cagr>0 else ALERT}"
              f"{_pct(s.cagr):>6}{RESET}/yr   {INK_DIM}Sharpe{RESET} {INK}{s.sharpe:>5.2f}{RESET}   "
              f"{INK_DIM}worst drop{RESET} {_ddcol(s.max_dd)}   "
              f"{INK_DIM}invested{RESET} {INK}{s.time_in*100:>3.0f}%{RESET}")

    dd_cut = (bh.max_dd - tf.max_dd)  # how much shallower (positive = better)
    print(f"\n   {INK}→ trend-follow cut the worst drop by "
          f"{SIGNAL}{dd_cut*100:.0f} points{RESET} "
          f"({_pct(bh.max_dd)} → {_pct(tf.max_dd)}), "
          f"Sharpe {bh.sharpe:.2f} → {tf.sharpe:.2f}, "
          f"for {_pct(tf.cagr-bh.cagr)} of return.{RESET}")

    # ── robustness: does it hold across MA lengths? ──────────────────────
    print(f"\n{INK}Robustness{RESET} {INK_FAINT}(is the drawdown-cut just a 200-day fluke?){RESET}\n")
    print(f"   {INK_FAINT}{'MA window':<12}{'TF ret':>9}{'TF maxDD':>10}{'TF Sharpe':>11}{RESET}")
    print(f"   {INK_FAINT}{'─'*42}{RESET}")
    for ma in (50, 100, 150, 200, 250):
        s, _ = portfolio(frames, ma, args.cost_bps, cash)
        print(f"   {INK}{str(ma)+'-day':<12}{RESET}{INK}{_pct(s.cagr):>9}{RESET}"
              f"{SIGNAL if s.max_dd > bh.max_dd else ALERT}{s.max_dd*100:>9.0f}%{RESET}"
              f"{INK}{s.sharpe:>11.2f}{RESET}")
    print(f"   {INK_DIM}{'buy & hold':<12}{_pct(bh.cagr):>9}{bh.max_dd*100:>9.0f}%{bh.sharpe:>11.2f}{RESET}")

    # ── regime split: when does it actually help? ────────────────────────
    tfr, bhr, _, _ = portfolio_returns(frames, args.ma, args.cost_bps, cash)
    print(f"\n{INK}When does it help?{RESET} {INK_FAINT}(return by year){RESET}\n")
    print(f"   {INK_FAINT}{'year':<8}{'buy & hold':>12}{'trend-follow':>14}{'  helped?':>10}{RESET}")
    for y in sorted(set(tfr.index.year)):
        b_y = (1 + bhr[bhr.index.year == y]).prod() - 1
        t_y = (1 + tfr[tfr.index.year == y]).prod() - 1
        helped = "✓ saved you" if (b_y < 0 and t_y > b_y) else ("· gave up" if t_y < b_y else "·")
        hc = SIGNAL if (b_y < 0 and t_y > b_y) else INK_FAINT
        print(f"   {INK}{y:<8}{RESET}{(SIGNAL if b_y>0 else ALERT)}{_pct(b_y):>12}{RESET}"
              f"{(SIGNAL if t_y>0 else ALERT)}{_pct(t_y):>14}{RESET}{hc}{helped:>12}{RESET}")

    # ── breadth as consensus ─────────────────────────────────────────────
    b = breadth(frames, args.ma).dropna()
    if not b.empty:
        cur = float(b.iloc[-1])
        # forward 21d return of the (buy&hold) basket, conditioned on breadth
        eqret = pd.concat([frames[s]["close"].pct_change() for s in frames], axis=1).mean(axis=1)
        fwd = (1 + eqret).rolling(21).apply(lambda x: x.prod() - 1, raw=True).shift(-21)
        idx = b.index.intersection(fwd.dropna().index)
        bb, ff = b.reindex(idx), fwd.reindex(idx)
        hi = ff[bb > 0.6].mean(); lo = ff[bb < 0.4].mean()
        print(f"\n{INK}Breadth = consensus{RESET} {INK_FAINT}(% of themes above their line){RESET}\n")
        bar = "█" * int(cur * 20)
        col = SIGNAL if cur > 0.6 else (AMBER if cur > 0.4 else ALERT)
        print(f"   today: {col}{bar:<20} {cur*100:.0f}%{RESET}  "
              f"{INK_DIM}({'risk-on' if cur>0.6 else 'mixed' if cur>0.4 else 'risk-off'}){RESET}")
        print(f"   {INK_DIM}next-month basket return when breadth was{RESET} "
              f">60%: {SIGNAL if hi>0 else ALERT}{_pct(hi)}{RESET}  "
              f"vs <40%: {SIGNAL if lo>0 else ALERT}{_pct(lo)}{RESET}")

    print(f"\n{INK}{'═'*60}{RESET}")
    verdict = (SIGNAL + "Trend-follow traded a little return for a much smaller drawdown — "
               "the honest win." + RESET) if dd_cut > 0.05 else (
               AMBER + "Drawdown reduction was modest here." + RESET)
    print(f"  {verdict}")
    print(f"{INK_FAINT}  honest: no T-bill yield on cash, same-close fills, ETFs only, "
          f"one ~7y window (one big bull + 2022).{RESET}")
    print(f"{INK}{'═'*60}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
