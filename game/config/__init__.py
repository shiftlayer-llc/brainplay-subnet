"""Config split scaffolding for the multi-game refactor."""

from .legacy import add_args, add_miner_args, add_validator_args, check_config, config

__all__ = [
    "add_args",
    "add_miner_args",
    "add_validator_args",
    "check_config",
    "config",
]
