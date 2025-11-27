import random
import time
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
    if minimum_local_count > 2:
        return []
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
        params = {}
        params["competition"] = competition.value
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
    competition: Competition = Competition.CLUE_COMPETITION,
    k: int = 2,
    exclude: List[int] = None,
) -> Tuple[List[int], List[str]]:
    """Returns up to ``k`` available uids for the provided competition."""

    exclude_set = {int(uid) for uid in (exclude or [])}
    exclude_set.update(
        int(uid)
        for uid in self.metagraph.uids
        if self.metagraph.S[uid] < self.config.neuron.minimum_stake_requirement
    )
    uids_to_ping = [uid for uid in self.metagraph.uids if uid not in exclude_set]

    ping_successful_uids, failed_uids = await ping_uids(
        self.dendrite, self.metagraph, uids_to_ping, timeout=30
    )
    retry_successful_uids, _ = await ping_uids(
        self.dendrite, self.metagraph, failed_uids, timeout=10
    )
    ping_successful_uids.extend(retry_successful_uids)

    ping_successful_set = {int(uid) for uid in ping_successful_uids}

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
    # fetch active miners(hotkey) who joined games
    active_miners = await fetch_active_miners(self, competition)
    active_miners_uids = [
        int(uid)
        for uid in self.metagraph.uids
        if self.metagraph.hotkeys[uid] in active_miners
    ]
    bt.logging.info(f"Active miners uids: {active_miners_uids}")
    exclude_set.update(uid for uid in active_miners_uids)

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
        bt.logging.error("No available miners could be selected.")
        return [], []

    selected.sort(
        key=lambda uid: window_scores.get(self.metagraph.hotkeys[uid], 0.0),
        reverse=True,
    )

    first_hotkey = self.metagraph.hotkeys[selected[0]]
    # Step 2: Select second player (who has closest score to first player):
    retry_count = 0
    while len(selected) < k and retry_count < 3:
        retry_count += 1
        available_pool = make_available_pool_for_second_player(self, list(exclude_set))
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
