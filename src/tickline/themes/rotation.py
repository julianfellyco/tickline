"""Rotation ranking + transition-based alerting.

Two jobs:
  1. Rank themes by relative-strength *acceleration* so you can see which
     leg money is rotating into (top of list) and out of (bottom).
  2. Diff today's states against the last saved snapshot and emit an alert
     only when a theme *changes state* — the anti-noise rule in code.

Snapshots persist to data/watchlist_snapshot.json so transitions survive
across daily runs (and across the eventual scheduled agent).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .heat import ThemeHeat
from .state import ACTIONABLE, RankState, ThemeState, play_for, rank_play_for

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
SNAPSHOT_PATH = DATA_DIR / "watchlist_snapshot.json"


@dataclass(frozen=True)
class Transition:
    key: str
    label: str
    tier: str               # "fast" or "slow"
    from_state: str | None  # None = first time we've seen this theme
    to_state: str
    play: str
    market_level: float
    market_slope: float
    retail_level: float | None


def rank_by_rotation(heats: list[ThemeHeat]) -> list[ThemeHeat]:
    """Sort themes by rel-strength acceleration (slope), strongest first."""
    return sorted(heats, key=lambda h: (h.market_slope, h.market_level), reverse=True)


def next_trend_candidates(
    heats: list[ThemeHeat], states: dict[str, ThemeState]
) -> list[ThemeHeat]:
    """Themes the watchlist thinks are the *next* leg: early + accelerating."""
    early = {ThemeState.EMERGING, ThemeState.CONFIRMING}
    picks = [h for h in heats if states.get(h.key) in early and h.market_slope > 0]
    return rank_by_rotation(picks)


# --- rank-based (BACKTEST-VALIDATED) rotation -------------------------------
ACTIONABLE_RANK = {RankState.LEADER, RankState.LAGGARD}


def long_short_books(
    heats: list[ThemeHeat], rank_states: dict[str, RankState]
) -> tuple[list[ThemeHeat], list[ThemeHeat]]:
    """(leaders, laggards) sorted by rel-strength level — the long/short books."""
    by_level = sorted(heats, key=lambda h: h.market_level, reverse=True)
    leaders = [h for h in by_level if rank_states.get(h.key) == RankState.LEADER]
    laggards = [h for h in by_level if rank_states.get(h.key) == RankState.LAGGARD]
    return leaders, laggards


def detect_rank_transitions(
    prev_states: dict[str, str],
    curr: dict[str, ThemeHeat],
    curr_states: dict[str, RankState],
    tier: str,
) -> list[Transition]:
    """Alert when a theme enters/leaves the long or short book (rank change)."""
    out: list[Transition] = []
    for key, heat in curr.items():
        new_state = curr_states[key]
        old = prev_states.get(key)
        if old == new_state.value:
            continue
        if old is None and new_state not in ACTIONABLE_RANK:
            continue
        out.append(
            Transition(
                key=key,
                label=heat.label,
                tier=tier,
                from_state=old,
                to_state=new_state.value,
                play=rank_play_for(new_state),
                market_level=heat.market_level,
                market_slope=heat.market_slope,
                retail_level=heat.retail_level,
            )
        )
    return out


def detect_transitions(
    prev_states: dict[str, str],
    curr: dict[str, ThemeHeat],
    curr_states: dict[str, ThemeState],
    tier: str,
) -> list[Transition]:
    """Emit a Transition for every theme whose state changed since last run."""
    out: list[Transition] = []
    for key, heat in curr.items():
        new_state = curr_states[key]
        old = prev_states.get(key)
        if old == new_state.value:
            continue  # no change -> no alert
        # Suppress first-sighting noise: only alert a brand-new theme if it
        # lands directly in an actionable state.
        if old is None and new_state not in ACTIONABLE:
            continue
        out.append(
            Transition(
                key=key,
                label=heat.label,
                tier=tier,
                from_state=old,
                to_state=new_state.value,
                play=play_for(new_state),
                market_level=heat.market_level,
                market_slope=heat.market_slope,
                retail_level=heat.retail_level,
            )
        )
    return out


# --- snapshot persistence ----------------------------------------------------
def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {"as_of": None, "tiers": {}}
    try:
        return json.loads(SNAPSHOT_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"as_of": None, "tiers": {}}


def save_snapshot(as_of: str, tier_states: dict[str, dict[str, ThemeState]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": as_of,
        "tiers": {
            tier: {k: s.value for k, s in states.items()}
            for tier, states in tier_states.items()
        },
    }
    SNAPSHOT_PATH.write_text(json.dumps(payload, indent=2))


def transitions_to_dicts(transitions: list[Transition]) -> list[dict]:
    return [asdict(t) for t in transitions]
