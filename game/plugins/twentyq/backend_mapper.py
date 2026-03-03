"""Payload mappers between TwentyQ runtime state and backend API contracts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from game.plugins.twentyq.models import TwentyQAttemptState, TwentyQRoomState


def _participant_to_payload(participant: TwentyQAttemptState) -> Dict[str, Any]:
    return {
        "hotkey": participant.hotkey,
        "is_finished": participant.is_finished,
        "finish_reason": participant.finish_reason,
        "question_count": int(participant.question_count),
        "score": float(participant.score),
        "qa_history": [turn.model_dump() for turn in participant.qa_history],
    }


def make_create_payload(room: TwentyQRoomState) -> Dict[str, Any]:
    return {
        "validatorKey": room.validator_key,
        "competition": room.competition,
        "participants": [participant.hotkey for participant in room.participants],
        "word": room.word,
        "question_limit": int(room.question_limit),
        "bonus_limit": int(room.bonus_limit),
    }


def make_update_payload(
    room: TwentyQRoomState, participants: Iterable[TwentyQAttemptState] | None = None
) -> Dict[str, Any]:
    changed = (
        list(participants) if participants is not None else list(room.participants)
    )
    return {
        "validatorKey": room.validator_key,
        "competition": room.competition,
        "status": room.status,
        "question_count": int(room.question_count),
        "participants": [_participant_to_payload(p) for p in changed],
    }


def make_score_payload(
    room: TwentyQRoomState, reason: str = "completed"
) -> Dict[str, Any]:
    scores: List[Dict[str, Any]] = []
    for participant in room.participants:
        scores.append({"hotkey": participant.hotkey, "score": float(participant.score)})
    return {"reason": reason, "scores": scores}
