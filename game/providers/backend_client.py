"""Signed backend API client for game room/session updates."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import aiohttp


class BackendClient:
    """Thin signed HTTP client for backend game room endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        signer: Optional[Callable[[], Dict[str, str]]] = None,
        timeout_sec: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.signer = signer
        self.timeout_sec = int(timeout_sec)

    def _headers(self) -> Dict[str, str]:
        return dict(self.signer() if self.signer else {})

    async def create_room(self, game_code: str, payload: Dict[str, Any]) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/v1/games/{game_code}/create",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_sec,
            ) as resp:
                return await resp.json(content_type=None)

    async def update_room(
        self, game_code: str, room_id: str, payload: Dict[str, Any]
    ) -> Any:
        async with aiohttp.ClientSession() as session:
            async with session.patch(
                f"{self.base_url}/api/v1/games/{game_code}/{room_id}",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_sec,
            ) as resp:
                return await resp.json(content_type=None)

    async def delete_room(self, game_code: str, room_id: str) -> int:
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{self.base_url}/api/v1/games/{game_code}/{room_id}",
                headers=self._headers(),
                timeout=self.timeout_sec,
            ) as resp:
                return int(resp.status)
