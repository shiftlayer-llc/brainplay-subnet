"""chutes.ai judge provider for 20Q referee decisions."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Mapping, Optional

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

    async def answer(
        self,
        *,
        secret: str,
        question: str,
        properties: Mapping[str, object] | None = None,
    ) -> str:
        if not question or not question.strip():
            bt.logging.info("[20Q] Judge source=none raw='' normalized=unknown")
            return "unknown"

        if not self.api_key or not self.base_url:
            heuristic = self._heuristic_answer(
                secret=secret, question=question, properties=properties
            )
            bt.logging.info(
                f"[20Q] Judge source=heuristic raw='' normalized={heuristic}"
            )
            return heuristic

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        normalized_properties = self._normalize_properties(properties)
        properties_json = json.dumps(normalized_properties, sort_keys=True)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a strict 20 Questions referee.\n"
                    "You KNOW the secret word and must judge the question.\n"
                    "Use the provided dataset properties as grounding facts when "
                    "they are relevant to the question.\n"
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
                    f"Dataset properties: {properties_json}\n"
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
                    f"Dataset properties: {properties_json}\n"
                    f"Question: {question}\n"
                    "Return JSON only."
                ),
            },
        ]

        try:
            model_candidates = [
                self.model,
                "openai/gpt-oss-20b-TEE",
                "openai/gpt-oss-120b-TEE",
            ]
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
                except Exception as err:  # noqa: BLE001
                    last_err = err
                    bt.logging.warning(
                        f"[20Q] Judge model failed: {candidate_model}; error={err}; trying next."
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

                heuristic = self._heuristic_answer(
                    secret=secret, question=question, properties=properties
                )
                bt.logging.info(
                    "[20Q] Judge source=heuristic_fallback "
                    f"raw={normalized_source!r} normalized={heuristic}"
                )
                return heuristic

            return normalized
        except Exception as err:
            heuristic = self._heuristic_answer(
                secret=secret, question=question, properties=properties
            )
            bt.logging.warning(
                f"[20Q] Judge source=heuristic_fallback exception={err} normalized={heuristic}"
            )
            return heuristic

    @staticmethod
    def normalize_answer(text: str) -> str:
        return normalize_yes_no_unknown(text)

    @staticmethod
    def _normalize_properties(
        properties: Mapping[str, object] | None,
    ) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for key, value in dict(properties or {}).items():
            key_str = str(key).strip()
            if not key_str:
                continue
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered == "true":
                    normalized[key_str] = True
                elif lowered == "false":
                    normalized[key_str] = False
                else:
                    normalized[key_str] = value.strip()
            else:
                normalized[key_str] = value
        return normalized

    def _heuristic_answer(
        self,
        *,
        secret: str,
        question: str,
        properties: Mapping[str, object] | None = None,
    ) -> str:
        q = (question or "").strip().lower()
        secret_norm = (secret or "").strip().lower()
        if not q or not secret_norm:
            return "unknown"
        if secret_norm in q:
            return "yes"
        props = self._normalize_properties(properties)
        boolean_question_map = {
            "living": ["living", "alive"],
            "animal": ["animal"],
            "plant": ["plant"],
            "food": ["food", "eat", "edible"],
            "vehicle": ["vehicle"],
            "tool": ["tool"],
            "building": ["building"],
            "place": ["place"],
            "profession": ["profession", "job", "occupation"],
            "instrument": ["instrument"],
            "manmade": ["man-made", "manmade", "human-made", "artificial"],
            "natural": ["natural"],
            "portable": ["portable", "carry", "hold"],
            "electronic": ["electronic"],
            "mechanical": ["mechanical"],
            "digital": ["digital"],
            "dangerous": ["dangerous"],
            "liquid": ["liquid"],
            "solid": ["solid"],
            "indoor_use": ["indoors", "indoor"],
            "outdoor_use": ["outdoors", "outdoor"],
            "has_wheels": ["wheels", "wheel"],
            "has_legs": ["legs", "leg"],
            "has_wings": ["wings", "wing"],
            "has_engine": ["engine", "motor"],
            "has_screen": ["screen", "display"],
            "made_of_metal": ["metal"],
            "made_of_wood": ["wood"],
            "made_of_plastic": ["plastic"],
            "made_of_stone": ["stone", "rock"],
            "made_of_fabric": ["fabric", "cloth"],
            "used_for_transport": ["transport", "transportation"],
            "used_for_music": ["music", "musical"],
            "used_for_work": ["work"],
            "used_for_fun": ["fun", "play", "game"],
            "found_in_home": ["home", "household"],
            "found_in_city": ["city", "urban"],
            "found_in_nature": ["nature", "wild"],
            "mechanical_device": ["mechanical device"],
            "digital_device": ["digital device"],
            "consumable": ["consumable"],
            "fragile": ["fragile", "breakable"],
            "heavy": ["heavy"],
            "lightweight": ["lightweight", "light weight"],
            "round_shape": ["round"],
            "rectangular_shape": ["rectangular", "rectangle"],
            "long_shape": ["long"],
            "flat_shape": ["flat"],
            "can_move": ["move", "mobile"],
            "requires_energy": ["electricity", "energy", "power"],
            "handheld": ["handheld", "hold in your hand"],
            "wearable": ["wearable", "wear"],
            "used_outdoors": ["used outdoors"],
            "used_indoors": ["used indoors"],
            "storage_object": ["storage"],
            "container": ["container"],
            "decorative": ["decorative", "decoration"],
            "communication_device": ["communication", "communicate"],
        }
        for prop_name, phrases in boolean_question_map.items():
            prop_value = props.get(prop_name)
            if not isinstance(prop_value, bool):
                continue
            if any(phrase in q for phrase in phrases):
                return "yes" if prop_value else "no"
        return "unknown"
