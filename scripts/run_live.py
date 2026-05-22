#!/usr/bin/env python3
"""Live trading runner — shadow mode by default.

Reads real OHLCV from the configured exchange (default Binance), feeds
it to a strategy, and either:

  - simulates fills locally (shadow=true, default) — no money at risk
  - places real orders on the exchange's sandbox (sandbox=true, keys set)
  - places real orders on mainnet (sandbox=false, keys set, shadow=false)

Defaults are safe. Mainnet trading requires three explicit env flags.

Usage:
    python scripts/run_live.py --strategy sma_crossover --symbol BTC/USDT \\
        --steps 3 --interval 5

To enable real testnet trading:
    export TICKLINE_API_KEY=...
    export TICKLINE_SECRET=...
    export TICKLINE_SHADOW=false
    python scripts/run_live.py ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest.engine import CostModel
from tickline.live import LiveBroker, LiveConfig, LiveRunner
from tickline.strategies import RSIMeanReversion, SMACrossover

RESET = "\033[0m"
SIGNAL = "\033[38;2;45;209;120m"
ALERT = "\033[38;2;237;93;110m"
AMBER = "\033[38;2;245;166;35m"
INK = "\033[38;2;212;218;227m"
INK_DIM = "\033[38;2;138;150;163m"
INK_FAINT = "\033[38;2;91;101;115m"

BANNER = f"""{INK}
   ┌─────────────────────────────────────────┐
   │  tick{SIGNAL}/{INK}line {INK_FAINT}live{RESET}{INK}                            │
   │  {INK_FAINT}shadow → testnet → mainnet (3 deliberate steps){INK}
   └─────────────────────────────────────────┘{RESET}
"""

STRATEGIES = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}


def main() -> int:
    p = argparse.ArgumentParser(description="Live runner (shadow-safe by default)")
    p.add_argument("--strategy", default="sma_crossover", choices=list(STRATEGIES))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--history", type=int, default=200, help="bars of history per step")
    p.add_argument("--steps", type=int, default=3, help="number of polling iterations")
    p.add_argument("--interval", type=int, default=10, help="seconds between iterations")
    p.add_argument("--capital", type=float, default=10_000.0)
    args = p.parse_args()

    print(BANNER)

    config = LiveConfig.from_env()
    print(f"{INK_FAINT}>>{RESET} config: {INK}{config.summary()}{RESET}")

    if config.can_place_real_orders:
        warn = f"{ALERT}!! REAL ORDERS WILL BE PLACED !!{RESET}" if not config.sandbox else f"{AMBER}testnet orders will be placed{RESET}"
        print(f"{warn}")

    broker = LiveBroker(config=config, cost_model=CostModel(), initial_cash=args.capital)

    # safe ledger path
    safe = args.symbol.replace("/", "-")
    ledger_path = Path(__file__).resolve().parents[1] / "data" / "ledgers" / f"live_{safe}_{args.strategy}.jsonl"
    if ledger_path.exists():
        ledger_path.unlink()

    runner = LiveRunner(
        broker=broker,
        strategy=STRATEGIES[args.strategy](),
        symbol=args.symbol,
        timeframe=args.timeframe,
        history_bars=args.history,
        ledger_path=ledger_path,
    )

    print(f"{INK_FAINT}>>{RESET} strategy: {INK}{args.strategy}{RESET}  symbol: {INK}{args.symbol}{RESET}  tf: {INK}{args.timeframe}{RESET}")
    print(f"{INK_FAINT}>>{RESET} {INK}{args.steps}{RESET} steps · {INK}{args.interval}s{RESET} between\n")

    for i in range(args.steps):
        step = runner.step_once()
        action_color = {
            "hold": INK_FAINT,
            "open_long": SIGNAL,
            "open_short": AMBER,
            "close": ALERT,
        }.get(step.action, INK)
        price = f"${step.fill_price:,.2f}" if step.fill_price else "—"
        target = f"{step.target_position:+.2f}"
        pos = f"{step.current_position:+.6f}"
        ts_str = step.ts.strftime("%Y-%m-%d %H:%M") if step.ts is not None else "—"
        print(
            f"  step {i+1:>2}  {INK_FAINT}{ts_str}{RESET}  "
            f"{action_color}{step.action:<10}{RESET}  "
            f"target {INK}{target:>6}{RESET}  "
            f"pos {INK}{pos}{RESET}  "
            f"px {INK}{price:>12}{RESET}"
            + (f"  {INK_FAINT}{step.note}{RESET}" if step.note else "")
        )
        if i < args.steps - 1:
            import time as _time
            _time.sleep(args.interval)

    print()
    print(f"{INK}final equity:{RESET}  ${broker.equity():,.2f}")
    print(f"{INK}fills:{RESET}         {len(broker.fills)}")
    print(f"{INK}ledger:{RESET}        {INK_DIM}{ledger_path.relative_to(Path.cwd()) if Path.cwd() in ledger_path.parents else ledger_path}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
