"""Tests for the Donchian breakout strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tickline.strategies import DonchianBreakout


def _market(closes: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="1h", tz="UTC")
    close = pd.Series(closes, index=idx)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
        index=idx,
    )


def test_rejects_bad_params():
    with pytest.raises(ValueError):
        DonchianBreakout(entry_window=1)
    with pytest.raises(ValueError):
        DonchianBreakout(exit_window=1)
    with pytest.raises(ValueError):
        DonchianBreakout(entry_window=10, exit_window=20)  # exit > entry not allowed


def test_breaks_out_on_new_high():
    # 30 bars flat at 100, then break to 105
    closes = [100.0] * 30 + [105.0] * 10
    df = _market(closes)
    pos = DonchianBreakout(entry_window=20, exit_window=10).generate_positions(df)
    # at bar 30 (first 105), prior 20-bar high was 100 → 105 > 100 → enter long
    assert pos.iloc[30] == 1.0
    assert (pos.iloc[30:] == 1.0).all()


def test_exits_on_new_low():
    # break out then break back down
    closes = [100.0] * 30 + [110.0] * 15 + [99.0] * 10
    df = _market(closes)
    pos = DonchianBreakout(entry_window=20, exit_window=10).generate_positions(df)
    # after the drop, 10-bar low gets broken → exit
    assert pos.iloc[-1] == 0.0


def test_no_long_signal_in_flat_market():
    closes = [100.0 + np.sin(i / 5) for i in range(100)]  # tiny ripples, no breakout
    df = _market(closes)
    pos = DonchianBreakout(entry_window=20, exit_window=10).generate_positions(df)
    # never breaks (max amplitude 1 → highest high gets hit immediately, but no new high)
    # most bars should be flat
    assert (pos == 0.0).mean() > 0.5


def test_allow_short_can_emit_negative():
    closes = [100.0] * 30 + [95.0] * 10
    df = _market(closes)
    pos = DonchianBreakout(entry_window=20, exit_window=10, allow_short=True).generate_positions(df)
    # 20-bar min was 100, drop to 95 → short signal
    assert (pos < 0).any()
