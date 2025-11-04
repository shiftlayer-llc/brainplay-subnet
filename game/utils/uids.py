import random
import time
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
    # Step 2: Exclude uids game count in current epoch is non-zero
    available_pool = [
        uid
        for uid in available_pool
        if self._global_counts_in_epoch.get(self.metagraph.hotkeys[uid], 0) == 0
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
        window_scores = self.score_store.window_average_scores_by_hotkey(
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

    # Step 2: Select remaining players:
    while len(selected) < k and available_pool:
        # Sort available pool by score distance to first selected player
        first_hotkey = self.metagraph.hotkeys[selected[0]]
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

        available_pool = make_available_pool(self, list(exclude_set))

    if len(selected) < k:
        bt.logging.warning(
            f"Selected only {len(selected)} miner(s) out of requested {k}."
        )
    else:
        bt.logging.info(
            f"Selected miners: {selected}, selected counts: {[self._local_counts_in_window.get(self.metagraph.hotkeys[uid], 0) for uid in selected]}"
        )

    return selected, observer_hotkeys
