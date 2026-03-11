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
