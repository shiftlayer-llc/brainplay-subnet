import random
import time
import bittensor as bt
from game.api.get_query_axons import ping_uids
import numpy as np
from typing import List


async def get_random_uids(self, k: int, exclude: List[int] = None) -> np.ndarray:
    """Returns up to ``k`` available uids following selection-count and score rules."""

    exclude_set = {int(uid) for uid in (exclude or [])}

    successful_uids = await ping_uids(
        self.dendrite, self.metagraph, self.metagraph.uids, timeout=30
    )
    successful_set = {int(uid) for uid in successful_uids}

    window_seconds = self.scoring_window_seconds
    window_scores = {}
    selection_counts = {}
    try:
        since = time.time() - float(window_seconds)
        window_scores = self.score_store.window_scores_by_hotkey(since)
        selection_counts = self.score_store.selection_counts_since(since)
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Failed to fetch window scores: {err}")
        window_scores = {}
        selection_counts = {}

    available_pool = [
        int(uid) for uid in self.metagraph.uids if int(uid) not in exclude_set
    ]

    random.shuffle(available_pool)
    selected: List[int] = []
    hotkeys_to_increase: List[str] = []  # Hotkeys to increase selection count for
    selected_ips: List[str] = []  # IPs to avoid selecting duplicates
    selected_coldkeys: List[str] = []  # Coldkeys to avoid selecting duplicates

    while len(selected) < k and len(available_pool) > 0:
        available_selection_counts = [
            selection_counts.get(self.metagraph.hotkeys[uid])
            for uid in available_pool
            if self.metagraph.hotkeys[uid] in selection_counts
        ]
        if len(available_selection_counts) > 0:
            min_selection_count = min(available_selection_counts)
        else:
            min_selection_count = 0

        for uid in available_pool:
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

            ip = self.metagraph.axons[uid].ip
            # Avoid selecting multiple miners from the same IP
            if ip in selected_ips:
                bt.logging.info(
                    f"Skipping UID {uid} from IP {ip} to avoid duplicates. Selected IPs: {selected_ips}"
                )
                continue

            coldkey = self.metagraph.coldkeys[uid]
            if coldkey in selected_coldkeys:
                bt.logging.info(
                    f"Skipping UID {uid} with coldkey {coldkey} to avoid duplicates. Selected coldkeys: {selected_coldkeys}"
                )

            # Mark hotkey to increase selection count
            hotkeys_to_increase.append(hotkey)

            if uid not in successful_set:
                continue

            score = float(window_scores.get(hotkey, 0.0))

            # Filter out very low score miners
            if score < -2.0:
                bt.logging.warning(f"UID {uid} has low score: {score}")
                continue

            selected.append(uid)
            selected_ips.append(ip)
            selected_coldkeys.append(coldkey)

    if len(selected) < k:
        bt.logging.warning(
            f"Selected only {len(selected)} miner(s) out of requested {k}."
        )
    else:
        bt.logging.info(
            f"Selected miners: {selected}, selected counts: {[selection_counts.get(self.metagraph.hotkeys[uid], 0) for uid in selected]}"
        )

    return selected, hotkeys_to_increase
