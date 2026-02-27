"""Core multi-game scaffolding (registry, interfaces, codes, telemetry).

These modules are additive scaffolding for the multi-game refactor and are
intentionally not wired into the runtime yet.
"""

from .codes import GameCodeInfo, get_game_code_info, list_supported_game_codes
from .registry import GameRegistry, get_registry

__all__ = [
    "GameCodeInfo",
    "GameRegistry",
    "get_game_code_info",
    "get_registry",
    "list_supported_game_codes",
]
