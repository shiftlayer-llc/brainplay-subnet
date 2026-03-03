"""chutes.ai judge provider for 20Q referee decisions."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from openai import OpenAI

from .base import normalize_yes_no_unknown


class ChutesAIJudge:
    """Provider wrapper for yes/no/unknown answers.

    If credentials/config are absent, falls back to a deterministic local
    heuristic so validator rounds can still run in development.
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
        self.base_url = (base_url or os.getenv("CHUTES_BASE_URL", "")).rstrip("/")
        self.timeout_sec = int(timeout_sec)

    async def answer(self, *, secret: str, question: str) -> str:
        if not question or not question.strip():
            return "unknown"

        if not self.api_key or not self.base_url:
            return self._heuristic_answer(secret=secret, question=question)

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict 20 questions referee. "
                    "Return exactly one word: yes, no, or unknown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Secret word: {secret}\n"
                    f"Question: {question}\n"
                    "Answer with yes/no/unknown only."
                ),
            },
        ]

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model=self.model,
                    messages=messages,
                    max_tokens=3,
                    temperature=0.0,
                ),
                timeout=self.timeout_sec,
            )
            text = result.choices[0].message.content if result.choices else ""
            return normalize_yes_no_unknown(text)
        except Exception:
            return self._heuristic_answer(secret=secret, question=question)

    @staticmethod
    def normalize_answer(text: str) -> str:
        return normalize_yes_no_unknown(text)

    def _heuristic_answer(self, *, secret: str, question: str) -> str:
        q = (question or "").strip().lower()
        secret_norm = (secret or "").strip().lower()
        if not q or not secret_norm:
            return "unknown"
        if secret_norm in q:
            return "yes"
        if q.startswith("is it "):
            tail = q[6:].strip(" ?.!")
            if tail:
                return "no"
        return "unknown"
