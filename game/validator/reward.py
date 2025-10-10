# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# TODO(developer): Set your name
# Copyright © 2023 <your name>

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
import numpy as np
from typing import List, Dict
import bittensor as bt


# def reward(winner, red_team:Dict, blue_team: Dict) -> float:
#     """
#     Reward the miner response to the dummy request. This method returns a reward
#     value for the miner, which is used to update the miner's score.

#     Returns:
#     - float: The reward value for the miner.
#     """

#     if winner == "red":

#     bt.logging.info(
#         f"In rewards, query val: {query}, response val: {response}, rewards val: {1.0 if response == query * 2 else 0}"
#     )
#     return 1.0 if response == query * 2 else 0


def get_rewards(
    self, winner, red_team: Dict, blue_team: Dict, end_reason: str = ""
) -> np.ndarray:
    """
    Calculates and returns an array of rewards based on the winning team.

    Args:
    - winner (str): The team that won the game, either "red" or "blue".
    - red_team (Dict): A dictionary representing the red team's members.
    - blue_team (Dict): A dictionary representing the blue team's members.

    Returns:
    - np.ndarray: An array of rewards for the team members based on the game outcome.
    """
    if winner == "red":
        rewards = np.array([1.0, 1.0, 0.0, 0.0])
        if end_reason == "invalid_clue":
            rewards[2] = -1.0
    elif winner == "blue":
        rewards = np.array([0.0, 0.0, 1.0, 1.0])
        if end_reason == "invalid_clue":
            rewards[0] = -1.0
    else:
        rewards = np.array([0.0, 0.0, 0.0, 0.0])
    return rewards
