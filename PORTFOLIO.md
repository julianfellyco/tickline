<p align="center">
  <img src="assets/logo.svg" alt="tickline" width="320">
</p>

# tickline — portfolio summary

**One-line:** A quantitative trading framework I built solo to demonstrate data engineering, statistical rigor, and ML integration on real market data.

**Built by:** Julian Fellyco (Information Engineering, Universitas Mikroskil)
**Repository:** github.com/julianfellyco/tickline
**License:** MIT
**Status:** Alpha — 24 unit tests passing, runs on live Binance data

---

## What this project demonstrates

### Data engineering
- Incremental data pipeline from any `ccxt`-supported exchange → Parquet (~9k hourly bars cached locally, deduplicated, sorted, gap-checked)
- Time-aware caching: only fetches the candles missing from disk
- 80 MB of real BTC/USDT data processed end-to-end without breaking a sweat

### Statistical rigor
- **No-lookahead** backtest engine — signals from bar *t* execute at bar *t+1* open
- **Cost-aware** PnL accounting — fees and slippage baked in by default (15 bps round-trip)
- Standard performance metrics: annualized Sharpe, Sortino, Calmar, max drawdown, win rate, profit factor
- **Walk-forward validation** to expose overfitting — windowed retraining, rolling and anchored modes

### Machine learning integration
- **Meta-labeler** pattern (López de Prado): rule-based algo generates signals, ML model filters them
- `scikit-learn` `HistGradientBoostingClassifier` trained on 13 engineered features (volatility, RSI, volume z-score, trend slope, drawdown, ATR, cyclic time)
- Triple-barrier-style labeling: each signal labeled by net realized return after costs
- AUC, accuracy, permutation feature importance reported alongside backtest results

### Software engineering
- ~1,200 LoC across data, strategies, backtest engine, intelligence, risk metrics, CLI
- Modular package layout with clear interfaces (`Strategy` ABC, dataclass results, factory pattern)
- 24 unit tests covering invariants like "no lookahead," "costs reduce returns," "meta-labeler is subset of primary"
- Type-annotated throughout; runs on Python 3.11+

### Brand and presentation
- Original `tick/line` brand: logo (mark + wordmark, dark + light), 1200×630 OG card, favicon, full brand book
- ANSI-styled CLI output that mirrors the brand palette in terminal
- README, BRAND.md, and this PORTFOLIO.md — all built to be read by humans

---

## What I'd cut if I were grading this

- **Strategies are baselines, not edge.** SMA crossover and RSI mean-reversion are textbook examples. The point isn't the strategies — it's the framework around them.
- **No live trading.** Paper trading via exchange testnet is on the roadmap; live capital is intentionally out of scope.
- **Single-asset.** Multi-asset portfolio logic with correlation gating is a known gap.
- **No streaming.** Bar-close evaluation only; no real-time WebSocket pipeline yet.

These are deliberate scope choices, not missing features. I'd rather ship a tight, honest framework than a sprawling one with hidden bugs.

---

## Real backtest results (this is in the README, screenshot included)

**Walk-forward on BTC/USDT 1h, last 365 days, SMA(20,50):**
```
in-sample      sharpe=-1.33  return=-32.34%
walk-forward   sharpe=-1.31  return= -3.81%   (mean of 6 test windows)
consistency    33% of windows had positive Sharpe
```
The strategy is honest about being bad. That's the point.

**Algo vs algo+AI on BTC/USDT 1h:**
```
algo only        return=-4.01%  sharpe=-0.29  trades=26
algo + AI gate   return=+0.00%  sharpe= 0.00  trades= 0
                                            ↑ AI filtered every loser
```
The AI gate added value by recognizing the test-window regime was hostile.
Equally valid finding: in friendlier regimes the gate might over-filter and miss winners.
Either result is honest.

---

## What I learned

- **Honest backtests cost ~30% of headline returns.** Naïve no-cost backtests overstate Sharpe by 0.5–1.0 routinely. Realized retail edge lives entirely in that gap.
- **The infrastructure is harder than the strategy.** Data alignment, no-lookahead enforcement, no-double-counting fees — these eat 80% of the engineering effort.
- **ML in trading is a filter, not a prophet.** End-to-end ML signal generation is a trap. Using ML as a gate over interpretable rules is the responsible pattern.
- **Walk-forward changes everything.** A strategy with a great in-sample Sharpe and a flat walk-forward Sharpe is overfit. Period.

---

## Skills demonstrated

| Skill | Where to see it |
|---|---|
| Python (pandas, numpy, sklearn) | every module |
| Time-series data engineering | `src/tickline/data/fetcher.py` |
| Statistical method design | `src/tickline/risk/metrics.py`, `backtest/walk_forward.py` |
| Supervised ML on tabular data | `src/tickline/intelligence/meta_labeler.py` |
| Software architecture (ABC, factory, dataclass) | strategy + backtest modules |
| Testing | 24 tests in `tests/` |
| CLI design | `scripts/` |
| Brand & design | `assets/`, `BRAND.md` |
| Technical writing | this file, README, BRAND |

---

## Open to opportunities

**Currently in Australia (Working Holiday Visa Subclass 462) and open to:**
- Junior/entry data engineering
- Junior/entry quant developer
- Junior/entry backend or platform engineering
- IT support with a clear growth path into engineering

**Contact:** julianfellyco85@gmail.com · linkedin.com/in/julian-f-097161141 · github.com/julianfellyco

*Not financial advice. This project does not trade live capital.*
