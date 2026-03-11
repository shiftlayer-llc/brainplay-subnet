from game.plugins.twentyq.protocol import (
    TwentyQMinerOutput,
    TwentyQPayload,
    TwentyQTurn,
)


def test_twentyq_payload_defaults():
    payload = TwentyQPayload(room_id="r1", attempt_id="a1", turn_index=1)
    assert payload.max_questions == 20
    assert payload.max_bonus_questions == 10
    assert payload.history == []
    assert payload.last_answer is None


def test_twentyq_miner_output_action_detection():
    assert TwentyQMinerOutput().has_action() is False
    assert TwentyQMinerOutput(question="Is it alive?").has_action() is True
    assert TwentyQMinerOutput(guess="apple").has_action() is True


def test_twentyq_turn_shape():
    turn = TwentyQTurn(turn=1, question="Is it a fruit?", answer="yes")
    assert turn.turn == 1
    assert turn.answer == "yes"
