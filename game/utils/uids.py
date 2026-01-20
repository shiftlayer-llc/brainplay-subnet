import random
import time
import aiohttp
import bittensor as bt
from game.api.get_query_axons import ping_uids
import numpy as np
from typing import List, Tuple

from game.utils.game import Competition
from game.utils.commit import read_endpoints
from game.utils.targon import check_endpoints, get_metadata


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
    session = aiohttp.ClientSession()
    try:
        headers = self.build_signed_headers()
        params = {"competition": competition.value}
        async with session.get(
            self.active_miners_endpoint, headers=headers, params=params, timeout=15
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                bt.logging.error(f"Failed to get active miners: {resp.status} {text}")
                return []
            payload = await resp.json(content_type=None)
            if not isinstance(payload["data"], list):
                bt.logging.error(
                    "Unexpected payload when fetching active miners; expected list."
                )
                return []
            return payload["data"]
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Exception fetching active miners: {err}")
        return []
    finally:
        await session.close()


async def choose_players(
    self,
    competition: Competition = Competition.CODENAMES_CLUE,
    k: int = 2,
    exclude: List[int] = None,
) -> Tuple[List[int], List[str]]:
    """Returns up to ``k`` available uids for the provided competition."""

    exclude_set = {int(uid) for uid in (exclude or [])}
    exclude_set.update(
        int(uid)
        for uid in self.metagraph.uids
        if self.metagraph.S[uid] < self.config.neuron.minimum_stake_requirement
        or self.metagraph.S[uid] > self.config.blacklist.minimum_stake_requirement
    )
    uids_to_ping = [uid for uid in self.metagraph.uids if uid not in exclude_set]
    targon_endpoints = read_endpoints(self, competition, uids_to_ping)

    responsive_uids = await check_endpoints(self, targon_endpoints, timeout=30)

    window_seconds = self.scoring_window_seconds
    window_scores = {}
    self._local_counts_in_window = {}
    self._global_counts_in_window = {}
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
        bt.logging.error(f"Failed to fetch window scores: {err}")
        return [], []

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

            if uid not in responsive_uids:
                bt.logging.warning(f"UID {uid} is not in responsive set")
                continue

            selected.append(uid)
            observer_hotkeys.pop()

            bt.logging.info(f"Selected first player: {uid}")
            break

        available_pool = make_available_pool(self, list(exclude_set))

    bt.logging.debug(f"Excluded uids after first selection: {exclude_set}")

    if len(selected) == 0:
        bt.logging.error("No available miners could be selected.")
        return [], []

    while len(selected) < k:
        available_pool = make_available_pool_for_second_player(self, list(exclude_set))
        if not available_pool:
            bt.logging.warning("No available miners left to select from.")
            break
        for uid in list(available_pool):
            hotkey = self.metagraph.hotkeys[uid]

            available_pool.remove(uid)
            observer_hotkeys.append(hotkey)
            exclude_set.add(uid)

            if uid not in responsive_uids:
                bt.logging.warning(f"UID {uid} is not in responsive set")
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
    metadata = {
        uid: {
            "endpoint": targon_endpoints[uid],
            "reasoning": get_metadata(self, targon_endpoints[uid]).get(
                "reasoning", "none"
            ),
        }
        for uid in selected
    }
    return selected, observer_hotkeys, metadata
