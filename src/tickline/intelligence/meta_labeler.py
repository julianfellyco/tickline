"""Meta-labeler: an ML gate on top of a rule-based primary strategy.

Pattern from Marcos López de Prado, *Advances in Financial Machine Learning*.

The primary strategy generates signals. The meta-labeler learns from history
which signals were profitable after costs, then filters out the signals the
model thinks won't be. Only trades when *both* the rule and the model agree.

Why this is the safe place to plug in AI:
  1. The model decides *which* signals to take, not *what* to trade.
     If the model is uninformative, you just trade fewer signals.
  2. The model is trained on tabular features with binary labels — a
     well-understood supervised problem, not magic.
  3. The primary strategy is still interpretable. The model only adds a
     gate; it cannot invent positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from ..strategies.base import Strategy


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def build_features(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Build the feature matrix used by the meta-labeler.

    Every feature is causal — it uses only data up to (and including) the
    current bar. No lookahead.

    Feature families:
      momentum/vol     — ret_5, ret_20, vol_20, rsi_14, atr_rel
      trend            — sma_dist, sma_slope (50-bar)
      drawdown         — drawdown_20
      volume regime    — volume_z, volume_trend_5
      higher timeframe — htf_dist_4x, htf_slope_4x, htf_agree
      microstructure   — body_pct, gap_pct, range_pct
      cyclic time      — hour_sin/cos, dow_sin/cos
    """
    close = ohlcv["close"]
    high = ohlcv["high"]
    low = ohlcv["low"]
    open_ = ohlcv["open"]
    volume = ohlcv["volume"]
    returns = close.pct_change()

    feats = pd.DataFrame(index=ohlcv.index)

    # ── momentum / volatility ────────────────────────────────
    feats["vol_20"] = returns.rolling(20).std()
    feats["rsi_14"] = _rsi(close, 14)
    feats["ret_5"] = close.pct_change(5)
    feats["ret_20"] = close.pct_change(20)

    # ── volume regime ────────────────────────────────────────
    vol_mean = volume.rolling(20).mean()
    vol_std = volume.rolling(20).std().replace(0, np.nan)
    feats["volume_z"] = (volume - vol_mean) / vol_std
    feats["volume_trend_5"] = volume.pct_change(5)

    # ── base-timeframe trend (50-bar SMA) ────────────────────
    sma_50 = close.rolling(50).mean()
    feats["sma_dist"] = (close - sma_50) / sma_50
    feats["sma_slope"] = sma_50.pct_change(10)

    # ── higher-timeframe trend (4× and 24× via long base SMAs) ──
    # 4× ≈ a 200-bar slow-moving filter on 1h data ≈ 4h SMA-50
    sma_200 = close.rolling(200).mean()
    feats["htf_dist_4x"] = (close - sma_200) / sma_200
    feats["htf_slope_4x"] = sma_200.pct_change(20)
    # multi-timeframe agreement: do 50-bar and 200-bar slopes have the same sign?
    feats["htf_agree"] = (
        np.sign(feats["sma_slope"].fillna(0))
        * np.sign(feats["htf_slope_4x"].fillna(0))
    ).clip(0, 1)  # 1 if same sign, 0 if opposing/either-zero

    # ── drawdown / structure ─────────────────────────────────
    high_20 = close.rolling(20).max()
    feats["drawdown_20"] = (close - high_20) / high_20

    # ── range / volatility (intra-bar) ───────────────────────
    tr = pd.concat(
        [high - low, (high - close.shift()).abs(), (low - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    feats["atr_rel"] = (tr.rolling(14).mean() / close)

    # ── microstructure (bar shape) ───────────────────────────
    feats["body_pct"] = (close - open_) / open_.replace(0, np.nan)
    feats["range_pct"] = (high - low) / close.replace(0, np.nan)
    feats["gap_pct"] = (open_ / close.shift() - 1.0)

    # ── cyclic time ──────────────────────────────────────────
    if isinstance(ohlcv.index, pd.DatetimeIndex):
        hour = ohlcv.index.hour
        dow = ohlcv.index.dayofweek
        feats["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        feats["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        feats["dow_sin"] = np.sin(2 * np.pi * dow / 7)
        feats["dow_cos"] = np.cos(2 * np.pi * dow / 7)

    return feats


@dataclass
class MetaFitInfo:
    train_auc: float
    test_auc: float
    train_acc: float
    test_acc: float
    n_train_signals: int
    n_test_signals: int
    n_test_signals_passed: int
    base_rate: float
    feature_importance: pd.Series


def _find_entries(positions: pd.Series) -> pd.DatetimeIndex:
    """Return timestamps where the primary strategy opens a long position."""
    prev = positions.shift(1).fillna(0.0)
    entries = (positions > 0) & (prev == 0)
    return positions.index[entries]


def _label_signals(
    ohlcv: pd.DataFrame,
    positions: pd.Series,
    cost_round_trip: float,
) -> pd.DataFrame:
    """For each entry, compute the realized return until the primary exits.

    Returns a DataFrame indexed by entry timestamp with columns:
      entry_loc, exit_loc, entry_px, exit_px, net_return, label
    """
    rows = []
    idx_arr = positions.index
    pos_arr = positions.values
    open_arr = ohlcv["open"].values

    for entry_loc in range(1, len(pos_arr)):
        if pos_arr[entry_loc] > 0 and pos_arr[entry_loc - 1] == 0:
            exit_loc = None
            for j in range(entry_loc + 1, len(pos_arr)):
                if pos_arr[j] == 0:
                    exit_loc = j
                    break
            if exit_loc is None:
                continue
            entry_px = open_arr[entry_loc]
            exit_px = open_arr[exit_loc]
            ret = (exit_px / entry_px - 1.0) - cost_round_trip
            rows.append(
                {
                    "entry_ts": idx_arr[entry_loc],
                    "entry_loc": entry_loc,
                    "exit_loc": exit_loc,
                    "entry_px": entry_px,
                    "exit_px": exit_px,
                    "net_return": ret,
                    "label": int(ret > 0),
                }
            )
    return pd.DataFrame(rows)


class MetaLabeler(Strategy):
    """Wrap a primary Strategy with an ML gate.

    Usage:
        primary = SMACrossover(20, 50)
        meta = MetaLabeler(primary, threshold=0.55)
        meta.fit(train_df)
        positions = meta.generate_positions(test_df)  # filtered
    """

    def __init__(
        self,
        primary: Strategy,
        threshold: float = 0.55,
        cost_round_trip: float = 0.0015,
        random_state: int = 42,
        min_train_signals: int = 30,
    ):
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be in (0, 1)")
        self.primary = primary
        self.threshold = threshold
        self.cost_round_trip = cost_round_trip
        self.random_state = random_state
        self.min_train_signals = min_train_signals
        self.model: Optional[HistGradientBoostingClassifier] = None
        self.feature_cols: Optional[list[str]] = None
        self.last_fit_info: Optional[MetaFitInfo] = None
        self.name = f"meta+{primary.name}"

    # Strategy interface --------------------------------------------------

    def fit(self, ohlcv: pd.DataFrame) -> MetaFitInfo:
        features = build_features(ohlcv)
        positions = self.primary.generate_positions(ohlcv).fillna(0.0)
        signals = _label_signals(ohlcv, positions, self.cost_round_trip)

        if len(signals) < self.min_train_signals:
            raise ValueError(
                f"too few primary signals ({len(signals)}) to train; "
                f"need ≥ {self.min_train_signals}"
            )

        # features at the bar *before* entry (info available at decision time)
        feat_idx = signals["entry_loc"].astype(int) - 1
        feat_idx = feat_idx.clip(lower=0)
        X_full = features.iloc[feat_idx].reset_index(drop=True)
        y_full = signals["label"].astype(int).reset_index(drop=True)

        # drop rows with any NaN features (warmup period)
        mask = X_full.notna().all(axis=1)
        X_full = X_full[mask].reset_index(drop=True)
        y_full = y_full[mask].reset_index(drop=True)

        if len(X_full) < self.min_train_signals:
            raise ValueError(
                f"too few clean signals after dropping NaNs ({len(X_full)})"
            )

        # internal 70/30 holdout so we get an honest test AUC
        n_train = int(len(X_full) * 0.7)
        X_train, X_test = X_full.iloc[:n_train], X_full.iloc[n_train:]
        y_train, y_test = y_full.iloc[:n_train], y_full.iloc[n_train:]

        self.feature_cols = list(X_full.columns)
        self.model = HistGradientBoostingClassifier(
            max_depth=4,
            max_iter=200,
            learning_rate=0.05,
            random_state=self.random_state,
        )
        self.model.fit(X_train, y_train)

        def _auc(y, X):
            if X.empty or y.nunique() < 2:
                return 0.5
            proba = self.model.predict_proba(X)[:, 1]
            return float(roc_auc_score(y, proba))

        def _acc(y, X):
            if X.empty:
                return 0.0
            proba = self.model.predict_proba(X)[:, 1]
            return float(accuracy_score(y, (proba > self.threshold).astype(int)))

        passed = 0
        if not X_test.empty:
            proba_test = self.model.predict_proba(X_test)[:, 1]
            passed = int((proba_test > self.threshold).sum())

        # crude permutation-style importance for the fitted model
        importance = self._compute_importance(X_train, y_train)

        self.last_fit_info = MetaFitInfo(
            train_auc=_auc(y_train, X_train),
            test_auc=_auc(y_test, X_test),
            train_acc=_acc(y_train, X_train),
            test_acc=_acc(y_test, X_test),
            n_train_signals=len(X_train),
            n_test_signals=len(X_test),
            n_test_signals_passed=passed,
            base_rate=float(y_full.mean()) if len(y_full) else 0.0,
            feature_importance=importance,
        )
        return self.last_fit_info

    def generate_positions(self, ohlcv: pd.DataFrame) -> pd.Series:
        if self.model is None:
            raise RuntimeError("MetaLabeler is not fit; call .fit(train_df) first")

        features = build_features(ohlcv)
        positions = self.primary.generate_positions(ohlcv).fillna(0.0)
        out = pd.Series(0.0, index=ohlcv.index, name="position")

        current = 0.0
        feat_cols = list(features.columns)
        feat_values = features.values
        feat_n_cols = feat_values.shape[1]
        for i in range(len(positions)):
            prev = positions.iloc[i - 1] if i > 0 else 0.0
            curr_signal = positions.iloc[i]
            if curr_signal > 0 and prev == 0:
                # entry signal — consult the model
                if i == 0:
                    feat_row = np.full(feat_n_cols, np.nan)
                else:
                    feat_row = feat_values[i - 1]
                if not np.isnan(feat_row).any():
                    feat_df = pd.DataFrame([feat_row], columns=feat_cols)
                    proba = self.model.predict_proba(feat_df)[0, 1]
                    if proba > self.threshold:
                        current = 1.0
            elif curr_signal == 0:
                current = 0.0
            out.iloc[i] = current

        return out

    # internals -----------------------------------------------------------

    def _compute_importance(self, X: pd.DataFrame, y: pd.Series) -> pd.Series:
        """Permutation importance, cheap and model-agnostic."""
        if self.model is None or X.empty:
            return pd.Series(dtype=float)
        rng = np.random.default_rng(self.random_state)
        base_proba = self.model.predict_proba(X)[:, 1]
        base = roc_auc_score(y, base_proba) if y.nunique() > 1 else 0.5
        importances = {}
        for col in X.columns:
            X_shuffled = X.copy()
            X_shuffled[col] = rng.permutation(X_shuffled[col].values)
            shuffled_proba = self.model.predict_proba(X_shuffled)[:, 1]
            auc_shuffled = (
                roc_auc_score(y, shuffled_proba) if y.nunique() > 1 else 0.5
            )
            importances[col] = base - auc_shuffled
        return pd.Series(importances).sort_values(ascending=False)
