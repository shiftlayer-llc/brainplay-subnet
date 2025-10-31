import random
import time
import bittensor as bt
from game.api.get_query_axons import ping_uids
import numpy as np
from typing import List, Tuple

from game.utils.game import Competition


async def get_random_uids(
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

    successful_uids = await ping_uids(
        self.dendrite, self.metagraph, uids_to_ping, timeout=30
    )
    successful_set = {int(uid) for uid in successful_uids}

    window_seconds = self.scoring_window_seconds
    window_scores = {}
    selection_counts = {}
    try:
        since = time.time() - float(window_seconds)
        window_scores = self.score_store.window_scores_by_hotkey(
            since, competition.value
        )
        selection_counts = self.score_store.selection_counts_since(
            since, competition.value
        )
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Failed to fetch window scores: {err}")
        window_scores = {}
        selection_counts = {}

    available_pool = [
        int(uid) for uid in self.metagraph.uids if int(uid) not in exclude_set
    ]

    random.shuffle(available_pool)
    selected: List[int] = []
    observer_hotkeys: List[str] = []

    while len(selected) < k and available_pool:
        available_selection_counts = [
            selection_counts.get(self.metagraph.hotkeys[uid])
            for uid in available_pool
            if self.metagraph.hotkeys[uid] in selection_counts
        ]
        min_selection_count = (
            min(available_selection_counts) if available_selection_counts else 0
        )

        for uid in list(available_pool):
            if len(selected) >= k:
                break
            if uid in selected:
                continue

            hotkey = self.metagraph.hotkeys[uid]
            current_count = selection_counts.get(hotkey, min_selection_count)
            if current_count > min_selection_count:
                continue

            try:
                available_pool.remove(uid)
            except ValueError:
                pass

            observer_hotkeys.append(hotkey)

            if uid not in successful_set:
                continue

            score = float(window_scores.get(hotkey, 0.0))
            if score < -2.0:
                bt.logging.warning(f"UID {uid} has low score: {score}")
                continue

            selected.append(uid)
            observer_hotkeys.pop()

            if len(selected) >= k:
                break

    if len(selected) < k:
        bt.logging.warning(
            f"Selected only {len(selected)} miner(s) out of requested {k}."
        )
    else:
        bt.logging.info(
            f"Selected miners: {selected}, selected counts: {[selection_counts.get(self.metagraph.hotkeys[uid], 0) for uid in selected]}"
        )

    return selected, observer_hotkeys
