#!/usr/bin/env python3
"""Paper trading runner — simulation mode.

Replays cached OHLCV through a strategy via the paper broker. Each
trade is persisted to a JSONL ledger in `data/ledgers/`. This is the
same shape as a live runner; only the bar source would change.

For live trading, you'd replace the cached frame with a WebSocket
subscription, and ledger writes would mirror the exchange's trade
endpoint.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tickline.backtest.engine import CostModel
from tickline.data import fetch_ohlcv, load_cached
from tickline.paper import PaperRunner
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
   │  tick{SIGNAL}/{INK}line {INK_FAINT}paper{INK}                           │
   │  {INK_FAINT}simulation broker · jsonl ledger{INK}         │
   └─────────────────────────────────────────┘{RESET}
"""

STRATEGIES = {
    "sma_crossover": lambda: SMACrossover(fast=20, slow=50),
    "rsi_meanrev": lambda: RSIMeanReversion(period=14, lower=30.0, exit_level=55.0),
}


def _color(value: float) -> str:
    if value > 0:
        return f"{SIGNAL}{value:+.2f}{RESET}"
    if value < 0:
        return f"{ALERT}{value:+.2f}{RESET}"
    return f"{INK}{value:+.2f}{RESET}"


def main() -> int:
    p = argparse.ArgumentParser(description="Paper trading simulation")
    p.add_argument("--strategy", default="sma_crossover", choices=list(STRATEGIES))
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--exchange", default="binance")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--bars", type=int, default=None, help="limit to last N bars")
    p.add_argument("--no-fetch", action="store_true")
    args = p.parse_args()

    print(BANNER)

    if args.no_fetch:
        df = load_cached(args.exchange, args.symbol, args.timeframe)
    else:
        df = fetch_ohlcv(args.symbol, args.timeframe, args.days, args.exchange)
    if df.empty:
        print(f"{ALERT}no data{RESET}")
        return 1
    if args.bars:
        df = df.tail(args.bars)

    print(f"{INK_FAINT}>>{RESET} replaying {len(df)} bars  "
          f"({INK}{df.index[0].date()}{RESET} → {INK}{df.index[-1].date()}{RESET})")

    safe_symbol = args.symbol.replace("/", "-")
    ledger_path = (
        Path(__file__).resolve().parents[1] / "data" / "ledgers" /
        f"paper_{safe_symbol}_{args.strategy}.jsonl"
    )
    # fresh ledger per run for clean comparison
    if ledger_path.exists():
        ledger_path.unlink()

    runner = PaperRunner(
        symbol=args.symbol,
        strategy=STRATEGIES[args.strategy](),
        initial_cash=args.capital,
        cost_model=CostModel(),
        ledger_path=ledger_path,
    )
    print(f"{INK_FAINT}>>{RESET} ledger: {INK_DIM}{ledger_path}{RESET}")
    print(f"{INK_FAINT}>>{RESET} running...\n")

    result = runner.run(df)

    print(f"{INK}Session result:{RESET}")
    print(f"   start equity   ${args.capital:>10,.2f}")
    print(f"   end equity     ${result.final_equity:>10,.2f}")
    print(f"   net pnl        ${result.final_equity - args.capital:>+10,.2f}")
    print(f"   return         {_color(result.total_return_pct)}%")
    print(f"   fills          {result.num_fills}")
    print()

    if result.fills:
        print(f"{INK}First 5 fills:{RESET}")
        for f in result.fills[:5]:
            side_col = SIGNAL if f.side.value == "buy" else ALERT
            print(
                f"   {INK_FAINT}{f.fill_ts.strftime('%Y-%m-%d %H:%M')}{RESET}  "
                f"{side_col}{f.side.value.upper():<4}{RESET}  "
                f"{INK}{f.quantity:>10.4f}{RESET}  @  "
                f"${INK}{f.price:>9,.2f}{RESET}  "
                f"cost ${ALERT}{f.cost:>5.2f}{RESET}"
            )
        if result.num_fills > 5:
            print(f"   {INK_FAINT}... and {result.num_fills - 5} more{RESET}")
        print(f"\n{INK_FAINT}>>{RESET} ledger contains {INK}{result.num_fills}{RESET} fills")
        print(f"{INK_FAINT}>>{RESET} replay with: jq . {ledger_path.relative_to(Path.cwd()) if Path.cwd() in ledger_path.parents else ledger_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
