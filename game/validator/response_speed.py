"""
Response speed tracking and reward calculation utilities.
Encourages miners to optimize their code for the shortest latency.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import bittensor as bt
RESPONSE_TIMEOUT_SECONDS = 30.0
SPEED_BONUS_MAX = 0.3
SPEED_PENALTY_MAX = 0.2
FAST_RESPONSE_THRESHOLD = 5.0
SLOW_RESPONSE_THRESHOLD = 20.0
@dataclass
class ResponseMetrics:
    """Tracks response time metrics for a single miner during a game."""
    uid: int
    hotkey: str
    response_times: List[float] = field(default_factory=list)
    timeout_count: int = 0
    total_queries: int = 0
    def record_response(self, response_time: float, timed_out: bool = False) -> None:
        """Record a response time for this miner."""
        self.total_queries += 1
        if timed_out:
            self.timeout_count += 1
            self.response_times.append(RESPONSE_TIMEOUT_SECONDS)
        else:
            self.response_times.append(response_time)
    @property
    def average_response_time(self) -> float:
        """Calculate average response time across all queries."""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)
    @property
    def fastest_response(self) -> float:
        """Get the fastest response time."""
        if not self.response_times:
            return 0.0
        return min(self.response_times)
    @property
    def timeout_rate(self) -> float:
        """Calculate the rate of timeouts."""
        if self.total_queries == 0:
            return 0.0
        return self.timeout_count / self.total_queries
class GameResponseTracker:
    """Tracks response metrics for all miners in a game session."""
    def __init__(self):
        self._metrics: Dict[int, ResponseMetrics] = {}
    def get_or_create_metrics(self, uid: int, hotkey: str) -> ResponseMetrics:
        """Get existing metrics for a miner or create new ones."""
        if uid not in self._metrics:
            self._metrics[uid] = ResponseMetrics(uid=uid, hotkey=hotkey)
        return self._metrics[uid]
    def record_response(
        self,
        uid: int,
        hotkey: str,
        response_time: float,
        timed_out: bool = False
    ) -> None:
        """Record a response for a miner."""
        metrics = self.get_or_create_metrics(uid, hotkey)
        metrics.record_response(response_time, timed_out)
        bt.logging.debug(
            f"Recorded response for UID {uid}: {response_time:.2f}s "
            f"(avg: {metrics.average_response_time:.2f}s, "
            f"timeouts: {metrics.timeout_count}/{metrics.total_queries})"
        )
    def get_metrics(self, uid: int) -> Optional[ResponseMetrics]:
        """Get metrics for a specific miner."""
        return self._metrics.get(uid)
    def get_all_metrics(self) -> Dict[int, ResponseMetrics]:
        """Get all tracked metrics."""
        return self._metrics.copy()
    def calculate_speed_multiplier(self, uid: int) -> float:
        """
        Calculate a speed-based reward multiplier for a miner.
        Returns a value between (1 - SPEED_PENALTY_MAX) and (1 + SPEED_BONUS_MAX).
        - Fast responses (< FAST_RESPONSE_THRESHOLD): bonus up to SPEED_BONUS_MAX
        - Normal responses: multiplier of 1.0
        - Slow responses (> SLOW_RESPONSE_THRESHOLD): penalty up to SPEED_PENALTY_MAX
        - Timeouts: maximum penalty
        """
        metrics = self._metrics.get(uid)
        if not metrics or not metrics.response_times:
            return 1.0
        if metrics.timeout_rate > 0.5:
            return 1.0 - SPEED_PENALTY_MAX
        avg_time = metrics.average_response_time
        if avg_time <= FAST_RESPONSE_THRESHOLD:
            bonus_ratio = 1.0 - (avg_time / FAST_RESPONSE_THRESHOLD)
            return 1.0 + (bonus_ratio * SPEED_BONUS_MAX)
        elif avg_time >= SLOW_RESPONSE_THRESHOLD:
            penalty_ratio = min(
                (avg_time - SLOW_RESPONSE_THRESHOLD) /
                (RESPONSE_TIMEOUT_SECONDS - SLOW_RESPONSE_THRESHOLD),
                1.0
            )
            return 1.0 - (penalty_ratio * SPEED_PENALTY_MAX)
        return 1.0
    def log_game_summary(self) -> None:
        """Log a summary of response metrics for all miners in the game."""
        if not self._metrics:
            return
        bt.logging.info("📊 Response Speed Summary:")
        for uid, metrics in sorted(self._metrics.items()):
            multiplier = self.calculate_speed_multiplier(uid)
            bt.logging.info(
                f"  UID {uid}: avg={metrics.average_response_time:.2f}s, "
                f"fastest={metrics.fastest_response:.2f}s, "
                f"timeouts={metrics.timeout_count}/{metrics.total_queries}, "
                f"multiplier={multiplier:.2f}x"
            )
def apply_speed_multipliers(
    base_rewards: List[float],
    uids: List[int],
    tracker: GameResponseTracker
) -> List[float]:
    """
    Apply speed-based multipliers to base rewards.
    Args:
        base_rewards: List of base reward values
        uids: List of miner UIDs corresponding to rewards
        tracker: GameResponseTracker with recorded metrics
    Returns:
        List of adjusted rewards with speed multipliers applied
    """
    if len(base_rewards) != len(uids):
        bt.logging.warning(
            f"Reward/UID length mismatch: {len(base_rewards)} vs {len(uids)}"
        )
        return base_rewards
    adjusted_rewards = []
    for reward, uid in zip(base_rewards, uids):
        multiplier = tracker.calculate_speed_multiplier(uid)
        adjusted = reward * multiplier
        if multiplier != 1.0:
            bt.logging.debug(
                f"UID {uid}: base={reward:.2f} * speed={multiplier:.2f} = {adjusted:.2f}"
            )
        adjusted_rewards.append(adjusted)
    return adjusted_rewards
