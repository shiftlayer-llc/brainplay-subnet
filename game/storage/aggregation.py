"""Score aggregation interfaces for weight setting and analytics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from game.validator.scoring_config import parse_interval_to_seconds


@dataclass
class WindowScores:
    avg_scores: Dict[str, float]
    total_scores: Dict[str, float]
    counts: Dict[str, float]


class ScoreAggregator:
    """Aggregator interface backed by legacy and/or generic stores."""

    def __init__(self, *, generic_store=None, legacy_store=None):
        self.generic_store = generic_store
        self.legacy_store = legacy_store

    def window_average_scores_by_hotkey(
        self, competition_code: str, since_ts: float, end_ts: float
    ) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
        if self.legacy_store is not None and competition_code == "codenames":
            return self.legacy_store.window_average_scores_by_hotkey(
                competition_code, since_ts, end_ts
            )
        if self.generic_store is not None:
            return self.generic_store.window_average_scores_by_hotkey(
                competition_code, since_ts, end_ts
            )
        return {}, {}, {}


__all__ = ["ScoreAggregator", "WindowScores", "parse_interval_to_seconds"]
