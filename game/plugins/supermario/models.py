"""SuperMario validator runtime state."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SuperMarioProgress(BaseModel):
    x: int = 0
    y: int = 0
    coins: int = 0
    lives: int = 0
    world: int = 0
    stage: int = 0
    done: bool = False


class SuperMarioFramePayload(BaseModel):
    mime_type: str = "image/jpeg"
    jpg_base64: str
    width: int
    height: int


class SuperMarioStepPayload(BaseModel):
    step_index: int
    control: str
    captured_at: int
    reward_delta: float = 0.0
    progress: SuperMarioProgress = Field(default_factory=SuperMarioProgress)
    frame: SuperMarioFramePayload


class SuperMarioAttemptState(BaseModel):
    uid: int
    hotkey: str
    endpoint: str
    run_id: str | None = None
    is_finished: bool = False
    finish_reason: str | None = None
    score: float = 0.0
    steps_count: int = 0
    last_frame_id: str | None = None
    last_video_id: str | None = None
    last_control: str | None = None
    progress: SuperMarioProgress = Field(default_factory=SuperMarioProgress)
    level_complete: bool = False
    progress_from_start: float = 0.0
    env_score: float = 0.0
    elapsed_s: float = 0.0
    step_cursor: int = 0
    had_artifacts: bool = False


class SuperMarioRoomState(BaseModel):
    room_id: str
    validator_key: str
    competition: str = "supermario"
    status: str = "running"
    level: str = "1-1"
    seed: str | None = None
    step_limit: int = 3000
    step_count: int = 0
    participants: list[SuperMarioAttemptState] = Field(default_factory=list)
    started_at: int
    ended_at: int | None = None
