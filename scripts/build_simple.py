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

from tickline.data import fetch_equity, fetch_many
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

# The companies screened into each category (comprehensive major US names).
STOCKS = {
    "SMH":  ["NVDA", "AVGO", "AMD", "TSM", "MU", "QCOM", "TXN", "AMAT", "LRCX",
             "KLAC", "ADI", "MRVL", "MCHP", "NXPI", "ON", "SMCI"],
    "IGV":  ["MSFT", "CRM", "NOW", "PLTR", "SNOW", "ORCL", "ADBE", "INTU",
             "PANW", "CRWD", "DDOG", "TEAM", "WDAY", "NET"],
    "QQQ":  ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
             "NFLX", "COST", "PEP", "ADBE"],
    "CIBR": ["CRWD", "PANW", "ZS", "FTNT", "NET", "S", "OKTA", "CYBR", "TENB", "QLYS"],
    "BOTZ": ["NVDA", "ISRG", "TSLA", "PATH", "TER", "ROK", "EMR", "ZBRA", "IRBT", "SERV"],
    "IBIT": ["COIN", "MSTR", "MARA", "RIOT", "HOOD", "CLSK", "WULF", "CIFR", "BITF", "HUT"],
    "URA":  ["CCJ", "OKLO", "SMR", "LEU", "UEC", "UUUU", "DNN", "NNE", "NXE", "BWXT"],
    "TAN":  ["FSLR", "ENPH", "RUN", "NXT", "SEDG", "ARRY", "SHLS", "CSIQ", "JKS", "MAXN"],
    "XLE":  ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "OXY", "WMB", "KMI", "HAL", "DVN"],
    "GDX":  ["NEM", "AEM", "GOLD", "WPM", "FNV", "KGC", "AU", "GFI", "RGLD", "AGI", "BTG"],
    "SIL":  ["PAAS", "AG", "HL", "WPM", "FNV", "CDE", "SVM", "EXK", "MAG", "FSM"],
    "COPX": ["FCX", "SCCO", "TECK", "BHP", "RIO", "VALE", "ERO", "HBM", "TGB"],
    "ITA":  ["LMT", "RTX", "NOC", "GD", "BA", "LHX", "HII", "TXT", "LDOS", "HWM", "AXON", "KTOS"],
    "UFO":  ["RKLB", "LUNR", "ASTS", "RDW", "PL", "BKSY", "SPCE", "ASTR"],
    "XBI":  ["VRTX", "REGN", "MRNA", "GILD", "AMGN", "BIIB", "ALNY", "INCY", "NBIX", "SRPT"],
    "XLF":  ["JPM", "BAC", "WFC", "GS", "MS", "C", "USB", "PNC", "TFC", "SCHW", "AXP"],
    "XHB":  ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MTH", "TPH", "BLDR", "BLD"],
    "XLU":  ["NEE", "SO", "DUK", "CEG", "VST", "AEP", "D", "EXC", "SRE", "XEL", "ED", "PEG"],
}

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


def _stock_trend(df) -> dict:
    """Per-company trend: above its own 200-day line? + 3-month return."""
    close = df["close"]
    ma = close.rolling(200, min_periods=100).mean().iloc[-1]
    above = bool(close.iloc[-1] > ma) if pd.notna(ma) else None
    ret63 = _ret(close, 63)
    return {
        "trend": ("up" if above else "down") if above is not None else "flat",
        "above_ma": above,
        "ret3mo": round(ret63, 3) if ret63 is not None else None,
    }


# Hard-news / research outlets only. Listicle and promo factories
# (Motley Fool, Seeking Alpha, Investing.com, Yahoo listicles) are noise.
TRUSTED = {
    "reuters", "bloomberg", "wall street journal", "wsj", "financial times", "ft.com",
    "cnbc", "barron", "marketwatch", "associated press", "forbes",
    "investor's business daily", "morningstar", "the economist", "nasdaq",
    "business insider", "fortune", "axios", "the new york times", "washington post",
}


def _trusted_news(query: str, scorer, session, limit: int = 3):
    """Recent headlines from trusted outlets only + a coverage-tone read.

    Filters Google News results to the TRUSTED whitelist (drops blogs,
    promo, and aggregator noise). Returns (headlines, tone).
    """
    from urllib.parse import quote_plus
    from xml.etree import ElementTree as ET

    url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
           + "&hl=en-US&gl=US&ceid=US:en")
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return [], None

    out = []
    for item in root.iterfind(".//item"):
        title = (item.findtext("title") or "").strip()
        src_el = item.find("source")
        source = (src_el.text or "").strip() if src_el is not None else ""
        if not title or not source:
            continue
        if not any(t in source.lower() for t in TRUSTED):
            continue
        if title.endswith(" - " + source):
            title = title[: -(len(source) + 3)].strip()
        out.append({"title": title, "source": source})
        if len(out) >= limit:
            break
    if not out:
        return [], None
    avg = sum(scorer.score(h["title"]) for h in out) / len(out)
    tone = "positive" if avg > 0.12 else "negative" if avg < -0.12 else "mixed"
    return out, tone


def _company_brief(sym: str, df, session=None, scorer=None) -> dict:
    """Analyst view + fundamentals + price action for the click-out modal.

    Price action is computed from the price frame (always available);
    fundamentals/analyst come from yfinance .info (best-effort — small or
    new names may be missing, and those fields come back None).
    """
    info = {}
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info or {}
    except Exception:
        info = {}

    close = df["close"]
    price = float(close.iloc[-1])

    def ret(n):
        return round(float(close.iloc[-1] / close.iloc[-1 - n] - 1), 3) if len(close) > n else None

    def rnd(key, dp=2):
        v = info.get(key)
        return round(float(v), dp) if isinstance(v, (int, float)) else None

    window = close.iloc[-252:] if len(close) >= 60 else close
    summary = info.get("longBusinessSummary") or ""
    if len(summary) > 340:
        summary = summary[:337].rsplit(" ", 1)[0] + "…"

    news, news_tone = ([], None)
    if session is not None and scorer is not None:
        name_q = info.get("shortName") or info.get("longName") or sym
        news, news_tone = _trusted_news(name_q + " stock", scorer, session)

    return {
        "news": news, "news_tone": news_tone,
        "name": info.get("shortName") or info.get("longName") or sym,
        "sector": info.get("sector"), "industry": info.get("industry"),
        "summary": summary or None, "employees": info.get("fullTimeEmployees"),
        "price": round(price, 2),
        "w52h": round(float(window.max()), 2), "w52l": round(float(window.min()), 2),
        "mcap": info.get("marketCap"),
        "pe": rnd("trailingPE"), "fpe": rnd("forwardPE"), "eps": rnd("trailingEps"),
        "margin": rnd("profitMargins", 3), "beta": rnd("beta"), "divY": rnd("dividendYield", 4),
        "tgtMean": rnd("targetMeanPrice"), "tgtHigh": rnd("targetHighPrice"),
        "tgtLow": rnd("targetLowPrice"), "reco": info.get("recommendationKey"),
        "nAnalysts": info.get("numberOfAnalystOpinions"),
        "r1m": ret(21), "r3m": ret(63), "r6m": ret(126), "r1y": ret(252),
    }


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
            "stocks": STOCKS.get(etf, []),
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

    # per-company trend for the drill-down dots
    all_stocks = sorted({s for syms in STOCKS.values() for s in syms})
    print(f">> fetching {len(all_stocks)} companies for drill-down…")
    stock_frames = fetch_many(all_stocks, days=320, use_cache=use_cache)
    valid = {s: df for s, df in stock_frames.items()
             if df is not None and not df.empty and len(df) >= 120}
    stock_info = {sym: _stock_trend(df) for sym, df in valid.items()}

    print(f">> fetching analyst + fundamentals + trusted news for {len(valid)} companies (slow)…")
    from tickline.sentiment import LexiconScorer
    scorer = LexiconScorer()
    company_info = {}
    for i, (sym, df) in enumerate(valid.items(), 1):
        company_info[sym] = _company_brief(sym, df, sess, scorer)
        if i % 25 == 0:
            print(f"   …{i}/{len(valid)}")

    payload = {
        "as_of": str(spy.index[-1].date()),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        "benchmark": BENCH,
        "buzz_median": median,
        "stock_info": stock_info,
        "company_info": company_info,
        "themes": rows,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.js").write_text("window.SIMPLE_DATA = " + json.dumps(payload, indent=2) + ";\n")
    print(f">> wrote web/simple/data.js · {len(rows)} themes · as of {payload['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
