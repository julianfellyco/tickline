#!/usr/bin/env python3
"""AI theme-rotation watchlist.

Pulls US AI-connected sub-themes, scores a market thermometer (rel
strength, breadth, volume, ETF flow) and an optional retail thermometer
(news + StockTwits), classifies each theme's rotation state, ranks where
money is rotating, and alerts on *state changes* since the last run.

    python scripts/run_watchlist.py                 # market spine, both tiers
    python scripts/run_watchlist.py --retail        # add crowd thermometer
    python scripts/run_watchlist.py --tier fast     # swing tier only
    python scripts/run_watchlist.py --no-fetch      # use cached parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.data import fetch_many, fetch_shares_outstanding
from tickline.themes import (
    ALL_THEMES,
    BENCHMARK,
    FAST,
    SLOW,
    RankState,
    compute_theme_heat,
    load_snapshot,
    rank_states,
    save_snapshot,
)
from tickline.themes.rotation import detect_rank_transitions, long_short_books
from tickline.themes.taxonomy import all_tickers

GROUP_BY_KEY = {t.key: t.group for t in ALL_THEMES}
# Fraction of the universe to flag LEADER / LAGGARD (tighter for a big set).
RANK_FRAC = 0.15

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}watchlist{INK}                       │
   │  {INK_FAINT}AI theme rotation · market + crowd{INK}       │
   └─────────────────────────────────────────┘{RESET}
"""

RANK_COLOR = {
    RankState.LEADER: SIGNAL,
    RankState.NEUTRAL: INK_FAINT,
    RankState.LAGGARD: ALERT,
}
TIERS = {"fast": FAST, "slow": SLOW}
TIER_LABEL = {"fast": "swing / alpha", "slow": "position / confirm"}


def _pct(x: float | None) -> str:
    return f"{x * 100:+.1f}%" if x is not None else "  —  "


def _retail_cell(level: float | None) -> str:
    if level is None:
        return f"{INK_FAINT}  off {RESET}"
    color = AMBER if level > 1.0 else INK_DIM
    return f"{color}{level:+.2f}z{RESET}"


def _build_retail(session):
    """Map theme.key -> daily attention series. Best-effort; {} on opt-out."""
    from tickline.sentiment import build_theme_feed, retail_attention_series

    out: dict[str, object] = {}
    for theme in ALL_THEMES:
        feed = build_theme_feed(theme.query_terms, theme.tickers, session=session)
        series = retail_attention_series(feed)
        if not series.empty:
            out[theme.key] = series
        print(f"  [retail] {theme.key}: {len(feed)} events")
    return out


def _run_tier(tier: str, frames, bench_ret, retail, etf_shares, prev_states):
    cfg = TIERS[tier]
    heats = {}
    for theme in ALL_THEMES:
        heat = compute_theme_heat(
            theme,
            frames,
            bench_ret,
            cfg,
            retail_series=retail.get(theme.key),
            etf_shares=etf_shares.get(theme.etf) if theme.etf else None,
        )
        if heat is None:
            continue
        heats[theme.key] = heat

    states = rank_states(list(heats.values()), top_frac=RANK_FRAC, bottom_frac=RANK_FRAC)
    ranked = sorted(heats.values(), key=lambda h: h.market_level, reverse=True)
    print(f"{INK}{tier.upper()} tier{RESET} {INK_FAINT}({TIER_LABEL[tier]} · "
          f"lookback {cfg.lookback}d · {len(ranked)} themes ranked by rel-strength){RESET}\n")
    print(f"   {INK_FAINT}{'theme':<24}{'group':<18}{'signal':<9}{'rel-str':>9}"
          f"{'slope':>9}{'breadth':>9}{'retail':>9}{RESET}")
    print(f"   {INK_FAINT}{'─' * 87}{RESET}")
    for h in ranked:
        st = states[h.key]
        c = RANK_COLOR[st]
        grp = GROUP_BY_KEY.get(h.key, "")[:16]
        print(
            f"   {INK}{h.label[:23]:<24}{RESET}{INK_FAINT}{grp:<18}{RESET}"
            f"{c}{st.value:<9}{RESET}"
            f"{INK}{_pct(h.market_level):>9}{RESET}"
            f"{_slope(h.market_slope):>18}"
            f"{INK}{h.components.breadth * 100:>7.0f}%{RESET}"
            f"{_retail_cell(h.retail_level):>9}"
        )

    leaders, laggards = long_short_books(list(heats.values()), states)
    if leaders:
        names = ", ".join(f"{SIGNAL}{h.label}{RESET}" for h in leaders)
        print(f"\n   {INK_DIM}LONG  (leaders) →{RESET} {names}")
    if laggards:
        names = ", ".join(f"{ALERT}{h.label}{RESET}" for h in laggards)
        print(f"   {INK_DIM}SHORT (laggards) →{RESET} {names}")

    transitions = detect_rank_transitions(prev_states, heats, states, tier)
    print()
    return states, transitions


def _slope(x: float) -> str:
    color = SIGNAL if x > 0 else (ALERT if x < 0 else INK)
    return f"{color}{x * 100:+.1f}%{RESET}"


def main() -> int:
    p = argparse.ArgumentParser(description="AI theme-rotation watchlist")
    p.add_argument("--days", type=int, default=300)
    p.add_argument("--tier", choices=["fast", "slow", "both"], default="slow")
    p.add_argument("--retail", action="store_true", help="add crowd thermometer")
    p.add_argument("--no-fetch", action="store_true", help="use cached parquet only")
    p.add_argument("--flow", action="store_true", help="fetch ETF flow proxy (slow)")
    args = p.parse_args()

    print(BANNER)
    symbols = all_tickers()
    print(f"{INK_FAINT}>>{RESET} fetching {len(symbols)} symbols "
          f"(benchmark {BENCHMARK})…")
    frames = fetch_many(symbols, days=args.days, use_cache=not args.no_fetch)
    if BENCHMARK not in frames:
        print(f"{ALERT}benchmark {BENCHMARK} unavailable — aborting{RESET}")
        return 1
    bench_ret = frames[BENCHMARK]["close"].pct_change()
    as_of = frames[BENCHMARK].index[-1]
    print(f"{INK_FAINT}>>{RESET} {len(frames)} symbols ok · as of "
          f"{SIGNAL}{as_of.date()}{RESET}\n")

    etf_shares: dict[str, object] = {}
    if args.flow:
        for theme in ALL_THEMES:
            if theme.etf and theme.etf not in etf_shares:
                s = fetch_shares_outstanding(theme.etf, days=args.days)
                if s is not None:
                    etf_shares[theme.etf] = s

    retail: dict[str, object] = {}
    if args.retail:
        import requests

        sess = requests.Session()
        sess.headers.update({"User-Agent": "tickline-watchlist/0.1"})
        print(f"{INK_FAINT}>>{RESET} building crowd thermometer (best-effort)…")
        retail = _build_retail(sess)
        print()

    tiers = ["fast", "slow"] if args.tier == "both" else [args.tier]
    snapshot = load_snapshot()
    prev = snapshot.get("tiers", {})
    all_transitions = []
    tier_states = {}
    for tier in tiers:
        states, transitions = _run_tier(
            tier, frames, bench_ret, retail, etf_shares, prev.get(tier, {})
        )
        tier_states[tier] = states
        all_transitions.extend(transitions)

    # --- alerts: state changes since last run --------------------------------
    print(f"{INK}{'═' * 60}{RESET}")
    if all_transitions:
        print(f"{INK}⚑ ALERTS — {len(all_transitions)} state change(s) since last run{RESET}\n")
        for t in all_transitions:
            arrow = f"{t.from_state or 'new'} → {t.to_state}"
            color = RANK_COLOR.get(RankState(t.to_state), INK)
            print(f"   {color}[{t.tier}] {t.label:<22}{RESET} {INK}{arrow:<26}{RESET}"
                  f"{INK_DIM}{t.play}{RESET}")
            print(f"        {INK_FAINT}rel-str {_pct(t.market_level)}  "
                  f"slope {t.market_slope * 100:+.1f}%  "
                  f"retail {t.retail_level if t.retail_level is not None else '—'}{RESET}")
    else:
        print(f"{INK_DIM}no state changes since last run "
              f"(first run just seeds the baseline){RESET}")
    print(f"{INK}{'═' * 60}{RESET}")

    save_snapshot(str(as_of.date()), tier_states)
    print(f"\n{INK_FAINT}snapshot saved → data/watchlist_snapshot.json{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
