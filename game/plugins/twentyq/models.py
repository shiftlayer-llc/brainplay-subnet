"""TwentyQ model placeholder types."""

from __future__ import annotations

from pydantic import BaseModel


class TwentyQAttemptState(BaseModel):
    question_count: int = 0
    solved: bool = False
