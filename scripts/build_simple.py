#!/usr/bin/env python3
"""Simple 'Trend & Crowd' board — the beginner-friendly product.

One theme = one ETF (a ready-made basket you can actually buy). For each:

  TREND  (price)  — is it above its 200-day line AND beating the S&P
                    over 3 months?  -> up / sideways / down
  CROWD  (buzz)   — how much recent news is there vs the other themes?
                    -> loud / quiet

Combined into a 4-colour traffic light + one plain-English sentence. No
z-scores, no baskets, no backtests pretending to be alpha. Writes
web/simple/data.js for the static page.

    python scripts/build_simple.py            # fetch fresh
    python scripts/build_simple.py --no-fetch # cached
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from tickline.data import fetch_equity
from tickline.sentiment.live import fetch_news

OUT = Path(__file__).resolve().parents[1] / "web" / "simple"
BENCH = "SPY"

# theme label, ETF ticker (the basket), plain news query
THEMES = [
    ("Chips / Semiconductors", "SMH", "semiconductor stocks"),
    ("AI Software", "IGV", "AI software stocks"),
    ("Big Tech", "QQQ", "big tech stocks"),
    ("Cybersecurity", "CIBR", "cybersecurity stocks"),
    ("Robotics & AI", "BOTZ", "AI robotics stocks"),
    ("Bitcoin", "IBIT", "bitcoin price"),
    ("Nuclear & Uranium", "URA", "nuclear uranium stocks"),
    ("Solar", "TAN", "solar stocks"),
    ("Oil & Gas", "XLE", "oil price energy stocks"),
    ("Gold Miners", "GDX", "gold price"),
    ("Silver", "SIL", "silver price"),
    ("Copper", "COPX", "copper stocks"),
    ("Defense", "ITA", "defense stocks"),
    ("Space", "UFO", "space stocks"),
    ("Biotech", "XBI", "biotech stocks"),
    ("Banks", "XLF", "bank stocks"),
    ("Homebuilders", "XHB", "homebuilder stocks"),
    ("Utilities & Power", "XLU", "utility stocks power grid"),
]

VERDICTS = {
    "confirmed": "Uptrend and the crowd is piling in — the trend everyone agrees on.",
    "early": "Quietly trending up before the crowd noticed — the early ones.",
    "hype": "Lots of buzz but the price is falling — careful, this is a hype trap.",
    "dead": "Falling and forgotten — nothing happening here.",
    "neutral_loud": "Going sideways, but getting noisy — one to watch.",
    "neutral_quiet": "Going sideways — no clear trend yet.",
}
LIGHT = {"confirmed": "green", "early": "blue", "hype": "amber",
         "dead": "red", "neutral_loud": "grey", "neutral_quiet": "grey"}
EMOJI = {"green": "🟢", "blue": "🔵", "amber": "🟡", "red": "🔴", "grey": "⚪"}


def _ret(close: pd.Series, bars: int):
    if len(close) <= bars:
        return None
    return float(close.iloc[-1] / close.iloc[-1 - bars] - 1.0)


def _news_last7(query: str, session) -> int:
    evs = fetch_news(query, session=session)
    if not evs:
        return 0
    latest = max(e.ts for e in evs)
    return sum(1 for e in evs if e.ts >= latest - pd.Timedelta(days=7))


def main() -> int:
    p = argparse.ArgumentParser(description="Build the simple Trend & Crowd board")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    use_cache = not args.no_fetch
    spy = fetch_equity(BENCH, days=320, use_cache=use_cache)
    if spy.empty:
        print("no benchmark"); return 1
    spy_close = spy["close"]
    spy63 = _ret(spy_close, 63) or 0.0

    import requests
    sess = requests.Session(); sess.headers.update({"User-Agent": "tickline-simple/0.1"})

    rows = []
    for label, etf, query in THEMES:
        df = fetch_equity(etf, days=320, use_cache=use_cache)
        if df.empty:
            print(f"  skip {etf}: no data"); continue
        close = df["close"]
        ma = close.rolling(200, min_periods=100).mean().iloc[-1]
        above = bool(close.iloc[-1] > ma) if pd.notna(ma) else True
        ret63 = _ret(close, 63)
        beat = (ret63 - spy63) if ret63 is not None else 0.0

        if above and beat > 0:
            trend = "up"
        elif (not above) and beat < 0:
            trend = "down"
        else:
            trend = "sideways"

        buzz = _news_last7(query, sess)
        rows.append({
            "label": label, "etf": etf, "trend": trend,
            "ret3mo": round(ret63, 4) if ret63 is not None else None,
            "vs_spy": round(beat, 4), "buzz": buzz,
        })
        print(f"  {etf:5} {trend:8} 3mo {beat*100:+5.1f}% vs SPY · buzz {buzz}")

    # crowd is RELATIVE: loud = more recent news than the median theme
    buzzes = sorted(r["buzz"] for r in rows)
    median = buzzes[len(buzzes) // 2] if buzzes else 0
    for r in rows:
        loud = r["buzz"] > median or (r["buzz"] >= median and median > 0)
        r["crowd"] = "loud" if loud else "quiet"
        t, c = r["trend"], r["crowd"]
        if t == "up":
            key = "confirmed" if c == "loud" else "early"
        elif t == "down":
            key = "hype" if c == "loud" else "dead"
        else:
            key = "neutral_loud" if c == "loud" else "neutral_quiet"
        r["state"] = key
        r["light"] = LIGHT[key]
        r["emoji"] = EMOJI[LIGHT[key]]
        r["verdict"] = VERDICTS[key]

    # sort: leaders (up) first, then sideways, then down; within, louder first
    order = {"up": 0, "sideways": 1, "down": 2}
    rows.sort(key=lambda r: (order[r["trend"]], -(r["vs_spy"] or 0)))

    payload = {
        "as_of": str(spy.index[-1].date()),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        "benchmark": BENCH,
        "themes": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.js").write_text("window.SIMPLE_DATA = " + json.dumps(payload, indent=2) + ";\n")
    print(f">> wrote web/simple/data.js · {len(rows)} themes · as of {payload['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
