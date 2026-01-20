import json
from typing import List, Dict
from game.utils.game import Competition


def read_endpoints(self, competition: Competition, uids: List[int]) -> Dict[int, dict]:
    """Reads the endpoints for the given list of UIDs.

    Args:
        uids (List[int]): List of UIDs to read endpoints for.
    Returns:
        Dict[int, dict]: A dictionary mapping UIDs to their endpoints.
    """
    targon_endpoints = {}
    for uid in uids:
        try:
            commit_data = self.subtensor.get_commitment(self.netuid, uid)
            targon_endpoints[uid] = json.loads(commit_data)
            if not competition.value in targon_endpoints[uid]:
                continue
            targon_endpoints[uid] = targon_endpoints[uid][competition.value]
        except Exception as e:
            continue
    return targon_endpoints
