<p align="center">
  <img src="assets/logo.svg" alt="tickline" width="360">
</p>

<p align="center">
  <em>Honest curves from real ticks.</em>
</p>

<p align="center">
  <a href="#quick-start"><img alt="status" src="https://img.shields.io/badge/status-alpha-00ff9d?style=flat-square&labelColor=07090c"></a>
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-e8eef5?style=flat-square&labelColor=07090c">
  <img alt="license" src="https://img.shields.io/badge/license-MIT-8b96a5?style=flat-square&labelColor=07090c">
  <img alt="tests" src="https://img.shields.io/badge/tests-91%20passing-00ff9d?style=flat-square&labelColor=07090c">
</p>

---

# tickline

A learning-grade quantitative trading framework. Built for research, backtesting, and paper trading — **not** for blind live deployment.

<p align="center">
  <img src="assets/demo/dashboard.gif" alt="tick/line dashboard demo" width="900">
  <br>
  <em>Six-page Streamlit dashboard — overview · backtest · walk-forward · portfolio · consensus · paper ledger</em>
</p>


## Philosophy

> If your backtest doesn't include slippage + fees + realistic fills, it's fiction.

This repo is a portfolio project demonstrating:
- Time-series data engineering
- Strategy research & backtesting
- Risk metrics (Sharpe, Sortino, max drawdown, Calmar)
- Walk-forward validation
- Paper-trading discipline

## Stack

- **Language:** Python 3.11+
- **Data:** `ccxt` (crypto exchanges), `yfinance` (equities fallback)
- **Compute:** `pandas`, `numpy`
- **Storage:** Parquet files (local), optional SQLite
- **Backtest:** Custom event-driven engine (transparent, no magic)
- **Dashboard (later):** Streamlit

## Project layout

```
tickline/
├── src/tickline/
│   ├── data/           # market data fetchers (ccxt → parquet)
│   ├── strategies/     # rule-based signal generators
│   ├── backtest/       # engine + walk-forward validator
│   ├── intelligence/   # ML meta-labeler (algo + AI gate)
│   ├── portfolio/      # multi-asset sizing + risk-parity engine
│   ├── allocation/     # L6 regime gating + vote + DD circuit breaker
│   ├── sentiment/      # lexicon scorer + event feed + bar features
│   ├── paper/          # simulation broker + JSONL ledger
│   ├── live/           # ccxt-backed broker + runner (shadow → testnet → mainnet)
│   └── risk/           # performance metrics
├── scripts/            # CLI entry points
├── dashboard/          # Streamlit explorer (run with `streamlit run dashboard/app.py`)
├── tests/              # unit tests (63 passing)
├── assets/             # brand + logo
├── data/               # cached market data (gitignored)
└── notebooks/          # research notebooks
```

## Quick start

```bash
# 1. Install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Fetch sample data (BTC/USDT, 1h candles, Binance)
python scripts/fetch_data.py --symbol BTC/USDT --timeframe 1h --days 365

# 3. Single backtest (quant + algo)
python scripts/run_backtest.py --strategy sma_crossover

# 4. Walk-forward validation (the overfit detector)
python scripts/run_walk_forward.py --strategy sma_crossover --no-fetch

# 5. Algo + AI gate comparison (the ML layer)
python scripts/run_meta_backtest.py --primary sma_crossover --no-fetch

# 6. Multi-asset portfolio (inverse-vol across BTC / ETH / SOL)
python scripts/run_portfolio_backtest.py --no-fetch \
    --symbols "BTC/USDT" "ETH/USDT" "SOL/USDT" \
    --method inverse_vol

# 7. Sentiment demo (synthetic events → bar features → forward returns)
python scripts/run_sentiment_demo.py --no-fetch

# 8. Paper trading (simulation broker, JSONL ledger)
python scripts/run_paper.py --no-fetch --strategy sma_crossover --bars 2000

# 9. L6 consensus — regime gating + vote ensemble + DD breaker
python scripts/run_consensus.py --no-fetch

# 10. Dashboard (Streamlit; 6 pages)
streamlit run dashboard/app.py

# 11. Live trading — shadow mode, against real Binance market data
python scripts/run_live.py --strategy sma_crossover --symbol BTC/USDT \
    --steps 3 --interval 10

# 12. ATR stop+target comparison — does adding explicit exits help?
python scripts/run_exit_comparison.py --stop-atr 1.0 --target-atr 3.0

# 13. Stacked-layer comparison — HTF trend filter + ATR exits, every combo
python scripts/run_layer_stack.py

# 14. Final scoreboard — every strategy × every wrapper, sorted by Sharpe
python scripts/run_final_scoreboard.py
```

## Going live (carefully)

The `live/` module ships in **shadow mode** by default. Real orders require three deliberate environment flags:

```bash
# step 1 · testnet (safe, no real money)
export TICKLINE_API_KEY=...          # from Binance testnet
export TICKLINE_SECRET=...
export TICKLINE_SHADOW=false         # actually place orders
# TICKLINE_SANDBOX=true is the default

# step 2 · mainnet (real money — only after months of testnet success)
export TICKLINE_SANDBOX=false
```

The same `LiveBroker` / `LiveRunner` code handles all three modes — the strategy doesn't know or care.

## Roadmap

- [x] Data fetcher (ccxt → parquet, incremental cache)
- [x] Backtest engine with realistic costs + no lookahead
- [x] SMA crossover baseline (algo)
- [x] RSI mean-reversion baseline (algo)
- [x] Risk metrics (Sharpe, Sortino, drawdown, Calmar, profit factor)
- [x] **Walk-forward validation** (anchored + rolling modes)
- [x] **Meta-labeler ML gate** (algo + AI overlay via HistGradientBoosting)
- [x] **Multi-asset portfolio** (equal / inverse-vol / vol-target / fractional Kelly)
- [x] **Sentiment layer** (lexicon scorer + event feed + bar-level features)
- [x] **Paper trading** (simulation broker + JSONL ledger; live-ready)
- [x] **L6 consensus** (regime classifier + vote ensemble + drawdown circuit breaker)
- [x] **Streamlit dashboard** (6 pages — overview, backtest, walk-forward, portfolio, consensus, paper ledger)
- [x] **Live trading** (ccxt-backed broker + runner; shadow → testnet → mainnet via env flags)
- [x] **ATR stop-loss / take-profit wrapper** (any Strategy gets explicit exits)
- [x] **Higher-timeframe trend filter** (only trade with the bigger trend; biggest single lift measured)
- [x] **Volatility-targeted sizing** (scale positions to constant annualized vol)
- [x] **Donchian breakout strategy** (classic N-bar high entry / M-bar low exit)
- [x] **Expanded meta-labeler features** (20 features: HTF alignment, microstructure, gaps, volume regime)
- [ ] Streamlit dashboard
- [ ] Live (very small size, well-understood strategy only)

## Hard rules

1. **No live capital** until paper trading shows ≥3 months of consistent results.
2. **Every backtest** must include fees and slippage. The defaults in this repo are intentionally pessimistic.
3. **No overfitting.** If a strategy needs 8 hyperparameters to look good, it's noise.
4. **Position sizing > strategy selection.** A great strategy with bad sizing still blows up.

## Site

The Bloomberg-terminal-style marketing site lives at [`site/index.html`](site/index.html) — single static file, no build step. Open it in a browser or deploy to Vercel/Netlify/GitHub Pages directly.

```bash
open site/index.html
```

## Brand

See [`BRAND.md`](BRAND.md) for palette, typography, voice, and logo usage rules. Live preview at `assets/brand-preview.html` (open in a browser).

## Portfolio summary

See [`PORTFOLIO.md`](PORTFOLIO.md) — a one-page summary of what this project demonstrates, written for hiring managers and recruiters.

## License

MIT — for educational/personal use. Not financial advice.
