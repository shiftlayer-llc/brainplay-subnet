from pathlib import Path
from types import SimpleNamespace

from game.plugins.twentyq.protocol import TwentyQTurn
from game.plugins.twentyq.validator_runner import TwentyQValidatorRunner


def test_format_history_text_empty():
    assert TwentyQValidatorRunner._format_history_text([]) == "No prior turns."


def test_format_history_text_includes_guesses_and_correctness():
    history = [
        TwentyQTurn(turn=1, question="Is it furniture?", answer="yes"),
        TwentyQTurn(
            turn=2,
            question="<guess>",
            answer="unknown",
            guess="bed",
            is_correct_guess=False,
        ),
    ]

    text = TwentyQValidatorRunner._format_history_text(history)
    assert "Q1: Is it furniture?" in text
    assert "A1: yes" in text
    assert "G2: bed" in text
    assert "G2_correct: no" in text
    assert "<guess>" not in text


def test_normalize_secret_word_rules():
    assert TwentyQValidatorRunner._normalize_secret_word("mattress") == "mattress"
    assert TwentyQValidatorRunner._normalize_secret_word("thing") is None
    assert TwentyQValidatorRunner._normalize_secret_word("roll") is None
    assert TwentyQValidatorRunner._normalize_secret_word("red apple") is None
    assert TwentyQValidatorRunner._normalize_secret_word("123") is None


def test_normalize_dataset_word_rules():
    assert TwentyQValidatorRunner._normalize_dataset_word("giraffe_1") == "giraffe"
    assert (
        TwentyQValidatorRunner._normalize_dataset_word("fire_truck_22") == "fire-truck"
    )
    assert TwentyQValidatorRunner._normalize_dataset_word("watch_7") is None


def test_load_secret_word_pool_from_dataset(tmp_path, monkeypatch):
    dataset_path = tmp_path / "sample.csv"
    dataset_path.write_text(
        "word,category\n" "giraffe_1,animal\n" "apple_2,food\n" "watch_3,object\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "game.plugins.twentyq.validator_runner.DATASET_PATH", Path(dataset_path)
    )

    runner = TwentyQValidatorRunner.__new__(TwentyQValidatorRunner)
    runner.validator = SimpleNamespace()

    words = runner._load_secret_word_pool()

    assert words == ["giraffe", "apple"]


def test_active_game_error_detection():
    assert TwentyQValidatorRunner._is_active_game_exists_error(
        {"message": "Active game already exists for validator"}
    )
    assert TwentyQValidatorRunner._is_active_game_exists_error(
        {"statusCode": 409, "message": "active room exists"}
    )
    assert not TwentyQValidatorRunner._is_active_game_exists_error(
        {"statusCode": 400, "message": "validation error"}
    )
