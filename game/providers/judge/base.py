"""Base judge interfaces and answer normalization helpers."""

from __future__ import annotations

from typing import Protocol


VALID_BOOLEANISH_ANSWERS = ("yes", "no", "unknown")


def normalize_yes_no_unknown(text: str) -> str:
    t = (text or "").strip().lower().rstrip(".! ")
    if t in {"yes", "y", "true"}:
        return "yes"
    if t in {"no", "n", "false"}:
        return "no"
    if t in {"unknown", "unsure", "cannot determine", "can't determine"}:
        return "unknown"
    return "unknown"


class YesNoUnknownJudge(Protocol):
    async def answer(self, *, secret: str, question: str) -> str: ...
