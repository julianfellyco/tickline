"""Live-trading configuration.

Keys come from environment variables — never the codebase. Defaults are
deliberately safe: sandbox=True, shadow=True.

  TICKLINE_EXCHANGE   ccxt id, defaults 'binance'
  TICKLINE_SANDBOX    'true'/'false', defaults true
  TICKLINE_SHADOW     'true'/'false', defaults true
  TICKLINE_API_KEY    set to actually trade
  TICKLINE_SECRET     set to actually trade

Even with API keys set, shadow mode still simulates fills locally
unless explicitly disabled. Going from shadow → real testnet → real
mainnet is three deliberate environment changes, not an accident.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _envbool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LiveConfig:
    exchange: str = "binance"
    sandbox: bool = True
    shadow: bool = True
    api_key: str | None = None
    secret: str | None = None

    @classmethod
    def from_env(cls, prefix: str = "TICKLINE_") -> "LiveConfig":
        return cls(
            exchange=os.environ.get(f"{prefix}EXCHANGE", "binance"),
            sandbox=_envbool(f"{prefix}SANDBOX", True),
            shadow=_envbool(f"{prefix}SHADOW", True),
            api_key=os.environ.get(f"{prefix}API_KEY"),
            secret=os.environ.get(f"{prefix}SECRET"),
        )

    @property
    def can_place_real_orders(self) -> bool:
        return (
            not self.shadow
            and self.api_key is not None
            and self.secret is not None
        )

    def summary(self) -> str:
        bits = [f"exchange={self.exchange}"]
        bits.append("sandbox=yes" if self.sandbox else "sandbox=no")
        bits.append("shadow=yes" if self.shadow else "shadow=no")
        bits.append("keys=present" if self.api_key else "keys=missing")
        return " · ".join(bits)
