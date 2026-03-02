"""Codenames game plugin metadata and factories."""

from __future__ import annotations

from game.core.codes import get_game_code_info
from game.plugins.codenames.validator_runner import CodenamesValidatorRunner


class CodenamesPlugin:
    def __init__(self) -> None:
        info = get_game_code_info("codenames")
        self.game_code = info.game_code
        self.competition_code = info.competition_code
        self.mechid = info.mechid
        self.display_name = info.display_name
        self.protocol_version = "legacy-codenames@1"

    def validate_config(self, config) -> None:
        game_code = getattr(getattr(config, "game", None), "code", None)
        competition_code = getattr(config, "competition", None)
        if game_code and str(game_code).lower() not in {"codenames"}:
            raise ValueError(
                f"CodenamesPlugin received incompatible game.code={game_code!r}"
            )
        if competition_code and str(competition_code).lower() not in {
            "codenames",
            "main",
        }:
            raise ValueError(
                "CodenamesPlugin received incompatible "
                f"competition={competition_code!r}"
            )

    def create_validator_runner(self, ctx):
        # Phase 1 passes the validator neuron directly as the context.
        return CodenamesValidatorRunner(ctx)

    def create_miner_handler(self, ctx):
        # Miner-side plugin routing is not implemented yet.
        return None


_CODENAMES_PLUGIN = CodenamesPlugin()


def get_codenames_plugin() -> CodenamesPlugin:
    return _CODENAMES_PLUGIN
