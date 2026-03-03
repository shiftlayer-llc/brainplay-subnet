"""TwentyQ game plugin metadata and factories."""

from __future__ import annotations

from game.core.codes import get_game_code_info
from game.plugins.twentyq.validator_runner import TwentyQValidatorRunner


class TwentyQPlugin:
    def __init__(self) -> None:
        info = get_game_code_info("20q")
        self.game_code = info.game_code
        self.competition_code = info.competition_code
        self.mechid = info.mechid
        self.display_name = info.display_name
        self.protocol_version = "brainplay.20q@1"

    def validate_config(self, config) -> None:
        game_code = getattr(getattr(config, "game", None), "code", None)
        competition_code = getattr(config, "competition", None)
        if game_code and str(game_code).lower() not in {"20q"}:
            raise ValueError(
                f"TwentyQPlugin received incompatible game.code={game_code!r}"
            )
        if competition_code and str(competition_code).lower() not in {"20q", "main"}:
            raise ValueError(
                "TwentyQPlugin received incompatible "
                f"competition={competition_code!r}"
            )

    def create_validator_runner(self, ctx):
        return TwentyQValidatorRunner(ctx)

    def create_miner_handler(self, ctx):
        # Miner-side plugin routing is not implemented yet.
        return None


_TWENTYQ_PLUGIN = TwentyQPlugin()


def get_twentyq_plugin() -> TwentyQPlugin:
    return _TWENTYQ_PLUGIN
