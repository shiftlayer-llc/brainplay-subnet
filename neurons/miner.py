# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2025 ShiftLayer

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

import time
import typing
import json
import ast
import bittensor as bt
import os
from dotenv import load_dotenv
import game
from game.utils.spySysPrompt import spySysPrompt
from game.utils.opSysPrompt import opSysPrompt

# Bittensor Miner Template:
from game.protocol import CodenamesSynapse, CodenamesSynapseOutput, PingSynapse

from openai import OpenAI
from openai import (
    AuthenticationError,
    RateLimitError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
)

# import base miner class which takes care of most of the boilerplate
from game.base.miner import BaseMinerNeuron

load_dotenv()


class Miner(BaseMinerNeuron):
    """
    Your miner neuron class. You should use this class to define your miner's behavior. In particular, you should replace the forward function with your own logic. You may also want to override the blacklist and priority functions according to your needs.

    This class inherits from the BaseMinerNeuron class, which in turn inherits from BaseNeuron. The BaseNeuron class takes care of routine tasks such as setting up wallet, subtensor, metagraph, logging directory, parsing config, etc. You can override any of the methods in BaseNeuron if you need to customize the behavior.

    This class provides reasonable default behavior for a miner such as blacklisting unrecognized hotkeys, prioritizing requests based on stake, and forwarding requests to the forward function. If you need to define custom
    """

    def __init__(self, config=None):
        super(Miner, self).__init__(config=config)
        if not self.check_openai_key():
            raise ValueError("Invalid OPENAI_KEY environment variable.")
        self.axon.attach(
            forward_fn=self.pong,
            blacklist_fn=self.blacklist_ping,
        )

    def check_openai_key(self):
        retries = 3
        timeout = 5
        client = OpenAI(timeout=timeout, api_key=os.environ.get("OPENAI_KEY"))
        last_err = None

        for attempt in range(retries + 1):
            try:
                _ = client.responses.create(
                    model="gpt-4o",
                    input="api key test",
                    max_output_tokens=16,
                )
                return True
            except AuthenticationError as e:
                bt.logging.error(f"AUTH ERROR: {e}")
                return False
            except (
                RateLimitError,
                APIConnectionError,
                APITimeoutError,
                APIStatusError,
            ) as e:
                last_err = e
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except Exception as e:  # safety net
                last_err = e
                break
        if last_err:
            bt.logging.error(f"FAILED: {last_err}")
            return False
        return True

    async def pong(self, synapse: PingSynapse) -> PingSynapse:
        """
        Responds to a Ping with a Pong response, indicating the miner's availability.

        Args:
            synapse (Ping): The incoming ping synapse from a validator.

        Returns:
            Ping: The response synapse with the is_available field set to True.
        """
        bt.logging.info("💌 Received Ping request")
        synapse.is_available = True
        return synapse

    async def forward(
        self, synapse: game.protocol.CodenamesSynapse
    ) -> game.protocol.CodenamesSynapse:
        """
        Handles the incoming 'GameSynapse' by executing a series of operations based on the game state.
        This method should be customized to implement the specific logic required for the miner's function.

        Args:
            synapse (game.protocol.GameSynapse): The synapse object containing the game state data.

        Returns:
            game.protocol.GameSynapse: The synapse object with updated fields based on the miner's processing logic.

        The 'forward' function is a template and should be tailored to fit the miner's specific operational needs.
        This method illustrates a basic framework for processing game-related data.
        """

        bt.logging.info("💌 Received GameSynapse request")

        async def get_gpt5_response(messages):
            try:
                client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))
                result = client.responses.create(
                    model="gpt-5",
                    input=messages,
                    reasoning={
                        "effort": "minimal"
                    },  # Optional: control reasoning effort
                )
                return result.output_text
            except Exception as e:
                bt.logging.error(f"Error fetching response from GPT-4: {e}")
                return None

        # Build board and clue strings outside the f-string to avoid backslash-in-expression errors.
        messages = []
        if synapse.your_role == "operative":
            board = [
                {
                    "word": card.word,
                    "isRevealed": card.is_revealed,
                    "color": card.color if card.is_revealed else None,
                }
                for card in synapse.cards
            ]
            clue_block = (
                f"Your Clue: {synapse.your_clue}\nNumber: {synapse.your_number}"
            )
        else:
            board = synapse.cards
            clue_block = ""

        userPrompt = f"""
        ### Current Game State
        Your Team: {synapse.your_team}
        Your Role: {synapse.your_role}
        Red Cards Left to Guess: {synapse.remaining_red}
        Blue Cards Left to Guess: {synapse.remaining_blue}

        Board: {board}

        {clue_block}"""
        messages = []
        messages.append(
            {
                "role": "system",
                "content": (
                    spySysPrompt if synapse.your_role == "spymaster" else opSysPrompt
                ),
            }
        )
        messages.append({"role": "user", "content": userPrompt})

        response_str = await get_gpt5_response(messages)
        response_dict = json.loads(response_str)
        if "valid" in response_dict:
            valid = response_dict["valid"]
            if valid is False:
                bt.logging.warning(
                    f"🚨 Invalid clue detected: {synapse.your_clue}, reason: {response_dict['reasoning']}"
                )
        else:
            valid = None
        if "clue" in response_dict:
            clue = response_dict["clue"]
        else:
            clue = None
        if "number" in response_dict:
            number = response_dict["number"]
        else:
            number = None
        if "reasoning" in response_dict:
            reasoning = response_dict["reasoning"]
        else:
            reasoning = None

        if "guesses" in response_dict:
            guesses = response_dict["guesses"]
        else:
            guesses = None

        synapse.output = CodenamesSynapseOutput(
            clue_text=clue,
            number=number,
            reasoning=reasoning,
            guesses=guesses,
            clue_validity=valid,
        )
        bt.logging.info(f"🚀 llm response: {synapse.output}")

        return synapse

    async def _blacklist(self, synapse: bt.Synapse) -> typing.Tuple[bool, str]:
        """
        Evaluates whether an incoming request should be blacklisted and ignored based on predefined security criteria.

        The blacklist function operates before the synapse data is deserialized, utilizing request headers to make
        decisions. This preemptive check is crucial to conserve resources by filtering out requests that will not
        be processed.

        Args:
            synapse (game.protocol.GameSynapse): A synapse object derived from the incoming request's headers.

        Returns:
            Tuple[bool, str]: A tuple where the first element is a boolean indicating if the synapse's hotkey is
                              blacklisted, and the second element is a string explaining the reason.

        This function serves as a security measure to prevent unnecessary processing of undesirable requests. It is
        advisable to enhance this function with checks for entity registration, validator status, and adequate stake
        before synapse data deserialization to reduce processing load.

        Suggested blacklist criteria:
        - Reject requests if the hotkey is not a registered entity in the metagraph.
        - Consider blacklisting entities that are not validators or lack sufficient stake.

        In practice, it is prudent to blacklist requests from non-validators or entities with insufficient stake.
        This can be verified using metagraph.S and metagraph.validator_permit. The sender's uid can be obtained via
        metagraph.hotkeys.index(synapse.dendrite.hotkey).

        If none of the blacklist conditions are met, the request should proceed to further processing.
        """

        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return True, "Missing dendrite or hotkey"

        # TODO(developer): Define how miners should blacklist requests.
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if (
            not self.config.blacklist.allow_non_registered
            and synapse.dendrite.hotkey not in self.metagraph.hotkeys
        ):
            # Ignore requests from un-registered entities.
            bt.logging.debug(
                f"Blacklisting un-registered hotkey {synapse.dendrite.hotkey}"
            )
            return True, "Unrecognized hotkey"
        # Pass if owner of the subnet is the sender
        if uid == 0:
            bt.logging.debug(f"Not Blacklisting owner hotkey {synapse.dendrite.hotkey}")
            return False, "Owner hotkey"
        if self.config.blacklist.force_validator_permit:
            # If the config is set to force validator permit, then we should only allow requests from validators.
            if not self.metagraph.validator_permit[uid]:
                bt.logging.debug(
                    f"Blacklisting a request from non-validator hotkey {synapse.dendrite.hotkey}"
                )
                return True, "Non-validator hotkey"
        # TODO: enable this in mainnet
        stake = self.metagraph.S[uid].item()
        if stake < self.config.blacklist.minimum_stake_requirement:
            return True, "pubkey stake below min_allowed_stake"

        bt.logging.debug(
            f"Not Blacklisting recognized hotkey {synapse.dendrite.hotkey}"
        )

        return False, "Hotkey recognized!"

    async def blacklist(
        self, synapse: game.protocol.CodenamesSynapse
    ) -> typing.Tuple[bool, str]:
        return await self._blacklist(synapse)

    async def blacklist_ping(self, synapse: PingSynapse) -> typing.Tuple[bool, str]:
        return await self._blacklist(synapse)

    async def priority(self, synapse: game.protocol.CodenamesSynapse) -> float:
        """
        The priority function is responsible for determining the sequence in which requests are processed. Requests
        deemed more valuable or of higher priority are handled before others. It is crucial to carefully design your
        own priority mechanism.

        This current implementation calculates priority for incoming requests based on the stake of the calling entity
        within the metagraph.

        Args:
            synapse (game.protocol.GameSynapse): The synapse object containing metadata about the incoming request.

        Returns:
            float: A priority score calculated from the stake of the calling entity.

        Miners may receive requests from multiple entities simultaneously. This function decides which request should
        be prioritized. Higher priority values mean the request is processed sooner, while lower values mean it is
        processed later.

        Example priority logic:
        - Entities with a higher stake receive a higher priority score.
        """
        if synapse.dendrite is None or synapse.dendrite.hotkey is None:
            bt.logging.warning("Received a request without a dendrite or hotkey.")
            return 0.0

        # TODO(developer): Define how miners should prioritize requests.
        caller_uid = self.metagraph.hotkeys.index(
            synapse.dendrite.hotkey
        )  # Get the caller index.
        priority = float(
            self.metagraph.S[caller_uid]
        )  # Return the stake as the priority.
        bt.logging.trace(
            f"Prioritizing {synapse.dendrite.hotkey} with value: {priority}"
        )
        return priority


# This is the main function, which runs the miner.
if __name__ == "__main__":
    try:
        with Miner() as miner:
            while True:
                bt.logging.info(f"Miner running... {time.time()}")
                time.sleep(10)
    except Exception as e:
        bt.logging.error(f"Miner failed with exception: {e}")
        bt.logging.info(f"Miner exiting...")
