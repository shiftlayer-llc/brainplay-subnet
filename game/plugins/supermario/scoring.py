"""SuperMario scoring helpers."""

from __future__ import annotations

from typing import Iterable

from game.plugins.supermario.models import SuperMarioAttemptState


def compute_supermario_scores(
    participants: Iterable[SuperMarioAttemptState],
) -> dict[str, float]:
    attempts = list(participants)
    eligible = [
        participant
        for participant in attempts
        if participant.had_artifacts
        and participant.finish_reason not in {"error", "invalid_response"}
    ]
    if not eligible:
        return {participant.hotkey: 0.0 for participant in attempts}

    ranked = sorted(
        eligible,
        key=lambda participant: (
            0 if participant.level_complete else 1,
            -float(participant.progress_from_start),
            -float(participant.env_score),
            int(participant.steps_count),
            float(participant.elapsed_s),
        ),
    )
    best_progress = max(float(ranked[0].progress_from_start), 0.0)
    scores: dict[str, float] = {participant.hotkey: 0.0 for participant in attempts}
    for index, participant in enumerate(ranked):
        if index == 0:
            scores[participant.hotkey] = 1.0
            continue
        if best_progress <= 0:
            scores[participant.hotkey] = 0.0
            continue
        score = max(
            0.0, min(1.0, float(participant.progress_from_start) / best_progress)
        )
        scores[participant.hotkey] = score
    return scores
