"""20Q protocol models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TwentyQTurn(BaseModel):
    turn: int
    question: str
    answer: str
    guess: Optional[str] = None
    is_correct_guess: Optional[bool] = None
    ts: Optional[int] = None


class TwentyQMinerOutput(BaseModel):
    question: Optional[str] = None
    guess: Optional[str] = None
    reasoning: Optional[str] = None

    def has_action(self) -> bool:
        return bool((self.question or "").strip() or (self.guess or "").strip())


class TwentyQPayload(BaseModel):
    room_id: str
    attempt_id: str
    turn_index: int
    max_questions: int = 20
    max_bonus_questions: int = 5
    secret_hint: Optional[str] = None
    history: List[TwentyQTurn] = Field(default_factory=list)
    last_answer: Optional[str] = None
