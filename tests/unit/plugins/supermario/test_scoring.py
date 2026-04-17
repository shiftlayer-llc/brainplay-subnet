from game.plugins.supermario.models import SuperMarioAttemptState
from game.plugins.supermario.scoring import compute_supermario_scores


def test_supermario_scoring_ranks_top_attempt_and_scales_others():
    leader = SuperMarioAttemptState(
        uid=1,
        hotkey="miner-a",
        endpoint="https://a.example",
        had_artifacts=True,
        level_complete=True,
        progress_from_start=120.0,
        env_score=500.0,
        steps_count=100,
        elapsed_s=10.0,
        finish_reason="level_complete",
    )
    follower = SuperMarioAttemptState(
        uid=2,
        hotkey="miner-b",
        endpoint="https://b.example",
        had_artifacts=True,
        progress_from_start=60.0,
        env_score=300.0,
        steps_count=110,
        elapsed_s=12.0,
        finish_reason="timeout",
    )
    failed = SuperMarioAttemptState(
        uid=3,
        hotkey="miner-c",
        endpoint="https://c.example",
        had_artifacts=False,
        finish_reason="error",
    )

    scores = compute_supermario_scores([leader, follower, failed])

    assert scores["miner-a"] == 1.0
    assert scores["miner-b"] == 0.5
    assert scores["miner-c"] == 0.0
