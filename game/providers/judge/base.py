"""Base judge interfaces and answer normalization helpers."""

from __future__ import annotations

import json
import re
from typing import Protocol

VALID_BOOLEANISH_ANSWERS = ("yes", "no", "unknown")


def normalize_yes_no_unknown(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return "unknown"

    # Exact short forms first.
    t_simple = t.rstrip(".! ")
    if t_simple in {"yes", "y", "true"}:
        return "yes"
    if t_simple in {"no", "n", "false"}:
        return "no"
    if t_simple in {"unknown", "unsure", "cannot determine", "can't determine"}:
        return "unknown"

    # JSON-ish outputs: {"answer":"yes"} or fenced JSON blocks.
    json_candidates: list[str] = []
    if t.startswith("{") and t.endswith("}"):
        json_candidates.append(t)
    fence_match = re.search(r"```(?:json)?\s*({[\s\S]*?})\s*```", t)
    if fence_match:
        json_candidates.append(fence_match.group(1))
    inline_match = re.search(r"({[\s\S]*})", t)
    if inline_match:
        json_candidates.append(inline_match.group(1))

    for candidate in json_candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                for key in ("answer", "label", "result"):
                    value = payload.get(key)
                    if isinstance(value, str):
                        parsed = normalize_yes_no_unknown(value)
                        if parsed in VALID_BOOLEANISH_ANSWERS:
                            return parsed
        except Exception:
            continue

    # Natural text outputs: "Answer: no", "The answer is yes."
    # Prefer the first explicit standalone label token.
    match = re.search(r"\b(yes|no|unknown|unsure)\b", t)
    if match:
        token = match.group(1)
        if token == "yes":
            return "yes"
        if token == "no":
            return "no"
        return "unknown"

    return "unknown"


class YesNoUnknownJudge(Protocol):
    async def answer(self, *, secret: str, question: str) -> str: ...
