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
  <img alt="tests" src="https://img.shields.io/badge/tests-31%20passing-00ff9d?style=flat-square&labelColor=07090c">
</p>

---

# tickline

A learning-grade quantitative trading framework. Built for research, backtesting, and paper trading — **not** for blind live deployment.

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
│   └── risk/           # performance metrics
├── scripts/            # CLI entry points
├── tests/              # unit tests (31 passing)
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
```

## Roadmap

- [x] Data fetcher (ccxt → parquet, incremental cache)
- [x] Backtest engine with realistic costs + no lookahead
- [x] SMA crossover baseline (algo)
- [x] RSI mean-reversion baseline (algo)
- [x] Risk metrics (Sharpe, Sortino, drawdown, Calmar, profit factor)
- [x] **Walk-forward validation** (anchored + rolling modes)
- [x] **Meta-labeler ML gate** (algo + AI overlay via HistGradientBoosting)
- [x] **Multi-asset portfolio** (equal / inverse-vol / vol-target / fractional Kelly)
- [ ] Sentiment layer (news + onchain → features)
- [ ] Paper trading via exchange testnet
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
