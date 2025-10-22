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

import asyncio
import time
import uuid
import bittensor as bt
import aiohttp
import json
from game.protocol import GameSynapse, GameSynapseOutput
from game.utils.ruleSysPrompt import ruleSysPrompt
from game.validator.reward import get_rewards
from game.utils.uids import get_random_uids
import random
import typing
from game.utils.game import TParticipant
from game.utils.game import (
    GameState,
    Role,
    TeamColor,
    CardColor,
    CardType,
    Clue,
    ChatMessage,
)
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))


def organize_team(self, uids):
    """
    Organize the team with 4 miners randomly

    Args:
        uids (list[int]): The list of miner uids

    Returns:
        tuple[dict[str, int], dict[str, int]]: The red team and the blue team
    """
    # devide into 2 teams randomly
    team1 = {"spymaster": uids[0], "operative": uids[1]}
    team2 = {"spymaster": uids[2], "operative": uids[3]}
    return team1, team2


def resetAnimations(self, cards):
    """
    Reset the animation of the cards

    Args:
        self (:obj:`bittensor.neuron.Neuron`): The neuron object which contains all the necessary state for the validator.
        cards (list[CardType]): The list of cards
    """
    for card in cards:
        card.was_recently_revealed = False


async def create_room(self, game_state: GameState):
    endpoint = f"{self.backend_base}/api/v1/rooms/create"
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "validatorKey": self.wallet.hotkey.ss58_address,
                "cards": [
                    {
                        "word": card.word,
                        "color": card.color,
                        "isRevealed": card.is_revealed,
                        "wasRecentlyRevealed": card.was_recently_revealed,
                    }
                    for card in game_state.cards
                ],
                "chatHistory": [],  # Game just started, no chat history yet
                "currentTeam": game_state.currentTeam.value,
                "currentRole": game_state.currentRole.value,
                "previousTeam": None,  # Game just started, no previous team
                "previousRole": None,  # Game just started, no previous role
                "remainingRed": game_state.remainingRed,
                "remainingBlue": game_state.remainingBlue,
                "currentClue": None,  # Game just started, no current clue
                "currentGuesses": [],  # Game just started, no guesses yet
                "gameWinner": None,  # Game just started, no winner
                "participants": [
                    {
                        "name": p.name,
                        "hotkey": p.hotkey,
                        "team": p.team.value,
                        "role": p.role.value,
                    }
                    for p in game_state.participants
                ],
            }
            headers = self.build_signed_headers()
            async with session.post(
                endpoint, json=payload, headers=headers, timeout=10
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    bt.logging.error(
                        f"Failed to create new room: HTTP {response.status} - {text}"
                    )
                    return None
                else:
                    response_text = await response.text()
                    bt.logging.info(f"Room created successfully: {response_text}")
                    try:
                        return json.loads(response_text)["data"]["id"]
                    except (json.JSONDecodeError, KeyError) as e:
                        bt.logging.error(f"Failed to parse room creation response: {e}")
                        return None
    except aiohttp.ClientError as e:
        bt.logging.error(f"Network error creating room: {e}")
        return None
    except asyncio.TimeoutError:
        bt.logging.error(f"Timeout error creating room at {endpoint}")
        return None
    except Exception as e:
        bt.logging.error(f"Unexpected error creating room: {e}")
        return None


async def update_room(self, game_state: GameState, roomId):
    endpoint = f"{self.backend_base}/api/v1/rooms/{roomId}"
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "validatorKey": self.wallet.hotkey.ss58_address,
                "cards": [
                    {
                        "word": card.word,
                        "color": card.color,
                        "isRevealed": card.is_revealed,
                        "wasRecentlyRevealed": card.was_recently_revealed,
                    }
                    for card in game_state.cards
                ],
                "chatHistory": [
                    {
                        "sender": msg.sender.value,
                        "message": msg.message,
                        "team": msg.team.value,
                        "reasoning": msg.reasoning,
                        "clueText": msg.clueText,
                        "number": msg.number,
                        "guesses": msg.guesses,
                    }
                    for msg in game_state.chatHistory
                ],
                "currentTeam": game_state.currentTeam.value,
                "currentRole": game_state.currentRole.value,
                "previousTeam": (
                    game_state.previousTeam.value if game_state.previousTeam else None
                ),
                "previousRole": (
                    game_state.previousRole.value if game_state.previousRole else None
                ),
                "remainingRed": game_state.remainingRed,
                "remainingBlue": game_state.remainingBlue,
                "currentClue": (
                    {
                        "clueText": game_state.currentClue.clueText,
                        "number": game_state.currentClue.number,
                    }
                    if game_state.currentClue
                    else None
                ),
                "currentGuesses": (
                    game_state.currentGuesses if game_state.currentGuesses else []
                ),
                "gameWinner": (
                    game_state.gameWinner.value if game_state.gameWinner else None
                ),
                "participants": [
                    {
                        "name": p.name,
                        "hotkey": p.hotkey,
                        "team": p.team.value,
                        "role": p.role.value,
                    }
                    for p in game_state.participants
                ],
                # "createdAt": "2025-04-07T17:49:16.457Z"
            }
            headers = self.build_signed_headers()
            async with session.patch(
                endpoint, json=payload, headers=headers, timeout=10
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    bt.logging.error(
                        f"Failed to update room state: HTTP {response.status} - {response_text}"
                    )
                else:
                    bt.logging.info("Room state updated successfully")
    except aiohttp.ClientError as e:
        bt.logging.error(f"Network error updating room {roomId}: {e}")
    except asyncio.TimeoutError:
        bt.logging.error(f"Timeout error updating room {roomId} at {endpoint}")
    except Exception as e:
        bt.logging.error(f"Unexpected error updating room {roomId}: {e}")


async def remove_room(self, roomId):
    # return
    endpoint = f"{self.backend_base}/api/v1/rooms/{roomId}"
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "validatorKey": self.wallet.hotkey.ss58_address,
                "roomId": roomId,
                "action": "delete_room",
            }
            headers = self.build_signed_headers()
            async with session.delete(
                endpoint, headers=headers, timeout=10
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    bt.logging.error(
                        f"Failed to delete room: HTTP {response.status} - {response_text}"
                    )
                else:
                    bt.logging.info("Room deleted successfully")
    except aiohttp.ClientError as e:
        bt.logging.error(f"Network error deleting room {roomId}: {e}")
    except asyncio.TimeoutError:
        bt.logging.error(f"Timeout error deleting room {roomId} at {endpoint}")
    except Exception as e:
        bt.logging.error(f"Unexpected error deleting room {roomId}: {e}")


async def forward(self):
    """
    This method is invoked by the validator at each time step.

    Its main function is to query the network and evaluate the responses.

    Parameters:
        self (bittensor.neuron.Neuron): The neuron instance containing all necessary state information for the validator.

    """
    # Select 4 miners randomly and organize 2 teams
    miner_uids, selected_hotkeys = await get_random_uids(
        self, k=self.config.neuron.sample_size
    )
    # Exeption handling when number of miners less than 4
    if len(miner_uids) < 4:
        return

    (red_team, blue_team) = organize_team(self, miner_uids)
    bt.logging.info(f"\033[91mRed Team: {red_team}\033[0m")
    bt.logging.info(f"\033[94mBlue Team: {blue_team}\033[0m")

    rs_uid = red_team["spymaster"]
    ro_uid = red_team["operative"]
    bs_uid = blue_team["spymaster"]
    bo_uid = blue_team["operative"]

    rs_hotkey = self.metagraph.axons[rs_uid].hotkey
    ro_hotkey = self.metagraph.axons[ro_uid].hotkey
    bs_hotkey = self.metagraph.axons[bs_uid].hotkey
    bo_hotkey = self.metagraph.axons[bo_uid].hotkey

    participants: typing.List[TParticipant] = []
    for team in [red_team, blue_team]:
        participants.append(
            TParticipant(
                name="Miner " + str(team["spymaster"]),
                hotkey=self.metagraph.axons[team["spymaster"]].hotkey,
                team=TeamColor.RED if team == red_team else TeamColor.BLUE,
                role=Role.SPYMASTER,
            )
        )
        participants.append(
            TParticipant(
                name="Miner " + str(team["operative"]),
                hotkey=self.metagraph.axons[team["operative"]].hotkey,
                team=TeamColor.RED if team == red_team else TeamColor.BLUE,
                role=Role.OPERATIVE,
            )
        )

    # * Initialize game
    game_step = 0
    started_at = time.time()
    game_state = GameState(participants=participants)
    end_reason = "completed"

    # Create new room via API call
    # ===============🤞ROOM CREATE===================
    roomId = await create_room(self, game_state)
    if roomId is None:
        bt.logging.error("Failed to create room, exiting.")
        return

    # ===============GAME LOOP=======================
    while game_state.gameWinner is None:
        bt.logging.info("=" * 50)
        bt.logging.info(f"Game step {game_step + 1}")
        bt.logging.info(f"Current Team: {game_state.currentTeam}")
        bt.logging.info(f"Current Role: {game_state.currentRole}")

        # 1. Prepare the query
        if game_state.currentRole == Role.SPYMASTER:
            cards = game_state.cards
            if game_state.currentTeam == TeamColor.RED:
                to_uid = red_team["spymaster"]
            else:
                to_uid = blue_team["spymaster"]
        else:
            # If receiver is operative, we need to send the cards without color
            cards = [
                CardType(
                    word=card.word,
                    color=card.color if card.is_revealed else None,
                    is_revealed=card.is_revealed,
                    was_recently_revealed=card.was_recently_revealed,
                )
                for card in game_state.cards
            ]
            if game_state.currentTeam == TeamColor.RED:
                to_uid = red_team["operative"]
            else:
                to_uid = blue_team["operative"]

            # Remove animation of recently revealed cards
            resetAnimations(self, game_state.cards)

        your_team = game_state.currentTeam
        your_role = game_state.currentRole
        remaining_red = game_state.remainingRed
        remaining_blue = game_state.remainingBlue
        your_clue = (
            game_state.currentClue.clueText
            if game_state.currentClue is not None
            else None
        )
        your_number = (
            game_state.currentClue.number
            if game_state.currentClue is not None
            else None
        )

        synapse = GameSynapse(
            your_team=your_team,
            your_role=your_role,
            remaining_red=remaining_red,
            remaining_blue=remaining_blue,
            your_clue=your_clue,
            your_number=your_number,
            cards=cards,
        )

        # 2. Main Game Logic
        start_at = time.time()
        axon = self.metagraph.axons[to_uid]

        # 2.1 Query the participant
        if your_role == Role.SPYMASTER:
            try:
                # Select decoys fresh each spymaster turn
                decoy_uids, _ = await get_random_uids(self, k=10)
                # Exclude active players and direct recipient
                decoy_uids = [
                    uid for uid in decoy_uids if uid not in miner_uids and uid != to_uid
                ]
                bt.logging.info(f"Decoy uids: {decoy_uids}")
                # If fewer than 10, pad with random others from metagraph
                # if len(decoy_uids) < 10:
                #     candidates = [
                #         uid
                #         for uid in range(self.metagraph.n)
                #         if uid not in miner_uids and uid not in decoy_uids and uid != to_uid
                #     ]
                #     random.shuffle(candidates)
                #     decoy_uids.extend(candidates[: 10 - len(decoy_uids)])

                # Build decoy synapse with shuffled colors
                # Build one shared fake board for all decoy uids: randomize red/blue only
                decoy_colors = [card.color for card in game_state.cards]
                rb_indices = [
                    i for i, c in enumerate(decoy_colors) if c in ("red", "blue")
                ]
                rb_colors = [decoy_colors[i] for i in rb_indices]
                random.shuffle(rb_colors)
                for idx, color in zip(rb_indices, rb_colors):
                    decoy_colors[idx] = color
                decoy_cards = [
                    CardType(
                        word=card.word,
                        color=decoy_colors[i],
                        is_revealed=card.is_revealed,
                        was_recently_revealed=card.was_recently_revealed,
                    )
                    for i, card in enumerate(game_state.cards)
                ]
                decoy_synapse = GameSynapse(
                    your_team=game_state.currentTeam,
                    your_role=Role.SPYMASTER,
                    remaining_red=game_state.remainingRed,
                    remaining_blue=game_state.remainingBlue,
                    your_clue=None,
                    your_number=None,
                    cards=decoy_cards,
                )

                targets = [to_uid] + decoy_uids
                response = None
                for uid in targets:
                    if uid == to_uid:
                        # Real spymaster query with retries
                        bt.logging.info(f"⏬ Sending game query to miner {uid}, {axon}")
                        for i in range(3):
                            started_at = time.time()
                            response = await self.dendrite(
                                axons=self.metagraph.axons[uid],
                                synapse=synapse,
                                deserialize=True,
                                timeout=30,
                            )
                            if response is not None:
                                break
                        bt.logging.info(
                            f"📨 Real spymaster response received from {uid}: {response}"
                        )
                    else:
                        # Fire-and-forget decoys
                        try:
                            bt.logging.info(
                                f"🤫 Sending decoy query to miner {uid}, {axon}"
                            )
                            asyncio.create_task(
                                self.dendrite(
                                    axons=self.metagraph.axons[uid],
                                    synapse=decoy_synapse,
                                    deserialize=False,
                                    timeout=5,
                                )
                            )
                        except Exception as e:  # noqa: BLE001
                            bt.logging.warning(f"Decoy send failed to {uid}: {e}")
                bt.logging.info(
                    f"📤 Distributed decoy boards to {len(decoy_uids)} miners"
                )
            except Exception as e:  # noqa: BLE001
                bt.logging.warning(f"Failed unified spymaster loop: {e}")
        else:
            # retry 3 time to avoid broken pipe for operative
            for i in range(3):
                started_at = time.time()
                response = await self.dendrite(
                    axons=axon,
                    synapse=synapse,
                    deserialize=True,
                    timeout=30,
                )
                if response is not None:
                    break

        # 2.2 Check response
        if response is not None:
            bt.logging.info(
                f"⏫ Received response from miner {to_uid} in {time.time() - start_at:.2f}s"
            )
        else:
            game_state.gameWinner = (
                TeamColor.RED
                if game_state.currentTeam == TeamColor.BLUE
                else TeamColor.BLUE
            )
            resetAnimations(self, game_state.cards)
            end_reason = "no_response"
            bt.logging.info(
                f"💀 No response received! Game over. Winner: {game_state.gameWinner}"
            )
            game_state.chatHistory.append(
                ChatMessage(
                    sender=your_role,
                    message=f"❌ No response received! Game over.",
                    team=game_state.currentTeam,
                    reasoning="No response received.",
                )
            )
            # End the game and remove from gameboard after 10 seconds
            await update_room(self, game_state, roomId)
            break

        # 2.3 Turn/Role-based game logic
        if game_state.currentRole == Role.SPYMASTER:
            # Get the clue and number from the response
            clue = response.clue_text
            number = response.number
            reasoning = response.reasoning

            async def check_valid_clue(clue, number, board_words):
                if clue is None or number is None:
                    return False, "Clue or number is None"
                # Check if the clue is valid using opponent spymaster
                if game_state.currentTeam == TeamColor.RED:
                    opp_uid = blue_team["spymaster"]
                else:
                    opp_uid = red_team["spymaster"]
                opp_synapse = GameSynapse(
                    your_team=(
                        TeamColor.RED
                        if game_state.currentTeam == TeamColor.BLUE
                        else TeamColor.BLUE
                    ),
                    your_role="clue_validator",
                    remaining_red=remaining_red,
                    remaining_blue=remaining_blue,
                    your_clue=clue,
                    your_number=number,
                    cards=cards,
                )

                bt.logging.info(f"⏬ Sending clue check query to miner {opp_uid}")
                opp_response: GameSynapseOutput = await self.dendrite(
                    axons=self.metagraph.axons[opp_uid],
                    synapse=opp_synapse,
                    deserialize=True,
                    timeout=30,
                )
                if not opp_response or opp_response.clue_validity:
                    bt.logging.info(f"✅ Clue '{clue}' with number {number} is valid")
                    return True, "Clue is valid"

                bt.logging.warning(
                    f"Miner {opp_uid} reported that Clue '{clue}' with number {number} is invalid, reason: {opp_response.reasoning}"
                )
                bt.logging.info("Validator is checking clue validity with GPT-5...")

                # Secondary rule check using GPT-5 (by validator)
                messages = []
                messages.append({"role": "system", "content": ruleSysPrompt})
                messages.append(
                    {
                        "role": "user",
                        "content": f"Clue: {clue}, Number: {number}, Board Words: {board_words}",
                    }
                )

                try:
                    result = client.responses.create(
                        model="gpt-5",
                        input=messages,
                        reasoning={"effort": "medium"},
                    )
                    result_json = json.loads(result.output_text)
                    bt.logging.info(f"Rule System Response: {result_json}")
                    if result_json.get("valid") is False:
                        return False, result_json.get("reasoning", "Invalid clue")
                except Exception as e:  # noqa: BLE001
                    bt.logging.warning(f"Rule validation error: {e}")

                bt.logging.info(f"✅ Clue '{clue}' with number {number} is valid")
                return True, "Clue is valid"

            bt.logging.info(f"Received clue from miner {to_uid}")
            bt.logging.info(f"Clue: {clue}, Number: {number}")
            bt.logging.info(f"Reasoning: {reasoning}")

            board_words = [
                card.word for card in game_state.cards if not card.is_revealed
            ]

            game_state.currentClue = Clue(clueText=clue, number=number)
            game_state.currentClue.clueText = clue
            game_state.currentClue.number = number

            valid, reason = await check_valid_clue(clue, number, board_words)

            if not valid:
                bt.logging.info(
                    f"❌ Invalid clue '{clue}' provided by miner {to_uid} for board words {board_words}. Reason: {reason}"
                )
                # If the clue is invalid, the other team wins
                game_state.gameWinner = (
                    TeamColor.RED
                    if game_state.currentTeam == TeamColor.BLUE
                    else TeamColor.BLUE
                )
                resetAnimations(self, game_state.cards)
                end_reason = "invalid_clue"
                bt.logging.info(
                    f"💀 Invalid clue! Game over. Winner: {game_state.gameWinner}"
                )
                game_state.chatHistory.append(
                    ChatMessage(
                        sender=Role.SPYMASTER,
                        message=f"Gave invalid clue '{clue}' with number {number}. Reason: {reason}",
                        team=game_state.currentTeam,
                        clueText="null" if clue is None else clue,
                        number=-1 if number is None else number,
                        reasoning=reasoning,
                    )
                )

                await update_room(self, game_state, roomId)
                break

            game_state.chatHistory.append(
                ChatMessage(
                    sender=Role.SPYMASTER,
                    message=f"Gave clue '{clue}' with number {number}",
                    team=game_state.currentTeam,
                    clueText=clue,
                    number=number,
                    reasoning=reasoning,
                )
            )

        elif game_state.currentRole == Role.OPERATIVE:
            # Get the guessed cards from the response
            guesses = response.guesses
            reasoning = response.reasoning
            bt.logging.info(f"Guessed cards: {guesses}")
            bt.logging.info(f"Reasoning: {reasoning}")
            if guesses is None:
                bt.logging.info(
                    f"❌ Invalid guesses '{guesses}' provided by miner {to_uid}."
                )
                # If the guesses is invalid, the other team wins
                game_state.gameWinner = (
                    TeamColor.RED
                    if game_state.currentTeam == TeamColor.BLUE
                    else TeamColor.BLUE
                )
                resetAnimations(self, game_state.cards)
                end_reason = "no_response"
                bt.logging.info(
                    f"❌ No guesses received! Game over. Winner: {game_state.gameWinner}"
                )
                game_state.chatHistory.append(
                    ChatMessage(
                        sender=Role.OPERATIVE,
                        message=f"❌ No guesses provided.",
                        team=game_state.currentTeam,
                        guesses=[],
                        reasoning="No guesses provided.",
                    )
                )
                await update_room(self, game_state, roomId)
                break

            # Update the game state
            choose_assasin = False
            for guess in guesses:
                card = next((c for c in game_state.cards if c.word == guess), None)
                if card is None or card.is_revealed:
                    bt.logging.debug(f"Invalid guess: {guess}")
                    continue
                card.is_revealed = True
                card.was_recently_revealed = True
                if card.color == "red":
                    game_state.remainingRed -= 1
                elif card.color == "blue":
                    game_state.remainingBlue -= 1
                if game_state.remainingRed == 0:
                    game_state.gameWinner = TeamColor.RED
                    resetAnimations(self, game_state.cards)
                    end_reason = "red_all_cards"
                    bt.logging.info(
                        f"🎉 All red cards found! Winner: {game_state.gameWinner}"
                    )
                    game_state.chatHistory.append(
                        ChatMessage(
                            sender=Role.OPERATIVE,
                            message=f"🎉 All red cards found! Winner: {game_state.gameWinner.value.capitalize()} Team",
                            team=game_state.currentTeam,
                            guesses=guesses,
                            reasoning=reasoning,
                        )
                    )
                    await update_room(self, game_state, roomId)
                    break
                elif game_state.remainingBlue == 0:
                    game_state.gameWinner = TeamColor.BLUE
                    resetAnimations(self, game_state.cards)
                    end_reason = "blue_all_cards"
                    bt.logging.info(
                        f"🎉 All blue cards found! Winner: {game_state.gameWinner}"
                    )
                    game_state.chatHistory.append(
                        ChatMessage(
                            sender=Role.OPERATIVE,
                            message=f"🎉 All blue cards found! Winner: {game_state.gameWinner.value.capitalize()} Team",
                            team=game_state.currentTeam,
                            guesses=guesses,
                            reasoning=reasoning,
                        )
                    )
                    await update_room(self, game_state, roomId)
                    break
                if card.color == "assassin":
                    choose_assasin = True
                    game_state.gameWinner = (
                        TeamColor.RED
                        if game_state.currentTeam == TeamColor.BLUE
                        else TeamColor.BLUE
                    )
                    resetAnimations(self, game_state.cards)
                    end_reason = "assassin"
                    bt.logging.info(
                        f"💀 Assassin card '{card.word}' found! Game over. Winner: {game_state.gameWinner}"
                    )
                    game_state.chatHistory.append(
                        ChatMessage(
                            sender=Role.OPERATIVE,
                            message=f"💀 Assassin card '{card.word}' found! Game over. Winner: {game_state.gameWinner.value.capitalize()} Team",
                            team=game_state.currentTeam,
                            guesses=guesses,
                            reasoning=reasoning,
                        )
                    )
                    await update_room(self, game_state, roomId)
                    break
                if card.color != game_state.currentTeam.value:
                    # If the card is not of our team color, we break
                    # This is to ensure that the operative only guesses cards of their team color
                    bt.logging.warning(
                        f"❌ Card {card.word} is not of team color {game_state.currentTeam.value}, breaking."
                    )
                    break
            if choose_assasin or game_state.gameWinner is not None:
                break
            game_state.currentGuesses = guesses
            game_state.chatHistory.append(
                ChatMessage(
                    sender=Role.OPERATIVE,
                    message=f"Guessed cards: {', '.join(guesses)}",
                    team=game_state.currentTeam,
                    reasoning=reasoning,
                    guesses=guesses,
                )
            )

        # change the role
        game_state.previousRole = game_state.currentRole
        game_state.previousTeam = game_state.currentTeam

        if game_state.currentRole == Role.SPYMASTER:
            game_state.currentRole = Role.OPERATIVE
        else:
            game_state.currentRole = Role.SPYMASTER
            # change the team after operative moved
            if game_state.currentTeam == TeamColor.RED:
                game_state.currentTeam = TeamColor.BLUE
            else:
                game_state.currentTeam = TeamColor.RED
        game_step += 1

        await update_room(self, game_state, roomId)

    # Game over
    ended_at = time.time()
    winner_value = (
        game_state.gameWinner.value if game_state.gameWinner is not None else None
    )
    if winner_value and end_reason != "no_response":
        # Increase selection count
        for hotkey in selected_hotkeys:
            try:
                uid = self.metagraph.hotkeys.index(hotkey)
                self.score_store.increment_selection_count(hotkey, uid)
                bt.logging.info(f"Incremented selection count for {uid}")
            except Exception as err:  # noqa: BLE001
                bt.logging.error(
                    f"Failed to increment selection count for {hotkey}: {err}"
                )

    # Adjust the scores based on responses from miners.
    rewards = get_rewards(
        self,
        winner=game_state.gameWinner.value if game_state.gameWinner else None,
        red_team=red_team,
        blue_team=blue_team,
        end_reason=end_reason,
        current_team=game_state.currentTeam,
        current_role=game_state.currentRole,
    )

    bt.logging.info(f"Scored responses: {rewards}")

    rewards_list = rewards.tolist() if hasattr(rewards, "tolist") else list(rewards)

    def _score_at(index: int) -> float:
        return float(rewards_list[index]) if index < len(rewards_list) else 0.0

    try:
        self.score_store.record_game(
            room_id=roomId,
            rs=rs_hotkey,
            ro=ro_hotkey,
            bs=bs_hotkey,
            bo=bo_hotkey,
            winner=winner_value,
            started_at=started_at,
            ended_at=ended_at,
            score_rs=_score_at(0),
            score_ro=_score_at(1),
            score_bs=_score_at(2),
            score_bo=_score_at(3),
            reason=end_reason,
        )
        synced = await self.score_store.sync_pending()
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Failed to persist game score {roomId}: {err}")

    time.sleep(1)
