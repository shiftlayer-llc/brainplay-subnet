"""20Q runtime state models used by the validator runner."""

from __future__ import annotations

from pydantic import BaseModel, Field

from game.plugins.twentyq.protocol import TwentyQTurn


class TwentyQAttemptState(BaseModel):
    uid: int
    hotkey: str
    endpoint: str
    reasoning_effort: str = "none"
    is_finished: bool = False
    finish_reason: str | None = None
    solved: bool = False
    solved_at_turn: int | None = None
    score: float = 0.0
    invalid_turns: int = 0
    question_count: int = 0
    qa_history: list[TwentyQTurn] = Field(default_factory=list)


class TwentyQRoomState(BaseModel):
    room_id: str
    validator_key: str
    competition: str = "twentyq"
    word: str
    status: str = "running"
    question_limit: int = 20
    bonus_limit: int = 10
    question_count: int = 0
    participants: list[TwentyQAttemptState] = Field(default_factory=list)
    started_at: int
    ended_at: int | None = None
