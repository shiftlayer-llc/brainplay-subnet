from game.base.validator import BaseValidatorNeuron


def test_base_validator_argv_strips_competition_flag():
    argv = [
        "neurons/validator.py",
        "--wallet.name",
        "owner",
        "--competition",
        "main",
        "--logging.info",
    ]

    assert BaseValidatorNeuron._base_validator_argv(argv) == [
        "neurons/validator.py",
        "--wallet.name",
        "owner",
        "--logging.info",
    ]


def test_base_validator_argv_strips_competition_equals_flag():
    argv = [
        "neurons/validator.py",
        "--wallet.name",
        "owner",
        "--competition=twentyq",
        "--logging.info",
    ]

    assert BaseValidatorNeuron._base_validator_argv(argv) == [
        "neurons/validator.py",
        "--wallet.name",
        "owner",
        "--logging.info",
    ]


def test_main_mode_competition_codes_include_all_competitions():
    assert BaseValidatorNeuron._competition_codes_for_main() == [
        "codenames",
        "twentyq",
    ]
