"""TwentyQ plugin placeholder."""

from __future__ import annotations

from game.core.codes import GameCodeInfo


class TwentyQPlugin:
    game_code = "20q"
    competition_code = "20q"
    mechid = -1  # placeholder until subnet mechid is assigned
    display_name = "20 Questions"
    protocol_version = "brainplay.game@1"

    def validate_config(self, config) -> None:
        return

    def create_validator_runner(self, ctx):
        raise NotImplementedError("TwentyQ plugin not implemented yet.")

    def create_miner_handler(self, ctx):
        raise NotImplementedError("TwentyQ plugin not implemented yet.")
