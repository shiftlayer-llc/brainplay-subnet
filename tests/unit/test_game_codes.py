from game import __image_hash__, __mario_image_hash__, get_image_hash_for_competition
from game.core.codes import get_game_code_info, normalize_game_code


def test_mario_alias_normalizes_to_supermario():
    assert normalize_game_code("mario") == "supermario"
    info = get_game_code_info("mario")
    assert info.game_code == "supermario"
    assert info.weight_group == "vision"
    assert info.publish_mechid == 1


def test_supermario_uses_mario_image_hash():
    assert get_image_hash_for_competition("supermario") == __mario_image_hash__
    assert get_image_hash_for_competition("mario") == __mario_image_hash__
    assert get_image_hash_for_competition("codenames") == __image_hash__
