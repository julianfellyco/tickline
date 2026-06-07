"""Theme rotation state machine.

Maps the two thermometers (market level+slope, retail level+slope) onto a
rotation state. Alerts fire on *transitions* between these states, never
on price levels — that is the whole anti-noise discipline.

    state          meaning                                play
    DORMANT        nothing notable                        watch
    EMERGING       market leads, crowd asleep             ALPHA — earliest entry
    CONFIRMING     market + crowd both rising              BETA — ride confirmed trend
    CROWDED        both high, crowd accelerating           BETA (late) — trail stops
    EXHAUSTING     crowd euphoric, price stalled/rolling   EXIT / rotate out
    ROLLING_OVER   market leading down                     dead — hunt next leg

Thresholds are PRE-REGISTERED below. They are deliberately crude and
documented; tune them in backtest, not by eyeballing last week's winner.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .heat import ThemeHeat

# ---------------------------------------------------------------------------
# Cross-sectional rank classifier (the BACKTEST-VALIDATED signal).
#
# The per-theme `classify` below keys off slope/acceleration, which the
# event study (scripts/run_watchlist_backtest.py) showed is noise. What
# carried a clean, monotone cross-sectional edge (+8.3% long/short at 63d
# over ~6y) was the rel-strength LEVEL ranked ACROSS themes each day.
#
# rank_states implements that: rank themes by market_level, tag the top
# fraction LEADER (the long), the bottom fraction LAGGARD (the short).
# ---------------------------------------------------------------------------


class RankState(str, Enum):
    LEADER = "leader"     # top rel-strength rank -> long leg
    NEUTRAL = "neutral"   # middle -> no position
    LAGGARD = "laggard"   # bottom rel-strength rank -> short / avoid


RANK_PLAY: dict[RankState, str] = {
    RankState.LEADER: "LONG — strongest leg",
    RankState.NEUTRAL: "flat",
    RankState.LAGGARD: "SHORT / avoid — weakest leg",
}


def rank_states(
    heats: list[ThemeHeat], top_frac: float = 0.3, bottom_frac: float = 0.3
) -> dict[str, RankState]:
    """Cross-sectional classification by rel-strength LEVEL.

    Ranks the supplied themes against each other (point-in-time: pass
    heats computed from the same as-of bar) and tags the top/bottom
    fractions LEADER/LAGGARD. This is the signal the backtest validated.
    """
    if not heats:
        return {}
    ranked = sorted(heats, key=lambda h: h.market_level, reverse=True)
    n = len(ranked)
    n_top = max(1, round(n * top_frac))
    n_bot = max(1, round(n * bottom_frac))
    # never let the long and short books overlap on a small universe
    if n_top + n_bot > n:
        n_bot = max(1, n - n_top)
    out: dict[str, RankState] = {}
    for i, h in enumerate(ranked):
        if i < n_top:
            out[h.key] = RankState.LEADER
        elif i >= n - n_bot:
            out[h.key] = RankState.LAGGARD
        else:
            out[h.key] = RankState.NEUTRAL
    return out


def rank_play_for(state: RankState) -> str:
    return RANK_PLAY[state]


class ThemeState(str, Enum):
    DORMANT = "dormant"
    EMERGING = "emerging"
    CONFIRMING = "confirming"
    CROWDED = "crowded"
    EXHAUSTING = "exhausting"
    ROLLING_OVER = "rolling_over"


# Play classification for each state (for the report + alert routing).
PLAY: dict[ThemeState, str] = {
    ThemeState.DORMANT: "watch",
    ThemeState.EMERGING: "ALPHA — earliest entry",
    ThemeState.CONFIRMING: "BETA — ride confirmed trend",
    ThemeState.CROWDED: "BETA (late) — trail stops",
    ThemeState.EXHAUSTING: "EXIT / rotate out",
    ThemeState.ROLLING_OVER: "dead — hunt next leg",
}

# States worth pushing an alert on when first entered.
ACTIONABLE = {
    ThemeState.EMERGING,
    ThemeState.CONFIRMING,
    ThemeState.EXHAUSTING,
}


@dataclass(frozen=True)
class StateConfig:
    slope_z_rise: float = 0.5  # slope z-score to call market "rising" (tier-agnostic)
    retail_high: float = 1.0   # attention z-score to call the crowd "hot"
    retail_rise: float = 0.5   # attention z-score slope to call crowd "rising"


DEFAULT_STATE_CONFIG = StateConfig()


def classify(heat: ThemeHeat, cfg: StateConfig = DEFAULT_STATE_CONFIG) -> ThemeState:
    """Classify a theme's rotation state from its two thermometers.

    Uses the *normalized* slope (market_slope_z) so one threshold works
    across the fast and slow tiers — see heat.compute_theme_heat.
    """
    msz = heat.market_slope_z
    market_rising = msz > cfg.slope_z_rise
    market_falling = msz < -cfg.slope_z_rise

    rl = heat.retail_level
    rsl = heat.retail_slope

    # --- market-only fallback: no usable retail feed -----------------------
    if rl is None or rsl is None:
        if market_rising:
            return ThemeState.EMERGING
        if market_falling:
            return ThemeState.ROLLING_OVER
        return ThemeState.DORMANT

    retail_hot = rl > cfg.retail_high
    retail_rising = rsl > cfg.retail_rise

    # --- full two-thermometer ladder (order matters) -----------------------
    # 1. crowd euphoric while price no longer rising -> distribution
    if retail_hot and not market_rising:
        return ThemeState.EXHAUSTING
    # 2. market leading down
    if market_falling:
        return ThemeState.ROLLING_OVER
    # 3. rising regimes
    if market_rising and retail_rising:
        return ThemeState.CROWDED if retail_hot else ThemeState.CONFIRMING
    if market_rising and not retail_rising:
        return ThemeState.EMERGING
    return ThemeState.DORMANT


def play_for(state: ThemeState) -> str:
    return PLAY[state]
