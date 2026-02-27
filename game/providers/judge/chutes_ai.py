"""chutes.ai judge provider scaffold for 20Q-like referee tasks."""

from __future__ import annotations

import os
from typing import Optional

from .base import normalize_yes_no_unknown


class ChutesAIJudge:
    """Provider wrapper scaffold.

    Phase 1 stores configuration and exposes normalization. Network calls are not
    implemented until the 20Q plugin lands.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        model: str = "gpt-oss-120b",
        base_url: Optional[str] = None,
        timeout_sec: int = 15,
    ) -> None:
        self.api_key = api_key or os.getenv("CHUTES_API_KEY")
        self.model = model
        self.base_url = base_url or os.getenv("CHUTES_BASE_URL", "")
        self.timeout_sec = int(timeout_sec)

    async def answer(self, *, secret: str, question: str) -> str:
        raise NotImplementedError(
            "ChutesAIJudge.answer() will be implemented with the 20Q plugin."
        )

    @staticmethod
    def normalize_answer(text: str) -> str:
        return normalize_yes_no_unknown(text)
