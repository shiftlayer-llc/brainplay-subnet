"""Payload mappers for SuperMario backend contracts."""

from __future__ import annotations

from typing import Any, Dict, Iterable

from game.plugins.supermario.models import (
    SuperMarioAttemptState,
    SuperMarioRoomState,
    SuperMarioStepPayload,
)


def _participant_to_payload(
    participant: SuperMarioAttemptState,
    *,
    steps: Iterable[SuperMarioStepPayload] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "hotkey": participant.hotkey,
        "is_finished": participant.is_finished,
        "finish_reason": participant.finish_reason,
        "score": float(participant.score),
        "env_score": float(participant.env_score),
        "steps_count": int(participant.steps_count),
        "last_frame_id": participant.last_frame_id,
        "last_control": participant.last_control,
        "progress": participant.progress.model_dump(),
    }
    if steps:
        payload["steps"] = [step.model_dump() for step in steps]
    return payload


def make_create_payload(room: SuperMarioRoomState) -> Dict[str, Any]:
    return {
        "validatorKey": room.validator_key,
        "competition": room.competition,
        "participants": [participant.hotkey for participant in room.participants],
        "level": room.level,
        "seed": room.seed,
        "step_limit": int(room.step_limit),
    }


def make_update_payload(
    room: SuperMarioRoomState,
    participants: Iterable[SuperMarioAttemptState] | None = None,
    *,
    steps_by_hotkey: dict[str, list[SuperMarioStepPayload]] | None = None,
) -> Dict[str, Any]:
    changed = (
        list(participants) if participants is not None else list(room.participants)
    )
    return {
        "validatorKey": room.validator_key,
        "competition": room.competition,
        "status": room.status,
        "level": room.level,
        "step_count": int(room.step_count),
        "participants": [
            _participant_to_payload(
                participant,
                steps=(steps_by_hotkey or {}).get(participant.hotkey),
            )
            for participant in changed
        ],
    }


def make_score_payload(room: SuperMarioRoomState, *, reason: str) -> Dict[str, Any]:
    participants = [
        {"hotkey": participant.hotkey, "score": float(participant.score)}
        for participant in room.participants
    ]
    return {"reason": reason, "scores": participants, "participants": participants}
