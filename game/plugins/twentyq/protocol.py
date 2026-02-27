"""TwentyQ protocol placeholder."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TwentyQTurn(BaseModel):
    question: str
    answer: str


class TwentyQSynapseOutput(BaseModel):
    question: Optional[str] = None
    guess: Optional[str] = None
    reasoning: Optional[str] = None


class TwentyQPayload(BaseModel):
    history: List[TwentyQTurn] = Field(default_factory=list)
    max_questions: int = 20
    max_bonus_questions: int = 5
