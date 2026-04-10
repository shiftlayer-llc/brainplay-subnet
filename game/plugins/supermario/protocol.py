"""SuperMario runtime protocol models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SuperMarioRunRequest(BaseModel):
    num_runs: int = 1
    max_steps_per_episode: int = 3000
    parallel_runs: int = 1
    token_limit: int = 2048
    request_timeout_s: int = 300
    request_max_retries: int = 3


class SuperMarioRunCurrent(BaseModel):
    episode: int = 0
    step: int = 0
    score: float = 0.0
    progress_from_start: float = 0.0
    elapsed_s: float = 0.0


class SuperMarioRunEpisodeResult(BaseModel):
    run_id: str | int | None = None
    score: float = 0.0
    progress_from_start: float = 0.0
    elapsed_s: float = 0.0
    finish_reason: str | None = None
    steps: int = 0


class SuperMarioRunResult(BaseModel):
    summary: dict[str, Any] = Field(default_factory=dict)
    episodes: list[SuperMarioRunEpisodeResult] = Field(default_factory=list)
    video_url: str | None = None
    video_path: str | None = None


class SuperMarioRunStatus(BaseModel):
    run_id: str
    state: str
    submitted_at: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    current: SuperMarioRunCurrent | None = None
    result: SuperMarioRunResult | None = None
    status_url: str | None = None
    video_url: str | None = None
    pid: int | None = None
    returncode: int | None = None
