"""Generic protocol envelope models for multi-game requests/responses."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ProtocolEnvelope(BaseModel):
    """Validator<->miner transport envelope for game payloads."""

    protocol: str = Field(default="brainplay.game")
    version: str = Field(default="1.0")
    game_code: str
    competition_code: Optional[str] = None
    session_id: Optional[str] = None
    attempt_id: Optional[str] = None
    turn_index: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)


class ProtocolResponseEnvelope(BaseModel):
    """Generic response envelope mirroring request metadata where possible."""

    protocol: str = Field(default="brainplay.game")
    version: str = Field(default="1.0")
    game_code: str
    session_id: Optional[str] = None
    attempt_id: Optional[str] = None
    turn_index: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    meta: Dict[str, Any] = Field(default_factory=dict)
