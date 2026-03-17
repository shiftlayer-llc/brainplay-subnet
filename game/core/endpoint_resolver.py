"""On-chain commitment parsing and endpoint resolution helpers.

Supports the current commitment format (v1 string map) and the planned v2
capability schema. Validators can read both during migration.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import bittensor as bt


def parse_commitment_payload(raw: Any) -> Dict[str, Any]:
    """Parse a commitment payload from chain into a dict.

    Accepts a JSON string or a dict-like object. Returns `{}` on invalid payload.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return {}
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def commitment_version(payload: Dict[str, Any]) -> int:
    value = payload.get("version")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 1


def resolve_game_endpoint_from_commitment(
    payload: Dict[str, Any], game_code: str
) -> Optional[str]:
    """Resolve a game endpoint from commitment payload (v1 or v2)."""
    game_code = (game_code or "").strip().lower()
    if not payload or not game_code:
        return None

    version = commitment_version(payload)
    if version >= 2:
        endpoints = payload.get("endpoints") or {}
        games = endpoints.get("games") if isinstance(endpoints, dict) else None
        if isinstance(games, dict):
            game_entry = games.get(game_code)
            if isinstance(game_entry, str):
                return game_entry
            if isinstance(game_entry, dict):
                url = game_entry.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()
        default_endpoint = (
            endpoints.get("default") if isinstance(endpoints, dict) else None
        )
        if isinstance(default_endpoint, str) and default_endpoint.strip():
            return default_endpoint.strip()

    # Legacy v1: {"codenames": "<endpoint>"}
    value = payload.get(game_code)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def read_endpoints_for_competition(
    validator,
    *,
    competition_code: str,
    uids: list[int],
) -> Dict[int, str]:
    """Read and resolve miner endpoints from chain commitments for a competition."""
    resolved: Dict[int, str] = {}
    raw_map: Dict[str, Any] = {}
    bulk_ok = False
    try:
        maybe_map = validator.subtensor.get_all_commitments(validator.config.netuid)
        if isinstance(maybe_map, dict):
            raw_map = maybe_map
        bulk_ok = True
    except Exception:
        bulk_ok = False

    for uid in uids:
        payload: Dict[str, Any] = {}
        if bulk_ok:
            try:
                hotkey = validator.metagraph.hotkeys[int(uid)]
            except Exception:
                continue
            payload = parse_commitment_payload(raw_map.get(str(hotkey)))
        else:
            try:
                raw = validator.subtensor.get_commitment(validator.config.netuid, uid)
            except Exception:
                continue
            payload = parse_commitment_payload(raw)
        endpoint = resolve_game_endpoint_from_commitment(payload, competition_code)
        if endpoint:
            resolved[int(uid)] = endpoint
            bt.logging.debug(
                f"Resolved endpoint for uid={uid} competition={competition_code}: {endpoint}"
            )
    return resolved
