"""Game plugin registry for the multi-game architecture."""

from __future__ import annotations

import threading
from typing import Dict, Iterable, List, Optional, TypeVar

from .interfaces import GamePlugin

GamePluginT = TypeVar("GamePluginT", bound=GamePlugin)


def _norm(code: str) -> str:
    return (code or "").strip().lower()


class GameRegistry:
    """In-memory registry of game plugins.

    Phase 1 usage:
    - register codenames plugin wrapper
    - resolve plugin from validator startup
    - later drive `main` subprocess spawning and CLI validation
    """

    def __init__(self) -> None:
        self._by_game_code: Dict[str, GamePlugin] = {}
        self._by_competition_code: Dict[str, GamePlugin] = {}
        self._by_mechid: Dict[int, GamePlugin] = {}
        self._lock = threading.RLock()

    def clear(self) -> None:
        """Clear registry contents (primarily for tests)."""
        with self._lock:
            self._by_game_code.clear()
            self._by_competition_code.clear()
            self._by_mechid.clear()

    def register(self, plugin: GamePluginT) -> GamePluginT:
        """Register a plugin and return it (decorator-friendly)."""
        game_code = _norm(getattr(plugin, "game_code", ""))
        competition_code = _norm(getattr(plugin, "competition_code", ""))
        mechid = getattr(plugin, "mechid", None)

        if not game_code:
            raise ValueError("Plugin game_code is required")
        if not competition_code:
            raise ValueError("Plugin competition_code is required")
        if not isinstance(mechid, int):
            raise ValueError("Plugin mechid must be an int")

        with self._lock:
            self._check_conflict(
                self._by_game_code.get(game_code), plugin, f"game_code={game_code}"
            )
            self._check_conflict(
                self._by_competition_code.get(competition_code),
                plugin,
                f"competition_code={competition_code}",
            )
            self._check_conflict(
                self._by_mechid.get(mechid), plugin, f"mechid={mechid}"
            )

            self._by_game_code[game_code] = plugin
            self._by_competition_code[competition_code] = plugin
            self._by_mechid[mechid] = plugin

        return plugin

    def register_many(self, plugins: Iterable[GamePlugin]) -> None:
        for plugin in plugins:
            self.register(plugin)

    def get_by_game_code(self, game_code: str) -> GamePlugin:
        key = _norm(game_code)
        with self._lock:
            try:
                return self._by_game_code[key]
            except KeyError as exc:
                raise KeyError(f"Unknown game_code: {game_code!r}") from exc

    def get_by_competition_code(self, competition_code: str) -> GamePlugin:
        key = _norm(competition_code)
        with self._lock:
            try:
                return self._by_competition_code[key]
            except KeyError as exc:
                raise KeyError(
                    f"Unknown competition_code: {competition_code!r}"
                ) from exc

    def get_by_mechid(self, mechid: int) -> GamePlugin:
        with self._lock:
            try:
                return self._by_mechid[int(mechid)]
            except KeyError as exc:
                raise KeyError(f"Unknown mechid: {mechid!r}") from exc

    def maybe_get_by_game_code(self, game_code: str) -> Optional[GamePlugin]:
        key = _norm(game_code)
        with self._lock:
            return self._by_game_code.get(key)

    def list_plugins(self) -> List[GamePlugin]:
        with self._lock:
            return list(self._by_game_code.values())

    def list_game_codes(self) -> List[str]:
        with self._lock:
            return sorted(self._by_game_code.keys())

    @staticmethod
    def _check_conflict(existing: Optional[GamePlugin], new: GamePlugin, label: str):
        if existing is None:
            return
        if existing is new:
            return
        raise ValueError(f"Registry conflict for {label}: {existing!r} vs {new!r}")


_GLOBAL_REGISTRY = GameRegistry()


def get_registry() -> GameRegistry:
    return _GLOBAL_REGISTRY


def register_plugin(plugin: GamePluginT) -> GamePluginT:
    return _GLOBAL_REGISTRY.register(plugin)
