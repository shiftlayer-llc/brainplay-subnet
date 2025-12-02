import random
import time
import asyncio
import json
import aiohttp
import bittensor as bt
from game.api.get_query_axons import ping_uids
import numpy as np
from typing import List, Tuple

from game.utils.game import Competition


def make_available_pool(self, exclude: List[int] = None) -> List[int]:
    """Build the candidate uid pool, removing excluded miners"""
    available_pool = [int(uid) for uid in self.metagraph.uids]
    # Step 1: Exclude uids in the exclude list
    available_pool = [uid for uid in available_pool if uid not in (exclude or [])]
    if not available_pool:
        return []
    # Step 2: Choose uids which have minimum global game count in current epoch
    minimum_global_count = min(
        [
            self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0)
            for uid in available_pool
        ]
    )
    available_pool = [
        uid
        for uid in available_pool
        if self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0)
        == minimum_global_count
    ]
    bt.logging.debug(
        f"Available pool after exclusions: {available_pool}, counts: {[self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0) for uid in available_pool]}"
    )
    if not available_pool:
        return []
    # Step 3: Choose uids which have minimum local game count in current window
    minimum_local_count = min(
        [
            self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
            for uid in available_pool
        ]
    )
    available_pool = [
        uid
        for uid in available_pool
        if self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
        == minimum_local_count
    ]
    bt.logging.debug(
        f"Available pool after local count filter: {available_pool}, counts: {[self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0) for uid in available_pool]}"
    )
    # Step 4: Choose uids which have minimum global game count in current window
    minimum_global_count = min(
        [
            self._global_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
            for uid in available_pool
        ]
    )
    available_pool = [
        uid
        for uid in available_pool
        if self._global_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
        == minimum_global_count
    ]
    bt.logging.debug(
        f"Available pool after global count filter: {available_pool}, counts: {[self._global_counts_in_window.get(self.metagraph.hotkeys[uid], 0) for uid in available_pool]}"
    )
    # Step 5: Shuffle the available pool
    random.shuffle(available_pool)

    return available_pool


def make_available_pool_for_second_player(self, exclude: List[int] = None) -> List[int]:
    """Build the candidate uid pool, removing excluded miners"""
    available_pool = [int(uid) for uid in self.metagraph.uids]
    # Step 1: Exclude uids in the exclude list
    available_pool = [uid for uid in available_pool if uid not in (exclude or [])]
    if not available_pool:
        return []
    # Step 2: Choose uids which have minimum global game count in current epoch
    minimum_global_count = min(
        [
            self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0)
            for uid in available_pool
        ]
    )
    available_pool = [
        uid
        for uid in available_pool
        if self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0)
        == minimum_global_count
    ]
    bt.logging.debug(
        f"Available pool after exclusions: {available_pool}, counts: {[self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0) for uid in available_pool]}"
    )
    if not available_pool:
        return []
    # Step 3: Choose uids which have minimum local game count in current window
    minimum_local_count = min(
        [
            self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
            for uid in available_pool
        ]
    )
    available_pool = [
        uid
        for uid in available_pool
        if self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
        == minimum_local_count
    ]
    bt.logging.debug(
        f"Available pool after local count filter: {available_pool}, counts: {[self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0) for uid in available_pool]}"
    )

    # Step 4: Filter out uids which played too many games in current window
    median_count = np.median(
        [
            self._global_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
            for uid in available_pool
        ]
    )
    available_pool = [
        uid
        for uid in available_pool
        if self._global_counts_in_window.get(self.metagraph.hotkeys[uid], 0)
        < median_count + 3
    ]
    random.shuffle(available_pool)

    return available_pool


async def fetch_active_miners(self, competition: Competition):
    """
    Fetch active miners from API with improved error handling.
    
    Args:
        competition: Competition type
        
    Returns:
        List of active miner hotkeys, empty list on error
    """
    session = aiohttp.ClientSession()
    try:
        headers = self.build_signed_headers()
        params = {"competition": competition.value}
        async with session.get(
            self.active_miners_endpoint, headers=headers, params=params, timeout=15
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                bt.logging.warning(
                    f"Failed to get active miners: HTTP {resp.status} - {text[:200]}"
                )
                return []
            try:
                payload = await resp.json(content_type=None)
                if not isinstance(payload.get("data"), list):
                    bt.logging.warning(
                        f"Unexpected payload format when fetching active miners. "
                        f"Expected list, got: {type(payload.get('data'))}"
                    )
                    return []
                return payload["data"]
            except (json.JSONDecodeError, KeyError) as e:
                bt.logging.warning(
                    f"Failed to parse active miners response: {e}"
                )
                return []
    except aiohttp.ClientError as err:
        bt.logging.warning(f"Network error fetching active miners: {err}")
        return []
    except asyncio.TimeoutError:
        bt.logging.warning(f"Timeout fetching active miners from {self.active_miners_endpoint}")
        return []
    except Exception as err:  # noqa: BLE001
        bt.logging.warning(f"Unexpected error fetching active miners: {err}")
        return []
    finally:
        await session.close()


async def choose_players(
    self,
    competition: Competition = Competition.CLUE_COMPETITION,
    k: int = 2,
    exclude: List[int] = None,
) -> Tuple[List[int], List[str]]:
    """
    Returns up to ``k`` available uids for the provided competition.
    
    Handles edge cases:
    - Network failures during ping
    - Database connection issues
    - Insufficient available miners
    - API failures for active miners
    
    Args:
        competition: Competition type
        k: Number of players to select
        exclude: List of UIDs to exclude
        
    Returns:
        Tuple of (selected_uids, observer_hotkeys)
    """
    exclude_set = {int(uid) for uid in (exclude or [])}
    exclude_set.update(
        int(uid)
        for uid in self.metagraph.uids
        if self.metagraph.S[uid] < self.config.neuron.minimum_stake_requirement
    )
    uids_to_ping = [uid for uid in self.metagraph.uids if uid not in exclude_set]
    
    if not uids_to_ping:
        bt.logging.warning(
            f"No UIDs available to ping after exclusions. "
            f"Total UIDs: {len(self.metagraph.uids)}, Excluded: {len(exclude_set)}"
        )
        return [], []

    # Ping miners with retry logic
    try:
        ping_successful_uids, failed_uids = await ping_uids(
            self.dendrite, self.metagraph, uids_to_ping, timeout=30
        )
        if failed_uids:
            bt.logging.debug(
                f"Initial ping failed for {len(failed_uids)} UIDs. Retrying..."
            )
            retry_successful_uids, _ = await ping_uids(
                self.dendrite, self.metagraph, failed_uids, timeout=10
            )
            ping_successful_uids.extend(retry_successful_uids)
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Failed to ping miners: {err}")
        return [], []

    ping_successful_set = {int(uid) for uid in ping_successful_uids}
    
    if not ping_successful_set:
        bt.logging.error(
            f"No miners responded to ping. Total pinged: {len(uids_to_ping)}"
        )
        return [], []

    window_seconds = self.scoring_window_seconds
    window_scores = {}
    self._local_counts_in_window = {}
    self._global_counts_in_window = {}
    self._local_counts_in_epoch = {}
    self._global_counts_in_epoch = {}
    
    try:
        blocks_since_epoch = self.subtensor.get_subnet_info(
            self.config.netuid
        ).blocks_since_epoch
        end_ts = int(
            self.subtensor.get_timestamp().timestamp() + (360 - blocks_since_epoch) * 12
        )
        since_ts = end_ts - int(window_seconds)
        window_scores, _, _ = self.score_store.window_average_scores_by_hotkey(
            competition.value, since_ts, end_ts
        )
        self._local_counts_in_window, self._global_counts_in_window = (
            self.score_store.records_in_window(
                self.wallet.hotkey.ss58_address, competition.value, since_ts, end_ts
            )
        )
        self._local_counts_in_epoch, self._global_counts_in_epoch = (
            self.score_store.records_in_window(
                self.wallet.hotkey.ss58_address,
                competition.value,
                (end_ts - (360 * 12)),
                end_ts,
            )
        )
    except Exception as err:  # noqa: BLE001
        bt.logging.error(
            f"Failed to fetch window scores from database: {err}. "
            f"Continuing with empty scores (may affect miner selection fairness)."
        )
        # Continue with empty scores rather than failing completely
        window_scores = {}
        self._local_counts_in_window = {}
        self._global_counts_in_window = {}
        self._local_counts_in_epoch = {}
        self._global_counts_in_epoch = {}
    # fetch active miners(hotkey) who joined games
    try:
        active_miners = await fetch_active_miners(self, competition)
        active_miners_uids = [
            int(uid)
            for uid in self.metagraph.uids
            if self.metagraph.hotkeys[uid] in active_miners
        ]
        bt.logging.info(f"Active miners uids: {active_miners_uids}")
        exclude_set.update(uid for uid in active_miners_uids)
    except Exception as err:  # noqa: BLE001
        bt.logging.warning(
            f"Failed to fetch active miners from API: {err}. "
            f"Continuing without active miner exclusion (may affect fairness)."
        )
        # Continue without active miner exclusion rather than failing

    available_pool = make_available_pool(self, list(exclude_set))
    selected: List[int] = []
    observer_hotkeys: List[str] = []

    # Step 1: Select first player:
    while len(selected) < 1 and available_pool:

        for uid in list(available_pool):

            if uid in selected:
                continue

            hotkey = self.metagraph.hotkeys[uid]

            available_pool.remove(uid)

            observer_hotkeys.append(hotkey)
            exclude_set.add(uid)

            if uid not in ping_successful_set:
                bt.logging.warning(f"UID {uid} is not in successful ping set")
                continue

            score = float(window_scores.get(hotkey, 0.0))
            if score < -1.0:
                bt.logging.warning(f"UID {uid} has low score: {score}")
                continue

            selected.append(uid)
            observer_hotkeys.pop()

            bt.logging.info(f"Selected first player: {uid}")
            break

        available_pool = make_available_pool(self, list(exclude_set))

    bt.logging.debug(f"Excluded uids after first selection: {exclude_set}")

    if len(selected) == 0:
        bt.logging.error(
            f"No available miners could be selected after filtering. "
            f"Ping successful: {len(ping_successful_set)}, "
            f"Available pool size: {len(available_pool)}, "
            f"Excluded: {len(exclude_set)}"
        )
        return [], []

    first_hotkey = self.metagraph.hotkeys[selected[0]]
    # Step 2: Select second player (who has closest score to first player):
    while len(selected) < k:
        available_pool = make_available_pool_for_second_player(self, list(exclude_set))
        if not available_pool:
            bt.logging.warning("No available miners left to select from.")
            break
        # Sort available pool by score distance to first selected player
        available_pool.sort(
            key=lambda uid: abs(
                float(window_scores.get(self.metagraph.hotkeys[uid], 0.0))
                - float(window_scores.get(first_hotkey, 0.0))
            )
        )
        for uid in list(available_pool):
            hotkey = self.metagraph.hotkeys[uid]

            available_pool.remove(uid)
            observer_hotkeys.append(hotkey)
            exclude_set.add(uid)

            if uid not in ping_successful_set:
                bt.logging.warning(f"UID {uid} is not in successful ping set")
                continue

            score = float(window_scores.get(hotkey, 0.0))
            if score < -1.0:
                bt.logging.warning(f"UID {uid} has low score: {score}")
                continue

            selected.append(uid)
            observer_hotkeys.pop()
            break

    if len(selected) < k:
        bt.logging.warning(
            f"Selected only {len(selected)} miner(s) out of requested {k}."
        )
    else:
        bt.logging.info(
            f"Selected miners: {selected}, selected counts: {[self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0) for uid in selected]}"
        )
    random.shuffle(selected)
    return selected, observer_hotkeys
