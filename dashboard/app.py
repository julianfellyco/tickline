"""tick/line dashboard — Bloomberg-feel Streamlit explorer.

Run with:  streamlit run dashboard/app.py

Pages:
  · Overview      — project state, KPIs, layer status
  · Backtest      — pick strategy/symbol, see equity + metrics
  · Walk-Forward  — per-window in/out-of-sample comparison
  · Portfolio     — multi-asset sizing + correlation heatmap
  · Consensus     — regime-gated comparison (L6)
  · Paper Ledger  — replay + browse JSONL trades
"""

from __future__ import annotations

import sys
from pathlib import Path

import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tickline.allocation import (
    DrawdownCircuitBreaker,
    Regime,
    RegimeClassifier,
    RegimeGatedStrategy,
)
from tickline.backtest import Backtester, CostModel, run_walk_forward
from tickline.data import load_cached
from tickline.portfolio import Portfolio, Sleeve, SizingMethod
from tickline.paper import PaperRunner
from tickline.risk import compute_metrics
from tickline.strategies import RSIMeanReversion, SMACrossover

# ─── PALETTE (matches BRAND.md) ──────────────────────────────
BG_DEEP    = "#0b1015"
BG_PANEL   = "#0f161d"
BG_ROW     = "#131b24"
LINE       = "#1a232c"
INK        = "#d4dae3"
INK_DIM    = "#8a96a3"
INK_FAINT  = "#5b6573"
SIGNAL     = "#2dd178"
ALERT      = "#ed5d6e"
AMBER      = "#f5a623"

st.set_page_config(
    page_title="tick/line — dashboard",
    page_icon=str(ROOT / "assets" / "favicon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── GLOBAL STYLES ───────────────────────────────────────────
st.markdown(
    f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500&family=IBM+Plex+Mono:wght@400;500&display=swap');
      html, body, [class*="css"] {{
          font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
          background-color: {BG_DEEP} !important;
          color: {INK} !important;
      }}
      .stApp, section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div {{
          background-color: {BG_DEEP} !important;
      }}
      h1, h2, h3, h4 {{ color: {INK}; font-weight: 500; letter-spacing: -0.02em; }}
      .stMarkdown code, .stCode, pre, code {{
          font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
          background-color: {BG_PANEL} !important;
          color: {INK} !important;
      }}
      .stMetric {{
          background-color: {BG_PANEL};
          padding: 14px 18px;
          border: 1px solid {LINE};
          border-radius: 4px;
      }}
      [data-testid="stMetricValue"] {{
          font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
          font-weight: 500 !important;
          letter-spacing: -0.02em !important;
      }}
      [data-testid="stMetricLabel"] {{
          font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
          font-size: 10px !important;
          text-transform: uppercase !important;
          letter-spacing: 0.2em !important;
          color: {INK_FAINT} !important;
      }}
      [data-baseweb="select"] > div, .stSelectbox div[data-baseweb="select"] {{
          background-color: {BG_PANEL} !important;
          border-color: {LINE} !important;
      }}
      .stRadio > label > div, .stRadio label, .stRadio p {{
          font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
          font-size: 13px !important;
          letter-spacing: 0.02em !important;
      }}
      .stSlider [data-baseweb="slider"] {{ color: {SIGNAL} !important; }}
      .stButton button {{
          background-color: {SIGNAL} !important;
          color: {BG_DEEP} !important;
          font-family: 'IBM Plex Mono', ui-monospace, monospace !important;
          font-weight: 500 !important;
          border: none !important;
          border-radius: 4px !important;
      }}
      .stDataFrame {{
          background-color: {BG_PANEL} !important;
      }}
      .tlhead {{
          font-family: 'IBM Plex Mono', ui-monospace, monospace;
          font-size: 11px;
          color: {SIGNAL};
          letter-spacing: 0.22em;
          text-transform: uppercase;
          padding: 4px 10px;
          background-color: rgba(45, 209, 120, 0.07);
          border-radius: 3px;
          display: inline-block;
          margin-bottom: 14px;
      }}
      .tlsub {{ color: {INK_DIM}; font-size: 14px; margin-top: -8px; }}
      hr {{ border-color: {LINE} !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── HELPERS ─────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_data(exchange: str, symbol: str, timeframe: str) -> pd.DataFrame:
    return load_cached(exchange, symbol, timeframe)


def list_cached_symbols() -> list[tuple[str, str, str]]:
    """Return (exchange, symbol, timeframe) tuples for every parquet on disk."""
    data_dir = ROOT / "data"
    if not data_dir.exists():
        return []
    out = []
    for p in sorted(data_dir.glob("*.parquet")):
        parts = p.stem.split("_")
        if len(parts) >= 3:
            exchange = parts[0]
            timeframe = parts[-1]
            symbol = "_".join(parts[1:-1]).replace("-", "/")
            out.append((exchange, symbol, timeframe))
    return out


def equity_chart(equity: pd.Series, title: str, benchmark: pd.Series | None = None) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity.index, y=equity.values,
        mode="lines", line=dict(color=SIGNAL, width=2),
        name="strategy",
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:,.2f}<extra></extra>",
    ))
    if benchmark is not None:
        fig.add_trace(go.Scatter(
            x=benchmark.index, y=benchmark.values,
            mode="lines", line=dict(color=INK_FAINT, width=1, dash="dot"),
            name="buy & hold",
            hovertemplate="%{x|%Y-%m-%d %H:%M}<br>$%{y:,.2f}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=title, font=dict(family="IBM Plex Sans", size=14, color=INK_DIM)),
        plot_bgcolor=BG_PANEL,
        paper_bgcolor=BG_PANEL,
        font=dict(family="IBM Plex Mono", color=INK, size=11),
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=True,
        legend=dict(font=dict(size=10, color=INK_DIM)),
        xaxis=dict(gridcolor=LINE, zerolinecolor=LINE, color=INK_FAINT),
        yaxis=dict(gridcolor=LINE, zerolinecolor=LINE, color=INK_FAINT, tickprefix="$"),
        hoverlabel=dict(bgcolor=BG_ROW, font=dict(family="IBM Plex Mono", color=INK)),
        height=420,
    )
    return fig


def heatmap(corr: pd.DataFrame, title: str) -> go.Figure:
    fig = go.Figure(data=go.Heatmap(
        z=corr.values,
        x=corr.columns,
        y=corr.index,
        colorscale=[[0, ALERT], [0.5, BG_PANEL], [1, SIGNAL]],
        zmid=0,
        text=corr.round(2).values,
        texttemplate="%{text}",
        textfont=dict(family="IBM Plex Mono", size=11, color=INK),
        colorbar=dict(tickfont=dict(family="IBM Plex Mono", color=INK_FAINT, size=10)),
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(family="IBM Plex Sans", size=14, color=INK_DIM)),
        plot_bgcolor=BG_PANEL,
        paper_bgcolor=BG_PANEL,
        font=dict(family="IBM Plex Mono", color=INK_FAINT, size=11),
        margin=dict(l=10, r=10, t=40, b=10),
        height=380,
    )
    return fig


STRATEGIES = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}

# ─── SIDEBAR ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f"""
        <div style="font-family: 'IBM Plex Mono', monospace; font-weight: 500;
                    font-size: 22px; letter-spacing: -0.02em; padding-bottom: 12px;
                    border-bottom: 1px solid {LINE}; margin-bottom: 18px;">
            tick<span style="color: {SIGNAL}">/</span>line
            <div style="font-size: 10px; color: {INK_FAINT}; letter-spacing: 0.2em;
                        margin-top: 4px;">v0.1.0 · alpha</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    page = st.radio(
        "view",
        ["Overview", "Backtest", "Walk-forward", "Portfolio", "Consensus", "Paper ledger"],
        label_visibility="collapsed",
    )
    st.markdown(f"<hr style='margin: 16px 0; border-color: {LINE}'/>", unsafe_allow_html=True)
    cached = list_cached_symbols()
    if cached:
        st.markdown(f"<div style='color: {INK_FAINT}; font-family: IBM Plex Mono; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 8px'>cached data</div>", unsafe_allow_html=True)
        for exchange, symbol, tf in cached:
            st.markdown(
                f"<div style='font-family: IBM Plex Mono; font-size: 11px; color: {INK_DIM}; padding: 2px 0;'>"
                f"<span style='color: {SIGNAL}'>●</span> {symbol} <span style='color: {INK_FAINT}'>· {tf} · {exchange}</span></div>",
                unsafe_allow_html=True,
            )
    st.markdown(f"<hr style='margin: 16px 0; border-color: {LINE}'/>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-family: IBM Plex Mono; font-size: 10.5px; color: {INK_FAINT}; line-height: 1.6'>"
        f"<a style='color: {INK_DIM}; text-decoration: none' href='https://github.com/julianfellyco/tickline'>$ github →</a><br>"
        f"<span style='color: {AMBER}'>not financial advice</span></div>",
        unsafe_allow_html=True,
    )

# ─── PAGES ───────────────────────────────────────────────────

def page_overview():
    st.markdown('<div class="tlhead">▌ 00 · overview</div>', unsafe_allow_html=True)
    st.markdown("# Project state")
    st.markdown(
        f"<p class='tlsub'>A learning-grade quantitative trading framework. "
        f"Honest backtests. Real costs. Quant + algo + AI on real BTC, ETH, SOL data.</p>",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("tests", "45 / 45")
    c2.metric("modules", "7 shipped")
    c3.metric("commits", "≥ 4")
    c4.metric("license", "MIT")

    st.markdown("### Layer status")
    layers = [
        ("L6", "Allocation & Consensus",  "shipped", "regime gating · vote · drawdown breaker"),
        ("L5", "Intelligence",            "shipped", "algo (SMA, RSI) + AI meta-labeler + sentiment"),
        ("L4", "Portfolio Logic",         "shipped", "equal · inverse-vol · vol-target · ¼ Kelly"),
        ("L3", "Execution",               "shipped", "vectorized backtest · no lookahead · real costs"),
        ("L2", "Settlement",              "paper",   "PaperBroker + JSONL ledger · live one class away"),
        ("L1", "Physical Infrastructure", "shipped", "ccxt → parquet incremental · 8,760 bars cached"),
    ]
    for lid, name, status, role in layers:
        color = SIGNAL if status == "shipped" else AMBER
        st.markdown(
            f"<div style='display: grid; grid-template-columns: 50px 220px 90px 1fr; gap: 14px; "
            f"padding: 10px 16px; border-left: 2px solid {color}; background: {BG_PANEL}; "
            f"font-family: IBM Plex Mono; font-size: 12px; margin-bottom: 4px; align-items: center;'>"
            f"<span style='color: {SIGNAL}; font-weight: 600;'>{lid}</span>"
            f"<span style='color: {INK}'>{name}</span>"
            f"<span style='color: {color}; text-transform: uppercase; letter-spacing: 0.18em; font-size: 10px;'>{status}</span>"
            f"<span style='color: {INK_FAINT};'>{role}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


def page_backtest():
    st.markdown('<div class="tlhead">▌ 01 · backtest</div>', unsafe_allow_html=True)
    st.markdown("# Run a single backtest")

    cached = list_cached_symbols()
    if not cached:
        st.warning("No cached data yet. Run `python scripts/fetch_data.py` first.")
        return

    symbols = sorted({s for _, s, _ in cached})
    timeframes = sorted({tf for _, _, tf in cached})

    c1, c2, c3 = st.columns(3)
    symbol = c1.selectbox("symbol", symbols, index=symbols.index("BTC/USDT") if "BTC/USDT" in symbols else 0)
    strategy_name = c2.selectbox("strategy", list(STRATEGIES))
    timeframe = c3.selectbox("timeframe", timeframes, index=timeframes.index("1h") if "1h" in timeframes else 0)

    fee_bps = st.slider("round-trip fee (bps)", 0, 50, 10)
    slip_bps = st.slider("slippage (bps)", 0, 50, 5)

    if st.button("RUN BACKTEST", type="primary"):
        df = load_data("binance", symbol, timeframe)
        if df.empty:
            st.error("No data found for this combination.")
            return
        bt = Backtester(cost_model=CostModel(fee_bps=fee_bps, slippage_bps=slip_bps))
        result = bt.run(df, STRATEGIES[strategy_name]())
        metrics = compute_metrics(result.returns, result.equity_curve, result.trades, timeframe)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("return", f"{metrics.total_return_pct:+.2f}%")
        c2.metric("sharpe (ann.)", f"{metrics.sharpe:+.2f}")
        c3.metric("max DD", f"{metrics.max_drawdown_pct:.2f}%")
        c4.metric("trades", metrics.num_trades)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("win rate", f"{metrics.win_rate_pct:.1f}%")
        c2.metric("profit factor", f"{metrics.profit_factor:.2f}")
        c3.metric("CAGR", f"{metrics.cagr_pct:+.2f}%")
        c4.metric("vol (ann.)", f"{metrics.volatility_pct:.2f}%")

        bh = (1 + df["close"].pct_change().fillna(0.0)).cumprod() * 10_000
        st.plotly_chart(equity_chart(result.equity_curve, f"{symbol} {strategy_name} — equity curve", benchmark=bh), use_container_width=True)

        if not result.trades.empty:
            st.markdown("### Last 10 trades")
            st.dataframe(result.trades.tail(10), use_container_width=True)


def page_walk_forward():
    st.markdown('<div class="tlhead">▌ 02 · walk-forward</div>', unsafe_allow_html=True)
    st.markdown("# Walk-forward validation")
    st.markdown(f"<p class='tlsub'>Rolling train/test windows expose overfit before live capital does.</p>", unsafe_allow_html=True)

    cached = list_cached_symbols()
    if not cached:
        st.warning("No cached data yet.")
        return
    symbols = sorted({s for _, s, _ in cached})

    c1, c2, c3, c4 = st.columns(4)
    symbol = c1.selectbox("symbol", symbols, key="wf_sym")
    strategy_name = c2.selectbox("strategy", list(STRATEGIES), key="wf_strat")
    train_bars = c3.number_input("train bars", min_value=500, max_value=5000, value=2000, step=200)
    test_bars = c4.number_input("test bars", min_value=200, max_value=3000, value=1000, step=100)
    mode = st.radio("mode", ["anchored", "rolling"], horizontal=True)

    if st.button("RUN WALK-FORWARD", type="primary"):
        df = load_data("binance", symbol, "1h")
        if df.empty:
            st.error("No data.")
            return
        wf = run_walk_forward(
            df, strategy_factory=STRATEGIES[strategy_name],
            train_bars=int(train_bars), test_bars=int(test_bars), mode=mode,
        )
        summary = wf.summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("avg sharpe", f"{wf.aggregate_sharpe():+.2f}")
        c2.metric("avg return", f"{wf.aggregate_return_pct():+.2f}%")
        c3.metric("consistency", f"{wf.sharpe_consistency() * 100:.0f}%")

        st.dataframe(summary, use_container_width=True)

        # window returns bar chart
        fig = go.Figure()
        colors = [SIGNAL if r > 0 else ALERT for r in summary["return_pct"]]
        fig.add_trace(go.Bar(
            x=[f"w{int(w)}" for w in summary["window"]],
            y=summary["return_pct"],
            marker_color=colors,
        ))
        fig.update_layout(
            plot_bgcolor=BG_PANEL, paper_bgcolor=BG_PANEL,
            font=dict(family="IBM Plex Mono", color=INK_FAINT, size=11),
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(gridcolor=LINE, color=INK_FAINT),
            yaxis=dict(gridcolor=LINE, color=INK_FAINT, ticksuffix="%"),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)


def page_portfolio():
    st.markdown('<div class="tlhead">▌ 03 · portfolio</div>', unsafe_allow_html=True)
    st.markdown("# Multi-asset portfolio")

    cached = list_cached_symbols()
    if not cached:
        st.warning("No cached data yet.")
        return
    symbols = sorted({s for _, s, _ in cached})
    if len(symbols) < 2:
        st.warning("Need at least 2 cached symbols.")
        return

    chosen = st.multiselect("sleeves", symbols, default=symbols[:3])
    strategy_name = st.selectbox("strategy per sleeve", list(STRATEGIES))
    method = st.selectbox("sizing method", [m.value for m in SizingMethod])
    lookback = st.slider("lookback (bars)", 10, 200, 30)

    if st.button("RUN PORTFOLIO", type="primary") and chosen:
        sleeves = []
        common = None
        for sym in chosen:
            df = load_data("binance", sym, "1h")
            if df.empty:
                continue
            common = df.index if common is None else common.intersection(df.index)
            sleeves.append((sym, df))

        if not sleeves:
            st.error("No data for selected sleeves.")
            return

        aligned = [Sleeve(name=s, ohlcv=df.loc[common], strategy=STRATEGIES[strategy_name]())
                   for s, df in sleeves]
        portfolio = Portfolio(aligned, initial_capital=10_000.0)
        result = portfolio.run(method=method, lookback=lookback)
        metrics = compute_metrics(
            result.returns, result.equity_curve,
            pd.DataFrame(columns=["pnl_pct"]), "1h",
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("portfolio return", f"{result.total_return_pct:+.2f}%")
        c2.metric("sharpe (ann.)", f"{metrics.sharpe:+.2f}")
        c3.metric("max DD", f"{metrics.max_drawdown_pct:.2f}%")
        c4.metric("vol (ann.)", f"{metrics.volatility_pct:.2f}%")

        st.plotly_chart(equity_chart(result.equity_curve, "Portfolio equity"), use_container_width=True)

        # contributions
        contribs = result.contributions()
        fig = go.Figure()
        colors = [SIGNAL if c > 0 else ALERT for c in contribs.values]
        fig.add_trace(go.Bar(
            x=list(contribs.index), y=contribs.values, marker_color=colors,
        ))
        fig.update_layout(
            title=dict(text="Sleeve contributions (pp)", font=dict(family="IBM Plex Sans", size=14, color=INK_DIM)),
            plot_bgcolor=BG_PANEL, paper_bgcolor=BG_PANEL,
            font=dict(family="IBM Plex Mono", color=INK_FAINT, size=11),
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis=dict(gridcolor=LINE, color=INK_FAINT),
            yaxis=dict(gridcolor=LINE, color=INK_FAINT, ticksuffix="pp"),
            height=320,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.plotly_chart(heatmap(result.correlation, "Realized sleeve correlation"), use_container_width=True)


def page_consensus():
    st.markdown('<div class="tlhead">▌ 04 · consensus</div>', unsafe_allow_html=True)
    st.markdown("# Regime-gated consensus")
    st.markdown(f"<p class='tlsub'>Different strategies are authorized to trade in different market regimes.</p>", unsafe_allow_html=True)

    cached = list_cached_symbols()
    if not cached:
        st.warning("No cached data yet.")
        return
    symbols = sorted({s for _, s, _ in cached})

    c1, c2, c3 = st.columns(3)
    symbol = c1.selectbox("symbol", symbols, key="cs_sym")
    lookback = c2.slider("regime lookback (bars)", 20, 200, 50)
    threshold = c3.slider("trend threshold (× vol)", 0.5, 3.0, 1.0, 0.1)

    if st.button("ANALYZE", type="primary"):
        df = load_data("binance", symbol, "1h")
        if df.empty:
            st.error("No data.")
            return
        classifier = RegimeClassifier(lookback=lookback, trend_threshold=threshold)
        regimes = classifier.classify(df)
        counts = regimes.value_counts()

        c1, c2, c3 = st.columns(3)
        c1.metric("trend-up bars",   f"{int(counts.get(Regime.TREND_UP, 0)):,}",   delta=f"{int(counts.get(Regime.TREND_UP, 0))/len(df)*100:.1f}%")
        c2.metric("range bars",      f"{int(counts.get(Regime.RANGE, 0)):,}",      delta=f"{int(counts.get(Regime.RANGE, 0))/len(df)*100:.1f}%")
        c3.metric("trend-down bars", f"{int(counts.get(Regime.TREND_DOWN, 0)):,}", delta=f"{int(counts.get(Regime.TREND_DOWN, 0))/len(df)*100:.1f}%")

        # plot price colored by regime
        color_map = {Regime.TREND_UP: SIGNAL, Regime.RANGE: AMBER, Regime.TREND_DOWN: ALERT}
        fig = go.Figure()
        for regime in [Regime.TREND_UP, Regime.RANGE, Regime.TREND_DOWN]:
            mask = regimes == regime
            fig.add_trace(go.Scatter(
                x=df.index[mask], y=df["close"][mask],
                mode="markers",
                marker=dict(color=color_map[regime], size=2),
                name=regime.value,
            ))
        fig.update_layout(
            title=dict(text=f"{symbol} close, colored by regime", font=dict(family="IBM Plex Sans", size=14, color=INK_DIM)),
            plot_bgcolor=BG_PANEL, paper_bgcolor=BG_PANEL,
            font=dict(family="IBM Plex Mono", color=INK, size=11),
            margin=dict(l=10, r=10, t=40, b=10),
            xaxis=dict(gridcolor=LINE, color=INK_FAINT),
            yaxis=dict(gridcolor=LINE, color=INK_FAINT, tickprefix="$"),
            legend=dict(font=dict(size=10, color=INK_DIM)),
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)

        # consensus backtest comparison
        st.markdown("### Comparison")
        bt = Backtester(cost_model=CostModel())
        sma = SMACrossover(fast=20, slow=50)
        rsi = RSIMeanReversion(period=14, lower=30.0, exit_level=55.0)
        gated = RegimeGatedStrategy(
            regime_map={
                Regime.TREND_UP: SMACrossover(fast=20, slow=50),
                Regime.RANGE: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
            },
            classifier=classifier,
        )
        rows = []
        for name, strat in [("SMA only", sma), ("RSI only", rsi), ("regime-gated", gated)]:
            r = bt.run(df, strat)
            m = compute_metrics(r.returns, r.equity_curve, r.trades, "1h")
            rows.append({
                "strategy": name,
                "return_pct": round(m.total_return_pct, 2),
                "sharpe": round(m.sharpe, 2),
                "max_dd": round(m.max_drawdown_pct, 2),
                "trades": m.num_trades,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


def page_paper():
    st.markdown('<div class="tlhead">▌ 05 · paper ledger</div>', unsafe_allow_html=True)
    st.markdown("# Paper trading ledger")
    st.markdown(f"<p class='tlsub'>Same JSONL schema a real exchange would write.</p>", unsafe_allow_html=True)

    ledgers_dir = ROOT / "data" / "ledgers"
    ledger_files = sorted(ledgers_dir.glob("*.jsonl")) if ledgers_dir.exists() else []

    if not ledger_files:
        st.info("No ledgers yet. Run `python scripts/run_paper.py --no-fetch` to generate one.")
        return

    selected = st.selectbox("ledger", [p.name for p in ledger_files])
    path = ledgers_dir / selected
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    if not rows:
        st.warning("ledger is empty")
        return

    df = pd.DataFrame(rows)
    df["fill_ts"] = pd.to_datetime(df["fill_ts"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("fills", len(df))
    c2.metric("first fill", df["fill_ts"].min().strftime("%Y-%m-%d"))
    c3.metric("last fill", df["fill_ts"].max().strftime("%Y-%m-%d"))
    final_cash = df["cash_after"].iloc[-1]
    final_pos = df["position_after"].iloc[-1]
    last_price = df["price"].iloc[-1]
    final_equity = final_cash + final_pos * last_price
    c4.metric("equity (mark)", f"${final_equity:,.2f}")

    st.dataframe(df, use_container_width=True)

    # buy/sell scatter
    fig = go.Figure()
    buys = df[df["side"] == "buy"]
    sells = df[df["side"] == "sell"]
    fig.add_trace(go.Scatter(x=buys["fill_ts"], y=buys["price"], mode="markers",
                             marker=dict(color=SIGNAL, size=8, symbol="triangle-up"),
                             name="buy"))
    fig.add_trace(go.Scatter(x=sells["fill_ts"], y=sells["price"], mode="markers",
                             marker=dict(color=ALERT, size=8, symbol="triangle-down"),
                             name="sell"))
    fig.update_layout(
        title=dict(text="Fills timeline", font=dict(family="IBM Plex Sans", size=14, color=INK_DIM)),
        plot_bgcolor=BG_PANEL, paper_bgcolor=BG_PANEL,
        font=dict(family="IBM Plex Mono", color=INK, size=11),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(gridcolor=LINE, color=INK_FAINT),
        yaxis=dict(gridcolor=LINE, color=INK_FAINT, tickprefix="$"),
        legend=dict(font=dict(size=10, color=INK_DIM)),
        height=380,
    )
    st.plotly_chart(fig, use_container_width=True)


# ─── ROUTER ──────────────────────────────────────────────────
{
    "Overview": page_overview,
    "Backtest": page_backtest,
    "Walk-forward": page_walk_forward,
    "Portfolio": page_portfolio,
    "Consensus": page_consensus,
    "Paper ledger": page_paper,
}[page]()
