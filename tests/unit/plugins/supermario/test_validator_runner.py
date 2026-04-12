from __future__ import annotations

import asyncio
from types import SimpleNamespace

from game.plugins.supermario.models import (
    SuperMarioAttemptState,
    SuperMarioRoomState,
)
from game.plugins.supermario.protocol import (
    SuperMarioRunEpisodeResult,
    SuperMarioRunResult,
    SuperMarioRunStatus,
)
from game.plugins.supermario.validator_runner import SuperMarioValidatorRunner


class DummyBackend:
    def __init__(self) -> None:
        self.calls = []

    async def upload_room_video(self, game_code: str, room_id: str, payload: dict):
        self.calls.append((game_code, room_id, payload))
        return {"data": {"id": "video_123"}}


def make_runner() -> SuperMarioValidatorRunner:
    validator = SimpleNamespace(
        backend_base="https://backend.example",
        build_signed_headers=lambda: {},
        wallet=SimpleNamespace(hotkey=SimpleNamespace()),
    )
    runner = SuperMarioValidatorRunner(validator)
    runner.backend = DummyBackend()
    return runner


def test_upload_video_artifact_persists_video_id(monkeypatch):
    runner = make_runner()
    room = SuperMarioRoomState(
        room_id="room_1",
        validator_key="validator_hotkey",
        started_at=1,
    )
    participant = SuperMarioAttemptState(
        uid=58,
        hotkey="miner_hotkey",
        endpoint="https://miner.example",
        run_id="run_1",
    )
    status = SuperMarioRunStatus(
        run_id="run_1",
        state="succeeded",
        result=SuperMarioRunResult(
            video_url="/runs/run_1/video",
            episodes=[SuperMarioRunEpisodeResult(run_id="run_1")],
        ),
    )

    async def fake_fetch_video_bytes(*, participant, video_url):
        assert participant.run_id == "run_1"
        assert video_url == "/runs/run_1/video"
        return b"fake-mp4", "video/mp4"

    monkeypatch.setattr(runner, "_fetch_video_bytes", fake_fetch_video_bytes)

    asyncio.run(runner._upload_video_artifact(room, participant, status))

    assert participant.last_video_id == "video_123"
    assert len(runner.backend.calls) == 1
    game_code, room_id, payload = runner.backend.calls[0]
    assert game_code == "supermario"
    assert room_id == "room_1"
    assert payload["participant_hotkey"] == "miner_hotkey"
    assert payload["run_id"] == "run_1"
    assert payload["mime_type"] == "video/mp4"
    assert payload["mp4_base64"]


def test_upload_video_artifact_skips_when_video_missing(monkeypatch):
    runner = make_runner()
    room = SuperMarioRoomState(
        room_id="room_1",
        validator_key="validator_hotkey",
        started_at=1,
    )
    participant = SuperMarioAttemptState(
        uid=58,
        hotkey="miner_hotkey",
        endpoint="https://miner.example",
        run_id="run_1",
    )
    status = SuperMarioRunStatus(run_id="run_1", state="succeeded")

    called = False

    async def fake_fetch_video_bytes(*, participant, video_url):
        nonlocal called
        called = True
        return b"", "video/mp4"

    monkeypatch.setattr(runner, "_fetch_video_bytes", fake_fetch_video_bytes)

    asyncio.run(runner._upload_video_artifact(room, participant, status))

    assert participant.last_video_id is None
    assert called is False
    assert runner.backend.calls == []
