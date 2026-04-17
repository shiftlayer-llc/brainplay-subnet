"""Canonical game/competition codes and mechid metadata.

Phase 1 scope:
- Codenames and 20Q are runtime-supported.
- Future games can be added here once their mechids are finalized.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class GameCodeInfo:
    game_code: str
    competition_code: str
    mechid: int
    display_name: str
    weight_group: str = "llm"
    publish_mechid: int = 0
    default_interval: str = "1 minutes"


# Games currently supported by runtime code.
_SUPPORTED_GAMES: Dict[str, GameCodeInfo] = {
    "codenames": GameCodeInfo(
        game_code="codenames",
        competition_code="codenames",
        mechid=0,
        display_name="Codenames",
        weight_group="llm",
        publish_mechid=0,
    ),
    "twentyq": GameCodeInfo(
        game_code="twentyq",
        competition_code="twentyq",
        mechid=0,
        display_name="20 Questions",
        weight_group="llm",
        publish_mechid=0,
    ),
    "supermario": GameCodeInfo(
        game_code="supermario",
        competition_code="supermario",
        mechid=1,
        display_name="SuperMario",
        weight_group="vision",
        publish_mechid=1,
    ),
}

_ALIASES: Dict[str, str] = {
    "mario": "supermario",
}


# Reserved/planned codes (no mechid guarantees yet).
_RESERVED_GAME_CODES: Tuple[str, ...] = (
    "2048",
    "pacman",
    "chess",
    "go",
)


def normalize_game_code(code: str) -> str:
    """Normalize a user-provided game/competition code."""
    normalized = (code or "").strip().lower()
    return _ALIASES.get(normalized, normalized)


def get_game_code_info(code: str) -> GameCodeInfo:
    """Return canonical metadata for a supported game code."""
    normalized = normalize_game_code(code)
    try:
        return _SUPPORTED_GAMES[normalized]
    except KeyError as exc:
        raise KeyError(f"Unsupported game code: {code!r}") from exc


def list_supported_game_codes() -> Tuple[str, ...]:
    """List runtime-supported game codes in stable order."""
    return tuple(_SUPPORTED_GAMES.keys())


def list_supported_game_infos() -> Tuple[GameCodeInfo, ...]:
    return tuple(_SUPPORTED_GAMES.values())


def list_supported_game_codes_for_weight_group(weight_group: str) -> Tuple[str, ...]:
    normalized = normalize_game_code(weight_group)
    return tuple(
        info.game_code
        for info in _SUPPORTED_GAMES.values()
        if normalize_game_code(info.weight_group) == normalized
    )


def list_reserved_game_codes() -> Tuple[str, ...]:
    """List planned game codes reserved for future plugins."""
    return _RESERVED_GAME_CODES


def is_supported_game_code(code: str) -> bool:
    return normalize_game_code(code) in _SUPPORTED_GAMES


def is_reserved_game_code(code: str) -> bool:
    normalized = normalize_game_code(code)
    return normalized in _RESERVED_GAME_CODES or normalized in _SUPPORTED_GAMES


def register_supported_game(info: GameCodeInfo) -> None:
    """Register a supported game in the canonical code table.

    Intended for refactor staging and tests. Runtime wiring should still use the
    plugin registry as the source of enabled implementations.
    """
    key = normalize_game_code(info.game_code)
    if not key:
        raise ValueError("game_code cannot be empty")
    if key != normalize_game_code(info.competition_code):
        # Locked decision for Phase 1-6.
        raise ValueError(
            "competition_code must match game_code during Phase 1-6 refactor"
        )
    existing = _SUPPORTED_GAMES.get(key)
    if existing and existing != info:
        raise ValueError(
            f"Conflicting game metadata for {key!r}: existing={existing}, new={info}"
        )
    _SUPPORTED_GAMES[key] = info
