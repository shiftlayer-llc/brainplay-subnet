from typing import List, Dict, Tuple
from game.plugins.codenames.game_types import Competition
import bittensor as bt
from game.core.endpoint_resolver import (
    parse_commitment_payload,
    resolve_game_endpoint_from_commitment,
)


def _resolve_legacy_codenames_endpoint(payload: dict) -> str | None:
    """Handle legacy split-role commitment keys used by some miners.

    Examples:
    - {"codenames_clue": "...", "codenames_guess": "..."}
    - {"codenames": {"codenames_clue": "...", "codenames_guess": "..."}}
    """
    if not isinstance(payload, dict):
        return None

    # Direct split-role keys at top level.
    for key in ("codenames", "codenames_clue", "codenames_guess"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for subkey in ("url", "codenames_clue", "codenames_guess"):
                subval = value.get(subkey)
                if isinstance(subval, str) and subval.strip():
                    return subval.strip()
    return None


def _read_commitments_bulk(self) -> Tuple[bool, Dict[str, dict]]:
    """Read commitments via a single chain call keyed by hotkey.

    Returns:
        tuple[bool, dict[str, dict]]:
            - bool: whether the bulk call succeeded
            - dict: hotkey -> parsed commitment payload
    """
    try:
        raw_map = self.subtensor.get_all_commitments(self.config.netuid)
    except Exception as e:
        bt.logging.debug(f"Bulk commitment read failed; fallback to per-uid reads: {e}")
        return False, {}

    if not isinstance(raw_map, dict):
        return True, {}

    parsed: Dict[str, dict] = {}
    for hotkey, raw_payload in raw_map.items():
        payload = parse_commitment_payload(raw_payload)
        if payload:
            parsed[str(hotkey)] = payload
    return True, parsed


def read_endpoints(self, competition: Competition, uids: List[int]) -> Dict[int, dict]:
    """Reads the endpoints for the given list of UIDs.

    Args:
        uids (List[int]): List of UIDs to read endpoints for.
    Returns:
        Dict[int, dict]: A dictionary mapping UIDs to their endpoints.
    """
    targon_endpoints = {}
    bulk_ok, commitments_by_hotkey = _read_commitments_bulk(self)

    for uid in uids:
        try:
            hotkey = self.metagraph.hotkeys[int(uid)]
        except Exception as e:
            bt.logging.debug(f"Skipping UID {uid}; hotkey lookup failed: {e}")
            continue

        payload = {}
        if bulk_ok:
            payload = commitments_by_hotkey.get(str(hotkey), {})
        else:
            try:
                commit_data = self.subtensor.get_commitment(self.config.netuid, uid)
                payload = parse_commitment_payload(commit_data)
            except Exception as e:
                bt.logging.debug(f"Skipping UID {uid} commitment parse error: {e}")
                continue

        if not payload:
            continue
        bt.logging.debug(f"UID {uid} commitment data: {payload}")

        endpoint = resolve_game_endpoint_from_commitment(payload, competition.value)
        if endpoint is None and competition.value == "codenames":
            endpoint = _resolve_legacy_codenames_endpoint(payload)
        if not endpoint:
            continue
        targon_endpoints[uid] = endpoint
    return targon_endpoints
