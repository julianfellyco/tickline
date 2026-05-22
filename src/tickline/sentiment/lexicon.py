"""Lexicon-based sentiment scorer.

A tiny finance/crypto-tuned word list. Deterministic, offline, no API
key. Score in [-1, 1] per text:
   pos_count - neg_count
   ───────────────────────
   max(1, pos_count + neg_count)

This is intentionally a baseline. For production, swap in an LLM call
(Claude / GPT / a fine-tuned BERT) behind the same interface — the
shape of the output is what the feature pipeline depends on, not the
mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Hand-curated finance/crypto vocabulary. Extend per use case.
_POSITIVE = {
    "bull", "bullish", "rally", "surge", "gain", "gains", "breakout",
    "rise", "rising", "jump", "jumps", "soar", "soars", "ath",
    "all-time-high", "growth", "accumulate", "buy", "long", "longs",
    "partnership", "upgrade", "integration", "approval", "approved",
    "adoption", "etf", "listing", "listed", "mainnet", "launch",
    "milestone", "wins", "beat", "beats", "strong", "robust",
    "optimistic", "momentum", "outperform", "rebound", "recovery",
    "breakthrough", "innovation", "expand", "expansion", "scale",
    "hodl", "moon", "pump", "support",
}

_NEGATIVE = {
    "bear", "bearish", "dump", "crash", "fall", "falls", "drop",
    "drops", "plunge", "plunges", "decline", "declining", "sell",
    "sells", "short", "shorts", "hack", "hacked", "exploit",
    "vulnerability", "lawsuit", "sec", "ban", "banned", "restriction",
    "fud", "scam", "rugpull", "rug-pull", "liquidation", "liquidated",
    "contagion", "default", "bankruptcy", "downturn", "recession",
    "panic", "fear", "doubt", "uncertainty", "weak", "miss",
    "missed", "fail", "fails", "failed", "freeze", "halt", "suspend",
    "delist", "delisted", "resistance", "rejection", "rejected",
    "investigation", "probe", "charges", "fine", "fined",
}

_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z\-]+")


@dataclass(frozen=True)
class LexiconScorer:
    positive: frozenset[str] = frozenset(_POSITIVE)
    negative: frozenset[str] = frozenset(_NEGATIVE)

    def score(self, text: str) -> float:
        if not text:
            return 0.0
        tokens = [t.lower() for t in _TOKEN.findall(text)]
        pos = sum(1 for t in tokens if t in self.positive)
        neg = sum(1 for t in tokens if t in self.negative)
        denom = max(1, pos + neg)
        return (pos - neg) / denom

    def breakdown(self, text: str) -> dict:
        tokens = [t.lower() for t in _TOKEN.findall(text)]
        pos = [t for t in tokens if t in self.positive]
        neg = [t for t in tokens if t in self.negative]
        return {"score": self.score(text), "pos": pos, "neg": neg, "n_tokens": len(tokens)}


_DEFAULT = LexiconScorer()


def score_text(text: str) -> float:
    """Convenience: score a text with the default lexicon."""
    return _DEFAULT.score(text)
