"""Theme-rotation watchlist.

Tracks US AI-connected sub-themes, scores a market thermometer (price,
breadth, volume, ETF flow) and a retail thermometer (sentiment), and
classifies each theme into a rotation state so alerts fire on *state
changes* — not price levels.
"""

from .taxonomy import (
    AI_THEMES,
    ALL_THEMES,
    BENCHMARK,
    GROUPS,
    Theme,
    all_tickers,
    theme_by_key,
    themes_in_group,
)
from .heat import FAST, SLOW, HeatConfig, ThemeHeat, compute_theme_heat
from .state import (
    DEFAULT_STATE_CONFIG,
    RankState,
    StateConfig,
    ThemeState,
    classify,
    play_for,
    rank_play_for,
    rank_states,
)
from .rotation import (
    Transition,
    detect_transitions,
    load_snapshot,
    next_trend_candidates,
    rank_by_rotation,
    save_snapshot,
)

__all__ = [
    "AI_THEMES",
    "ALL_THEMES",
    "BENCHMARK",
    "GROUPS",
    "Theme",
    "all_tickers",
    "theme_by_key",
    "themes_in_group",
    "FAST",
    "SLOW",
    "HeatConfig",
    "ThemeHeat",
    "compute_theme_heat",
    "DEFAULT_STATE_CONFIG",
    "RankState",
    "StateConfig",
    "ThemeState",
    "classify",
    "play_for",
    "rank_play_for",
    "rank_states",
    "Transition",
    "detect_transitions",
    "load_snapshot",
    "next_trend_candidates",
    "rank_by_rotation",
    "save_snapshot",
]
