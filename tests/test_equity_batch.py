"""Tests for the batched equity fetcher (mocked — no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tickline.data import fetch_batch

_FIELDS = ["Open", "High", "Low", "Close", "Volume"]


def _fake_download(symbols, **kwargs):
    """Mimic yfinance: flat columns for one ticker, MultiIndex for many."""
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    if len(symbols) == 1:
        return pd.DataFrame({f: np.linspace(100, 120, 60) for f in _FIELDS}, index=idx)
    data, cols = {}, []
    for s in symbols:
        for f in _FIELDS:
            cols.append((s, f))
            data[(s, f)] = np.linspace(100, 120, 60)
    df = pd.DataFrame(data, index=idx)
    df.columns = pd.MultiIndex.from_tuples(cols)
    return df


def test_fetch_batch_parses_and_normalizes(monkeypatch):
    import yfinance as yf
    monkeypatch.setattr(yf, "download", lambda *a, **k: _fake_download(["AAA", "BBB"]))
    out = fetch_batch(["AAA", "BBB"], days=120)
    assert set(out) == {"AAA", "BBB"}
    assert list(out["AAA"].columns) == ["open", "high", "low", "close", "volume"]
    assert str(out["AAA"].index.tz) == "UTC"
    assert len(out["AAA"]) == 60


def test_fetch_batch_drops_thin_tickers(monkeypatch):
    import yfinance as yf

    def short(symbols, **k):
        df = _fake_download(symbols)
        df.iloc[5:, :] = np.nan  # only 5 usable bars -> below min_bars
        return df

    monkeypatch.setattr(yf, "download", short)
    out = fetch_batch(["CCC"], days=120, min_bars=40)
    assert out == {}  # dropped, not a silent half-frame


def test_fetch_batch_empty_input():
    assert fetch_batch([]) == {}
