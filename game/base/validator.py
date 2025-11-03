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


import copy
import os
import time
import json
import numpy as np
import asyncio
import argparse
import threading
from datetime import datetime, timezone
import bittensor as bt
import wandb

from typing import List, Union
from traceback import print_exception

from game.base.neuron import BaseNeuron
from game.base.utils.weight_utils import (
    process_weights_for_netuid,
    convert_weights_and_uids_for_emit,
)  # TODO: Replace when bittensor switches to numpy
from game.mock import MockDendrite
from game.utils.config import add_validator_args
from game.utils.game import Competition
from game.validator.score_store import ScoreStore
from game.validator.scoring_config import (
    parse_interval_to_seconds,
    SCORING_INTERVAL,
)
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.


class BaseValidatorNeuron(BaseNeuron):
    """
    Base class for Bittensor validators. Your validator should inherit from this class.
    """

    neuron_type: str = "ValidatorNeuron"

    @classmethod
    def add_args(cls, parser: argparse.ArgumentParser):
        super().add_args(parser)
        add_validator_args(cls, parser)

    def __init__(self, config=None):
        super().__init__(config=config)

        # Save a copy of the hotkeys to local memory.
        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)

        # Dendrite lets us send messages to other nodes (axons) in the network.
        if self.config.mock:
            self.dendrite = MockDendrite(wallet=self.wallet)
        else:
            self.dendrite = bt.dendrite(wallet=self.wallet)
        bt.logging.info(f"Dendrite: {self.dendrite}")

        # Set up initial scoring weights for validation
        bt.logging.info("Building validation weights.")
        self.scores = np.zeros(self.metagraph.n, dtype=np.float32)

        scores_db_path = os.path.join(self.config.neuron.full_path, "scores.db")
        if getattr(self.config, "clear_db", False):
            if os.path.exists(scores_db_path):
                try:
                    os.remove(scores_db_path)
                    bt.logging.info(
                        f"Removed existing score database at {scores_db_path}"
                    )
                except OSError as err:
                    bt.logging.error(
                        f"Failed to remove existing score database at {scores_db_path}: {err}"
                    )
            else:
                bt.logging.info(
                    "Score database flag set but no existing file found to remove."
                )
        self.backend_base = "https://backend.shiftlayer.ai"
        try:
            if getattr(self.config.subtensor, "network", None) == "test":
                self.backend_base = "https://dev-backend.shiftlayer.ai"
        except AttributeError:
            pass
        bt.logging.info(f"Using backend: {self.backend_base}")
        scores_endpoint = f"{self.backend_base}/api/v1/rooms/score"
        scores_fetch_endpoint = f"{self.backend_base}/api/v1/rooms/sync"
        self.score_store = ScoreStore(
            scores_db_path,
            backend_url=scores_endpoint,
            fetch_url=scores_fetch_endpoint,
            signer=self.build_signed_headers,
        )
        self.score_store.init(self.metagraph.hotkeys)
        scoring_interval_text = SCORING_INTERVAL
        if hasattr(self.config, "scoring") and getattr(
            self.config.scoring, "interval", None
        ):
            scoring_interval_text = self.config.scoring.interval
        self.scoring_window_seconds = parse_interval_to_seconds(scoring_interval_text)

        # Init wandb
        if self.config.wandb.off is False:
            bt.logging.info("Wandb logging is turned on.")
            bt.logging.info(
                f"Initializing wandb with project name: {self.config.wandb.project_name}, entity: {self.config.wandb.entity}"
            )
            self.wandb_run = None

            def _start_wandb_run():
                if self.wandb_run:
                    try:
                        self.wandb_run.finish()
                    except Exception as err:
                        bt.logging.warning(
                            f"Failed to finish existing Wandb run: {err}"
                        )
                self.wandb_run = wandb.init(
                    project=self.config.wandb.project_name,
                    entity=self.config.wandb.entity,
                    name=f"validator-{self.wallet.hotkey.ss58_address[:6]}",
                )
                if self.config.wandb.restart_interval > 0:
                    self._wandb_restart_timer = threading.Timer(
                        self.config.wandb.restart_interval * 3600, _start_wandb_run
                    )
                    self._wandb_restart_timer.daemon = True
                    self._wandb_restart_timer.start()
                    bt.logging.info(
                        f"Wandb auto-restart timer scheduled in {self.config.wandb.restart_interval} hours."
                    )

            _start_wandb_run()
        else:
            bt.logging.info("Wandb logging is turned off.")
            self.wandb_run = None

        # Init sync with the network. Updates the metagraph.
        self.sync()

        # Serve axon to enable external connections.
        if not self.config.neuron.axon_off:
            self.serve_axon()
        else:
            bt.logging.warning("axon off, not serving ip to chain.")

        # Create asyncio event loop to manage async tasks.
        self.loop = asyncio.get_event_loop()

        # Instantiate runners
        self.should_exit: bool = False
        self.is_running: bool = False
        self.thread: Union[threading.Thread, None] = None
        self.lock = asyncio.Lock()

    def serve_axon(self):
        """Serve axon to enable external connections."""

        bt.logging.info("serving ip to chain...")
        try:
            self.axon = bt.axon(wallet=self.wallet, config=self.config)

            try:
                self.subtensor.serve_axon(
                    netuid=self.config.netuid,
                    axon=self.axon,
                )
                bt.logging.info(
                    f"Running validator {self.axon} on network: {self.config.subtensor.chain_endpoint} with netuid: {self.config.netuid}"
                )
            except Exception as e:
                bt.logging.error(f"Failed to serve Axon with exception: {e}")
                pass

        except Exception as e:
            bt.logging.error(f"Failed to create Axon initialize with exception: {e}")
            pass

    async def concurrent_forward(self):
        coroutines = [
            self.forward() for _ in range(self.config.neuron.num_concurrent_forwards)
        ]
        await asyncio.gather(*coroutines)

    def run(self):
        """
        Initiates and manages the main loop for the miner on the Bittensor network. The main loop handles graceful shutdown on keyboard interrupts and logs unforeseen errors.

        This function performs the following primary tasks:
        1. Check for registration on the Bittensor network.
        2. Continuously forwards queries to the miners on the network, rewarding their responses and updating the scores accordingly.
        3. Periodically resynchronizes with the chain; updating the metagraph with the latest network state and setting weights.

        The essence of the validator's operations is in the forward function, which is called every step. The forward function is responsible for querying the network and scoring the responses.

        Note:
            - The function leverages the global configurations set during the initialization of the miner.
            - The miner's axon serves as its interface to the Bittensor network, handling incoming and outgoing requests.

        Raises:
            KeyboardInterrupt: If the miner is stopped by a manual interruption.
            Exception: For unforeseen errors during the miner's operation, which are logged for diagnosis.
        """

        # Check that validator is registered on the network.
        self.sync()

        bt.logging.info(f"Validator starting at block: {self.block}")

        # This loop maintains the validator's operations until intentionally stopped.
        while True:
            try:
                bt.logging.info(f"step({self.step}) block({self.block})")

                # Check weights version and run if matches
                weights_version = self.subtensor.get_subnet_hyperparameters(
                    self.config.netuid
                ).weights_version
                if self.spec_version != weights_version:
                    bt.logging.warning(
                        f"Spec version {self.spec_version} does not match subnet weights version {weights_version}. Please upgrade your code."
                    )
                    time.sleep(12)
                    continue
                # Run multiple forwards concurrently.
                self.loop.run_until_complete(self.concurrent_forward())

                # Check if we should exit.
                if self.should_exit:
                    break

                # Sync metagraph and potentially set weights.
                self.sync()

                self.step += 1

            # If someone intentionally stops the validator, it'll safely terminate operations.
            except KeyboardInterrupt:
                self.axon.stop()
                bt.logging.success("Validator killed by keyboard interrupt.")
                if self.wandb_run:
                    self.wandb_run.finish()
                if self._wandb_restart_timer:
                    self._wandb_restart_timer.cancel()
                exit()

            # In case of unforeseen errors, the validator will log the error and continue operations.
            except Exception as err:
                bt.logging.error(f"Error during validation: {str(err)}")
                bt.logging.debug(
                    str(print_exception(type(err), err, err.__traceback__))
                )

                time.sleep(2)

    def run_in_background_thread(self):
        """
        Starts the validator's operations in a background thread upon entering the context.
        This method facilitates the use of the validator in a 'with' statement.
        """
        if not self.is_running:
            bt.logging.debug("Starting validator in background thread.")
            self.should_exit = False
            self.thread = threading.Thread(target=self.run, daemon=True)
            self.thread.start()
            self.is_running = True
            bt.logging.debug("Started")

    def stop_run_thread(self):
        """
        Stops the validator's operations that are running in the background thread.
        """
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False
            self.score_store.close()
            bt.logging.debug("Stopped")

    def build_signed_headers(self) -> dict:
        timestamp = int(datetime.now(tz=timezone.utc).timestamp())
        message = f"<Bytes>{timestamp}</Bytes>"
        signature = self.wallet.hotkey.sign(message)
        return {
            "X-Validator-Hotkey": self.wallet.hotkey.ss58_address,
            "X-Validator-Signature": signature.hex(),
            "X-Validator-Timestamp": str(timestamp),
        }

    def __enter__(self):
        self.run_in_background_thread()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Stops the validator's background operations upon exiting the context.
        This method facilitates the use of the validator in a 'with' statement.

        Args:
            exc_type: The type of the exception that caused the context to be exited.
                      None if the context was exited without an exception.
            exc_value: The instance of the exception that caused the context to be exited.
                       None if the context was exited without an exception.
            traceback: A traceback object encoding the stack trace.
                       None if the context was exited without an exception.
        """
        if self.is_running:
            bt.logging.debug("Stopping validator in background thread.")
            self.should_exit = True
            self.thread.join(5)
            self.is_running = False
            bt.logging.debug("Stopped")

    def set_weights(self):
        """
        Sets the validator weights to the metagraph hotkeys based on the scores it has received from the miners. The weights determine the trust and incentive level the validator assigns to miner nodes on the network.
        """

        now = time.time()
        blocks_since_epoch = self.subtensor.get_subnet_info(
            self.config.netuid
        ).blocks_since_epoch

        end_ts = self.subtensor.get_timestamp().timestamp() - (blocks_since_epoch * 12)
        since_ts = end_ts - self.scoring_window_seconds

        latest_ts = self.score_store.latest_scores_all_timestamp()

        age_seconds = now - latest_ts
        if age_seconds > 3600:
            bt.logging.warning(
                f"Latest synced score is older than 1 hour ({age_seconds:.0f}s). Switching to burn code."
            )
            burn_weights = np.zeros(self.metagraph.n, dtype=np.float32)
            if self.metagraph.n > 0:
                burn_weights[0] = 1.0
            self._set_weights(burn_weights)
            return

        final_weights = np.zeros(self.metagraph.n, dtype=np.float32)
        for competition in Competition:
            weights = np.zeros(self.metagraph.n, dtype=np.float32)
            comp_value = competition.value

            comp_games = self.score_store.games_in_window(since_ts, end_ts, comp_value)
            if comp_games < 300:
                bt.logging.warning(
                    f"Not enough games for competition {comp_value}; skipping its allocation. ({comp_games} < 300)"
                )
                weights[0] = 1.0
                final_weights += weights
                continue

            comp_scores = self.score_store.window_average_scores_by_hotkey(
                comp_value, since_ts, end_ts
            )
            _, global_records_in_window = self.score_store.records_in_window(
                self.wallet.hotkey.ss58_address, competition.value, since_ts, end_ts
            )
            # Set record count limit for setting weights to avoid actors with few high scores (e.g new registrations)
            record_counts = sorted(
                [
                    global_records_in_window.get(hotkey, 0)
                    for hotkey in self.metagraph.hotkeys
                ],
                reverse=True,
            )
            record_count_limit = record_counts[
                int(len(record_counts) * 0.9)
            ]  # 90th percentile
            bt.logging.info(
                f"Competition {comp_value} record count limit for weight setting: {record_count_limit} (Max: {record_counts[0]})"
            )

            comp_scores_by_uid = {
                self.metagraph.hotkeys.index(hotkey): comp_scores.get(hotkey, 0.0)
                for hotkey in self.metagraph.hotkeys
            }
            bt.logging.info(
                f"Competition {comp_value} scores: \n {json.dumps(comp_scores_by_uid, indent=2)}"
            )
            if not comp_scores:
                bt.logging.warning(
                    f"No scores for competition {comp_value}; skipping its allocation."
                )
                continue

            top_score = max(comp_scores.values())
            if top_score <= 0:
                bt.logging.warning(
                    f"Top score for competition {comp_value} is non-positive; skipping."
                )
                weights[0] = 1.0
                final_weights += weights
                continue

            top_hotkeys = [
                hotkey for hotkey, score in comp_scores.items() if score == top_score
            ]
            winner_uids = []
            for hotkey in top_hotkeys:
                try:
                    winner_uids.append(self.metagraph.hotkeys.index(hotkey))
                except ValueError:
                    bt.logging.warning(
                        f"Top hotkey {hotkey} for competition {comp_value} not in metagraph."
                    )
            if not winner_uids:
                bt.logging.warning(
                    f"No top hotkeys for competition {comp_value} present in metagraph; skipping."
                )
                weights[0] = 1.0
                final_weights += weights
                continue

            if len(winner_uids) > 1:
                bt.logging.info(
                    f"Competition {comp_value} has multiple winners: {winner_uids} with score {top_score}; skipping"
                )
                weights[0] = 1.0
                final_weights += weights
                continue

            winner_uid = winner_uids[0]
            weights[winner_uid] = 1.0

            bt.logging.info(
                f"Competition {comp_value} winner: Miner {winner_uid} with score {top_score}"
            )

            final_weights += weights

        if final_weights.sum() == 0:
            bt.logging.warning(
                "No competition winners determined; skipping set_weights."
            )
            return

        # Normalize final weights
        self.scores = final_weights / sum(final_weights)

        bt.logging.info(f"Assigned scores: {self.scores}")

        if np.isnan(self.scores).any():
            bt.logging.warning(
                "Scores contain NaN values. This may be due to a lack of responses from miners, or a bug in your reward functions."
            )

        norm = np.linalg.norm(self.scores, ord=1, axis=0, keepdims=True)
        if np.any(norm == 0) or np.isnan(norm).any():
            norm = np.ones_like(norm)

        raw_weights = self.scores / norm
        self._set_weights(raw_weights)

    def _set_weights(self, weights: np.ndarray) -> None:
        weights = np.asarray(weights, dtype=np.float32)
        (
            processed_weight_uids,
            processed_weights,
        ) = process_weights_for_netuid(
            uids=self.metagraph.uids,
            weights=weights,
            netuid=self.config.netuid,
            subtensor=self.subtensor,
            metagraph=self.metagraph,
        )
        (
            uint_uids,
            uint_weights,
        ) = convert_weights_and_uids_for_emit(
            uids=processed_weight_uids, weights=processed_weights
        )
        result, msg = self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.config.netuid,
            uids=uint_uids,
            weights=uint_weights,
            wait_for_finalization=False,
            wait_for_inclusion=False,
            version_key=self.spec_version,
        )
        if result is True:
            bt.logging.info("set_weights on chain successfully!")
        else:
            bt.logging.error("set_weights failed", msg)

    def resync_metagraph(self):
        """Resyncs the metagraph and updates the hotkeys and moving averages based on the new metagraph."""
        bt.logging.info("resync_metagraph()")

        # Copies state of metagraph before syncing.
        previous_metagraph = copy.deepcopy(self.metagraph)

        # Sync the metagraph.
        self.metagraph.sync(subtensor=self.subtensor)

        # Check if the metagraph axon info has changed.
        if previous_metagraph.axons == self.metagraph.axons:
            return

        bt.logging.info(
            "Metagraph updated, re-syncing hotkeys, dendrite pool and moving averages"
        )
        # Zero out all hotkeys that have been replaced.
        for uid, hotkey in enumerate(self.hotkeys):
            if hotkey != self.metagraph.hotkeys[uid]:
                self.scores[uid] = 0  # hotkey has been replaced

        # Check to see if the metagraph has changed size.
        # If so, we need to add new hotkeys and moving averages.
        if len(self.hotkeys) < len(self.metagraph.hotkeys):
            # Update the size of the moving average scores.
            new_moving_average = np.zeros((self.metagraph.n))
            min_len = min(len(self.hotkeys), len(self.scores))
            new_moving_average[:min_len] = self.scores[:min_len]
            self.scores = new_moving_average

        # Update the hotkeys.
        self.hotkeys = copy.deepcopy(self.metagraph.hotkeys)

    def save_state(self):
        """Saves the state of the validator to a file."""
        bt.logging.info("Saving validator state.")

        # Save the state of the validator to file.
        np.savez(
            self.config.neuron.full_path + "/state.npz",
            step=self.step,
            scores=self.scores,
            hotkeys=self.hotkeys,
        )

    def load_state(self):
        """Loads the state of the validator from a file."""
        bt.logging.info("Loading validator state.")

        # Load the state of the validator from file.
        state = np.load(self.config.neuron.full_path + "/state.npz")
        self.step = state["step"]
        self.scores = state["scores"]
        self.hotkeys = state["hotkeys"]
