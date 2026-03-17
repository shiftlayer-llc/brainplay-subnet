import time

from game.plugins.twentyq.backend_mapper import (
    make_create_payload,
    make_score_payload,
    make_update_payload,
)
from game.plugins.twentyq.models import TwentyQAttemptState, TwentyQRoomState
from game.plugins.twentyq.protocol import TwentyQTurn


def _build_room():
    participant = TwentyQAttemptState(
        uid=1,
        hotkey="hotkey-1",
        endpoint="serv-u-1",
        question_count=1,
        qa_history=[TwentyQTurn(turn=1, question="Is it red?", answer="unknown")],
    )
    return TwentyQRoomState(
        room_id="room-1",
        validator_key="validator-hotkey",
        word="apple",
        started_at=int(time.time()),
        participants=[participant],
    )


def test_mapper_create_payload():
    room = _build_room()
    payload = make_create_payload(room)
    assert payload["validatorKey"] == "validator-hotkey"
    assert payload["competition"] == "twentyq"
    assert payload["participants"] == ["hotkey-1"]
    assert payload["word"] == "apple"


def test_mapper_update_and_score_payload():
    room = _build_room()
    room.participants[0].score = 0.9
    room.participants[0].is_finished = True
    room.participants[0].finish_reason = "solved"

    update_payload = make_update_payload(room)
    assert update_payload["participants"][0]["hotkey"] == "hotkey-1"
    assert update_payload["participants"][0]["score"] == 0.9
    assert update_payload["participants"][0]["is_finished"] is True

    score_payload = make_score_payload(room)
    assert score_payload["scores"] == [{"hotkey": "hotkey-1", "score": 0.9}]
    assert score_payload["participants"] == [{"hotkey": "hotkey-1", "score": 0.9}]
