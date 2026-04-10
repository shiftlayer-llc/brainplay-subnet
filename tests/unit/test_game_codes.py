from game.core.codes import get_game_code_info, normalize_game_code


def test_mario_alias_normalizes_to_supermario():
    assert normalize_game_code("mario") == "supermario"
    info = get_game_code_info("mario")
    assert info.game_code == "supermario"
    assert info.weight_group == "vision"
    assert info.publish_mechid == 1
