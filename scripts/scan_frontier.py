#!/usr/bin/env python3
"""Frontier scan — hunt the NEXT AI rotation leg.

Two confidence tiers, kept deliberately separate:

  HIGH confidence (validated momentum): rank the CORE themes by
  rel-strength level — be long the leaders. This is the edge the
  backtest proved (+29.6%/yr net, Sharpe 1.23).

  LOW confidence (speculative next-leg): score FRONTIER candidate themes
  not yet in the core graph by (a) rel-strength slope = is it turning up,
  and (b) news attention = is consensus starting to form. Acceleration
  was shown to be noisy, so treat these as hypotheses to size SMALL, not
  high-conviction bets.

The honest 'next trend' is a low-confidence hunt. This tool makes the
hunt evidence-based instead of vibes-based; it does not make it certain.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from tickline.data import fetch_many
from tickline.sentiment.live import fetch_news
from tickline.themes import AI_THEMES, BENCHMARK, SLOW, compute_theme_heat
from tickline.themes.taxonomy import Theme, all_tickers

RESET = "\033[0m"; SIGNAL = "\033[38;2;45;209;120m"; ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"; INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"; INK_FAINT = "\033[38;2;91;101;115m"

# Candidate frontier legs — NOT in the validated core universe.
FRONTIER: tuple[Theme, ...] = (
    Theme("neoclouds", "Neoclouds / AI infra", ("CRWV", "NBIS", "APLD", "IREN"),
          keywords=("CoreWeave", "Nebius", "AI cloud", "neocloud GPU rental")),
    Theme("custom_silicon", "Custom silicon / ASIC", ("MRVL", "ALAB", "CRDO"),
          keywords=("custom AI chip", "ASIC accelerator", "Marvell AI", "Astera Labs")),
    Theme("nuclear_smr", "Nuclear / SMR", ("OKLO", "SMR", "NNE", "LEU"),
          keywords=("small modular reactor", "nuclear data center", "Oklo", "SMR nuclear")),
    Theme("quantum", "Quantum computing", ("IONQ", "RGTI", "QBTS"),
          keywords=("quantum computing", "IonQ", "Rigetti", "quantum stock")),
    Theme("robotics_physical", "Humanoid / physical AI", ("TSLA", "SERV"),
          keywords=("humanoid robot", "physical AI", "Optimus robot", "embodied AI")),
)


def _news_attention(theme: Theme, session=None) -> tuple[int, float]:
    """(total recent headlines, share in last 7d) — a rising-attention proxy."""
    evs = []
    for term in theme.query_terms[:2]:
        evs += fetch_news(term, session=session)
    if not evs:
        return 0, 0.0
    ts = pd.DatetimeIndex([e.ts for e in evs], tz="UTC")
    now = ts.max()
    last7 = (ts >= now - pd.Timedelta(days=7)).sum()
    return len(evs), last7 / len(evs)


def _heat_row(theme, frames, bench_ret, att):
    h = compute_theme_heat(theme, frames, bench_ret, SLOW)
    if h is None:
        return None
    n, recent = att
    return {
        "label": theme.label, "level": h.market_level, "slope": h.market_slope,
        "breadth": h.components.breadth, "news": n, "recent_share": recent,
        "n_con": h.n_constituents,
    }


def _pct(x): return f"{x*100:+.0f}%"


def main() -> int:
    print(f"{INK}frontier scan — current leaders vs next-leg candidates{RESET}\n")
    core_syms = all_tickers()
    front_syms = [t for th in FRONTIER for t in th.tickers]
    print(f"{INK_FAINT}>> fetching {len(set(core_syms+front_syms))} symbols…{RESET}")
    frames = fetch_many(sorted(set(core_syms + front_syms)), days=300)
    if BENCHMARK not in frames:
        print(f"{ALERT}no benchmark{RESET}"); return 1
    bench_ret = frames[BENCHMARK]["close"].pct_change()

    import requests
    sess = requests.Session(); sess.headers.update({"User-Agent": "tickline/0.1"})

    # CORE: validated momentum leaders
    core = [r for r in (_heat_row(t, frames, bench_ret, (0, 0.0)) for t in AI_THEMES) if r]
    core.sort(key=lambda r: r["level"], reverse=True)
    print(f"\n{SIGNAL}HIGH-CONFIDENCE — current leaders (validated momentum long){RESET}")
    print(f"   {INK_FAINT}{'theme':<24}{'rel-str':>9}{'63d slope':>11}{'breadth':>9}{RESET}")
    for r in core[:4]:
        print(f"   {INK}{r['label']:<24}{SIGNAL}{_pct(r['level']):>9}{RESET}"
              f"{INK}{_pct(r['slope']):>11}{r['breadth']*100:>7.0f}%{RESET}")

    # FRONTIER: speculative next-leg candidates
    print(f"\n{AMBER}LOW-CONFIDENCE — frontier next-leg candidates (speculative){RESET}")
    print(f"{INK_FAINT}>> pulling news attention per candidate…{RESET}")
    rows = []
    for th in FRONTIER:
        att = _news_attention(th, sess)
        r = _heat_row(th, frames, bench_ret, att)
        if r is None:
            print(f"   {INK_FAINT}{th.label}: insufficient price history — skipped{RESET}")
            continue
        rows.append(r)
    # rank by turning-up + getting-noticed: slope, then recent news share
    rows.sort(key=lambda r: (r["slope"], r["recent_share"]), reverse=True)
    print(f"\n   {INK_FAINT}{'candidate':<24}{'rel-str':>9}{'63d slope':>11}"
          f"{'news':>7}{'7d%':>7}{'read':>16}{RESET}")
    for r in rows:
        turning = r["slope"] > 0
        loud = r["recent_share"] > 0.4
        if turning and loud:
            read, c = "turning + loud", SIGNAL
        elif turning:
            read, c = "turning, quiet", AMBER
        elif loud:
            read, c = "loud, not turning", AMBER
        else:
            read, c = "dormant", INK_FAINT
        sc = SIGNAL if turning else ALERT
        print(f"   {INK}{r['label']:<24}{INK}{_pct(r['level']):>9}{RESET}"
              f"{sc}{_pct(r['slope']):>11}{RESET}{INK}{r['news']:>7}{r['recent_share']*100:>6.0f}%{RESET}"
              f"{c}{read:>16}{RESET}")
    print(f"\n{INK_FAINT}'turning' = positive 63d rel-strength slope · 'loud' = >40% of news "
          f"in last 7d.\nNeither is backtested as predictive — these are research leads, not signals.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
