"""JSON-lines ledger for paper-trading fills.

One line per fill, append-only. Survives across runs so a "session" can
be resumed and audited later. Identical schema to what a real
exchange-side ledger would look like, so future integration is just
swapping the file path for a database URL.
"""

from __future__ import annotations

import json
from pathlib import Path

from .broker import Fill


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, fill: Fill) -> None:
        row = {
            "order_ts": fill.order_ts.isoformat(),
            "fill_ts": fill.fill_ts.isoformat(),
            "symbol": fill.symbol,
            "side": fill.side.value,
            "quantity": fill.quantity,
            "price": fill.price,
            "cost": fill.cost,
            "cash_after": fill.cash_after,
            "position_after": fill.position_after,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line]
