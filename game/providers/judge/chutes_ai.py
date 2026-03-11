"""chutes.ai judge provider for 20Q referee decisions."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

import bittensor as bt
from openai import NotFoundError, OpenAI

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
        model: str = "openai/gpt-oss-120b-TEE",
        base_url: Optional[str] = None,
        timeout_sec: int = 15,
    ) -> None:
        self.api_key = api_key or os.getenv("CHUTES_API_KEY")
        self.model = model
        self.base_url = (
            base_url or os.getenv("CHUTES_BASE_URL", "https://llm.chutes.ai/v1")
        ).rstrip("/")
        self.timeout_sec = int(timeout_sec)

    async def answer(self, *, secret: str, question: str) -> str:
        if not question or not question.strip():
            bt.logging.info("[20Q] Judge source=none raw='' normalized=unknown")
            return "unknown"

        if not self.api_key or not self.base_url:
            heuristic = self._heuristic_answer(secret=secret, question=question)
            bt.logging.info(
                f"[20Q] Judge source=heuristic raw='' normalized={heuristic}"
            )
            return heuristic

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict 20 Questions referee.\n"
                    "You KNOW the secret word and must judge the question.\n"
                    "Return only valid JSON (no markdown, no extra text) with this exact schema:\n"
                    '{"answer":"yes|no|unknown", "reasoning":"<short reason>"}\n'
                    "The 'answer' field must be exactly one of yes, no, unknown.\n"
                    "Keep reasoning under 12 words.\n"
                    "Use unknown only when the question is ambiguous, subjective, or not decidable from the secret."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Secret word: {secret}\n"
                    f"Question: {question}\n"
                    "Respond as JSON only."
                ),
            },
        ]
        retry_messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict 20 Questions referee.\n"
                    "Return only JSON with this exact shape: "
                    '{"answer":"yes|no|unknown"}\n'
                    "No extra keys. No extra text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Secret word: {secret}\n"
                    f"Question: {question}\n"
                    "Return JSON only."
                ),
            },
        ]

        try:
            model_candidates = [self.model, "openai/gpt-oss-120b-TEE"]
            # Keep order while deduplicating.
            deduped_models = []
            for candidate in model_candidates:
                if candidate and candidate not in deduped_models:
                    deduped_models.append(candidate)

            result = None
            used_model = None
            last_err = None
            for candidate_model in deduped_models:
                try:

                    def _call_default(messages_payload, max_tokens):
                        kwargs = {
                            "model": candidate_model,
                            "messages": messages_payload,
                            "max_tokens": max_tokens,
                            "temperature": 0.0,
                        }
                        try:
                            return client.chat.completions.create(
                                **kwargs,
                                reasoning_effort="low",
                            )
                        except TypeError:
                            return client.chat.completions.create(**kwargs)

                    result = await asyncio.wait_for(
                        asyncio.to_thread(_call_default, messages, 160),
                        timeout=self.timeout_sec,
                    )
                    used_model = candidate_model
                    break
                except NotFoundError as err:
                    last_err = err
                    bt.logging.warning(
                        f"[20Q] Judge model not found: {candidate_model}; trying next."
                    )
                    continue

            if result is None:
                raise last_err or RuntimeError("No valid judge model available")
            text = ""
            reasoning_text = ""
            finish_reason = None
            if result.choices:
                choice = result.choices[0]
                finish_reason = str(choice.finish_reason or "")
                msg = choice.message
                text = str(getattr(msg, "content", "") or "")
                reasoning_text = str(
                    getattr(msg, "reasoning_content", "")
                    or getattr(msg, "reasoning", "")
                    or ""
                )
            normalized_source = text or reasoning_text
            normalized = normalize_yes_no_unknown(normalized_source)
            bt.logging.info(
                "[20Q] Judge source=api "
                f"model={used_model} finish_reason={finish_reason} "
                f"content={text!r} normalized={normalized}"
            )

            # Retry with a tiny answer-only schema if the first call is blank,
            # refusal-like, or truncated before yielding an answer field.
            lowered_source = normalized_source.lower()
            has_answer_field = '"answer"' in lowered_source
            should_retry = (
                not normalized_source.strip()
                or "can't assist" in lowered_source
                or "cannot assist" in lowered_source
                or (finish_reason == "length" and not has_answer_field)
            )
            if should_retry and used_model:
                retry_result = await asyncio.wait_for(
                    asyncio.to_thread(_call_default, retry_messages, 32),
                    timeout=self.timeout_sec,
                )
                retry_text = ""
                retry_reasoning = ""
                retry_finish_reason = None
                if retry_result.choices:
                    retry_choice = retry_result.choices[0]
                    retry_finish_reason = str(retry_choice.finish_reason or "")
                    retry_msg = retry_choice.message
                    retry_text = str(getattr(retry_msg, "content", "") or "")
                    retry_reasoning = str(
                        getattr(retry_msg, "reasoning_content", "")
                        or getattr(retry_msg, "reasoning", "")
                        or ""
                    )
                retry_source = retry_text or retry_reasoning
                retry_normalized = normalize_yes_no_unknown(retry_source)
                bt.logging.info(
                    "[20Q] Judge source=api_retry "
                    f"model={used_model} finish_reason={retry_finish_reason} "
                    f"content={retry_text!r} normalized={retry_normalized}"
                )
                if retry_source.strip():
                    return retry_normalized

                heuristic = self._heuristic_answer(secret=secret, question=question)
                bt.logging.info(
                    "[20Q] Judge source=heuristic_fallback "
                    f"raw={normalized_source!r} normalized={heuristic}"
                )
                return heuristic

            return normalized
        except Exception as err:
            heuristic = self._heuristic_answer(secret=secret, question=question)
            bt.logging.warning(
                f"[20Q] Judge source=heuristic_fallback exception={err} normalized={heuristic}"
            )
            return heuristic

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
        return "unknown"
