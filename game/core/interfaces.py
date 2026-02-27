"""Core plugin interfaces for the multi-game validator architecture.

These protocols intentionally use broad types (`Any`, `Mapping[str, Any]`) in
Phase 1 so they can be adopted incrementally without forcing large refactors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence


@dataclass
class AttemptResult:
    """Generic result for one miner attempt inside a game session."""

    miner_hotkey: str
    status: str
    score: float
    started_at: float
    ended_at: float
    attempt_id: Optional[str] = None
    turns_used: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionResult:
    """Generic result for a validator-created game session."""

    session_id: str
    game_code: str
    competition_code: str
    status: str
    started_at: float
    ended_at: float
    attempts: Sequence[AttemptResult] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)


class GameValidatorRunner(Protocol):
    """Game-specific validator orchestration entry point."""

    async def run_round(self) -> SessionResult:
        """Run one validator game round/session and return generic results."""
        ...


class GameMinerHandler(Protocol):
    """Game-specific handler for miner-side requests."""

    async def handle(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Handle a game request payload and return a response payload."""
        ...


class ScoringPolicy(Protocol):
    """Game-specific scoring policy interface."""

    def score_attempt(
        self,
        *,
        transcript: Mapping[str, Any],
        limits: Optional[Mapping[str, Any]] = None,
    ) -> float:
        """Return a normalized score, typically in the [0, 1] range."""
        ...


class GamePlugin(Protocol):
    """Plugin contract implemented by each supported game."""

    game_code: str
    competition_code: str
    mechid: int
    display_name: str
    protocol_version: str

    def validate_config(self, config: Any) -> None:
        """Raise on invalid config for this plugin."""
        ...

    def create_validator_runner(self, ctx: Any) -> GameValidatorRunner:
        """Create the validator runner for this plugin."""
        ...

    def create_miner_handler(self, ctx: Any) -> Optional[GameMinerHandler]:
        """Create the miner handler for this plugin, if applicable."""
        ...
