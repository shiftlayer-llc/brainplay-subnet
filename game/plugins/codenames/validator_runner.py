"""Codenames validator runner wrapper.

Phase 1 implementation delegates to the legacy codenames forward loop so runtime
behavior remains unchanged while the plugin architecture is introduced.
"""

from __future__ import annotations

import time
from uuid import uuid4

from game.validator import forward as legacy_codenames_forward
from game.core.interfaces import SessionResult


class CodenamesValidatorRunner:
    def __init__(self, validator) -> None:
        self.validator = validator

    async def run_round(self) -> SessionResult:
        started_at = time.time()
        await legacy_codenames_forward(self.validator)
        ended_at = time.time()

        return SessionResult(
            session_id=f"legacy-codenames-{uuid4().hex}",
            game_code="codenames",
            competition_code="codenames",
            status="completed",
            started_at=started_at,
            ended_at=ended_at,
            attempts=(),
            metadata={"legacy_forward": True},
        )
