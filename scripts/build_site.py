#!/usr/bin/env python3
"""Export the theme-rotation watchlist to a static web data island.

Runs the watchlist over the full US universe for both tiers and writes
web/data.js as `window.TICKLINE_DATA = {...}`. Inlining as a JS global
(not a JSON file) means the site renders by opening index.html directly —
no server, no fetch/CORS — and deploys to any static host unchanged.

    python scripts/build_site.py            # fetch fresh
    python scripts/build_site.py --no-fetch # use cached parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.data import fetch_many
from tickline.themes import (
    ALL_THEMES,
    BENCHMARK,
    FAST,
    SLOW,
    compute_theme_heat,
    rank_states,
)
from tickline.themes.rotation import long_short_books
from tickline.themes.taxonomy import all_tickers

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
TIERS = {"slow": SLOW, "fast": FAST}
RANK_FRAC = 0.15
GROUP_BY_KEY = {t.key: t.group for t in ALL_THEMES}


def _round(x, n=4):
    return None if x is None else round(float(x), n)


def _tier_payload(cfg, frames, bench_ret) -> dict:
    heats = {}
    for theme in ALL_THEMES:
        h = compute_theme_heat(theme, frames, bench_ret, cfg)
        if h is not None:
            heats[theme.key] = h
    states = rank_states(list(heats.values()), top_frac=RANK_FRAC, bottom_frac=RANK_FRAC)
    ranked = sorted(heats.values(), key=lambda h: h.market_level, reverse=True)
    leaders, laggards = long_short_books(list(heats.values()), states)
    rows = [
        {
            "key": h.key,
            "label": h.label,
            "group": GROUP_BY_KEY.get(h.key, ""),
            "signal": states[h.key].value,
            "rel": _round(h.market_level),
            "slope": _round(h.market_slope),
            "breadth": _round(h.components.breadth),
        }
        for h in ranked
    ]
    return {
        "lookback": cfg.lookback,
        "rows": rows,
        "leaders": [h.key for h in leaders],
        "laggards": [h.key for h in laggards],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Export watchlist to web/data.js")
    p.add_argument("--days", type=int, default=250)
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    symbols = all_tickers()
    print(f">> fetching {len(symbols)} symbols…")
    frames = fetch_many(symbols, days=args.days, use_cache=not args.no_fetch)
    if BENCHMARK not in frames:
        print("benchmark unavailable"); return 1
    bench_ret = frames[BENCHMARK]["close"].pct_change()
    as_of = frames[BENCHMARK].index[-1]

    groups: list[str] = []
    for t in ALL_THEMES:
        if t.group not in groups:
            groups.append(t.group)

    payload = {
        "as_of": str(as_of.date()),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        "benchmark": BENCHMARK,
        "n_symbols": len(frames),
        "groups": groups,
        "tiers": {name: _tier_payload(cfg, frames, bench_ret) for name, cfg in TIERS.items()},
    }

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    out = WEB_DIR / "data.js"
    out.write_text("window.TICKLINE_DATA = " + json.dumps(payload, indent=2) + ";\n")
    n = len(payload["tiers"]["slow"]["rows"])
    print(f">> wrote {out.relative_to(WEB_DIR.parent)} · {n} themes · as of {payload['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
