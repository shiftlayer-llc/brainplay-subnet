"""SuperMario game plugin metadata and factories."""

from __future__ import annotations

from game.core.codes import get_game_code_info
from game.plugins.supermario.validator_runner import SuperMarioValidatorRunner


class SuperMarioPlugin:
    def __init__(self) -> None:
        info = get_game_code_info("supermario")
        self.game_code = info.game_code
        self.competition_code = info.competition_code
        self.mechid = info.mechid
        self.weight_group = info.weight_group
        self.publish_mechid = info.publish_mechid
        self.display_name = info.display_name
        self.protocol_version = "brainplay.supermario@1"

    def validate_config(self, config) -> None:
        game_code = getattr(getattr(config, "game", None), "code", None)
        competition_code = getattr(config, "competition", None)
        allowed = {"supermario", "mario", "main"}
        if game_code and str(game_code).lower() not in {"supermario", "mario"}:
            raise ValueError(
                f"SuperMarioPlugin received incompatible game.code={game_code!r}"
            )
        if competition_code and str(competition_code).lower() not in allowed:
            raise ValueError(
                "SuperMarioPlugin received incompatible "
                f"competition={competition_code!r}"
            )

    def create_validator_runner(self, ctx):
        return SuperMarioValidatorRunner(ctx)

    def create_miner_handler(self, ctx):
        return None


_SUPERMARIO_PLUGIN = SuperMarioPlugin()


def get_supermario_plugin() -> SuperMarioPlugin:
    return _SUPERMARIO_PLUGIN
