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
from game.protocol import CodenamesChatMessage, CodenamesSynapse, CodenamesSynapseOutput
from game.utils.opSysPrompt import opSysPrompt
from game.utils.spySysPrompt import spySysPrompt
from game.utils.ruleSysPrompt import ruleSysPrompt
from game.validator.reward import get_rewards
from game.utils.uids import choose_players
import random
import typing
from game.utils.game import Competition, TParticipant
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

client = OpenAI(api_key=os.environ.get("OPENAI_KEY"))


def organize_team(self, competition, uids):
    """
    Organize the team with 2 miners randomly

    Args:
        uids (list[int]): The list of miner uids

    Returns:
        tuple[dict[str, int], dict[str, int]]: The red team and the blue team
    """
    if competition == Competition.CLUE_COMPETITION:
        team1 = {"spymaster": uids[0], "operative": self.uid}
        team2 = {"spymaster": uids[1], "operative": self.uid}
    else:
        team1 = {"spymaster": self.uid, "operative": uids[0]}
        team2 = {"spymaster": self.uid, "operative": uids[1]}
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
                "competition": game_state.competition.value,
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
                    try:
                        room_id = json.loads(response_text)["data"]["id"]
                        bt.logging.info(
                            f"Room created successfully. Room ID: {room_id}"
                        )
                        bt.logging.debug(f"Room creation response: {response_text}")
                        return room_id
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
                "competition": game_state.competition.value,
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


async def get_llm_response(synapse: CodenamesSynapse) -> CodenamesSynapseOutput:

    async def get_gpt5_response(messages, effort="minimal"):
        try:
            result = client.responses.create(
                model="gpt-5",
                input=messages,
                reasoning={"effort": effort},  # Optional: control reasoning effort
            )
            return result.output_text
        except Exception as e:
            bt.logging.error(f"Error fetching response from GPT-5: {e}")
            bt.logging.debug(
                f"Messages sent to GPT-5: {json.dumps(messages, indent=2)}"
            )
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
        clue_block = f"Your Clue: {synapse.your_clue}\nNumber: {synapse.your_number}"
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

    retry = 0
    while retry < 2:
        response_str = await get_gpt5_response(
            messages
        )  # , effort = "medium" if synapse.your_role == "spymaster" else "minimal")
        if response_str:
            break
        retry += 1
    # bt.logging.debug(f"💬 LLM Response: {response_str}")
    response_dict = json.loads(response_str)
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

    output = CodenamesSynapseOutput(
        clue_text=clue, number=number, reasoning=reasoning, guesses=guesses
    )
    return output


async def forward(self):
    """
    This method is invoked by the validator at each time step.

    Its main function is to query the network and evaluate the responses.

    Parameters:
        self (bittensor.neuron.Neuron): The neuron instance containing all necessary state information for the validator.

    """
    competition = self.current_competition

    # Sync any pending score records to the database
    await self.score_store.sync_scores_all()

    miner_uids, observer_hotkeys = await choose_players(
        self, competition=competition, k=2
    )
    # Exception handling when number of miners less than 2
    if len(miner_uids) < 2:
        return

    (red_team, blue_team) = organize_team(self, competition, miner_uids)
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

    invalid_respond_counts = {
        miner_uids[0]: 0,
        miner_uids[1]: 0,
    }

    participants: typing.List[TParticipant] = []
    for team in [red_team, blue_team]:
        participants.append(
            TParticipant(
                name=(
                    ("Miner " + str(team["spymaster"]))
                    if team["spymaster"] != self.uid
                    else "Validator"
                ),
                hotkey=self.metagraph.axons[team["spymaster"]].hotkey,
                team=TeamColor.RED if team == red_team else TeamColor.BLUE,
                role=Role.SPYMASTER,
            )
        )
        participants.append(
            TParticipant(
                name=(
                    ("Miner " + str(team["operative"]))
                    if team["operative"] != self.uid
                    else "Validator"
                ),
                hotkey=self.metagraph.axons[team["operative"]].hotkey,
                team=TeamColor.RED if team == red_team else TeamColor.BLUE,
                role=Role.OPERATIVE,
            )
        )
    for hotkey in observer_hotkeys:
        uid = self.metagraph.hotkeys.index(hotkey)
        participants.append(
            TParticipant(
                name=("Miner " + str(uid)),
                hotkey=hotkey,
                team=TeamColor.OBSERVER,
                role=Role.OBSERVER,
            )
        )
    observer_uids = [
        self.metagraph.hotkeys.index(hotkey) for hotkey in observer_hotkeys
    ]
    if observer_uids:
        bt.logging.info(f"\033[33mObservers: {observer_uids}\033[0m")
    # * Initialize game
    game_step = 0
    started_at = time.time()
    game_state = GameState(competition=competition, participants=participants)
    end_reason = "completed"

    # Create new room via API call
    # ===============🤞ROOM CREATE===================
    roomId = await create_room(self, game_state)
    if roomId is None:
        bt.logging.error("Failed to create room, exiting.")
        time.sleep(10)
        return

    # ===============GAME LOOP=======================
    bt.logging.info("╔══════════════════════════════════════════════════════════════╗")
    bt.logging.info("║                     🚀  GAME STARTING  🚀                    ║")
    bt.logging.info(
        f"║                Competition: {competition.value}                 ║"
    )
    bt.logging.info(
        "╚══════════════════════════════════════════════════════════════╝\n"
    )
    while game_state.gameWinner is None:
        bt.logging.info("=" * 50)
        bt.logging.info(f"Game step {game_step + 1}")

        is_miner_turn = (
            game_state.competition == Competition.CLUE_COMPETITION
            and game_state.currentRole == Role.SPYMASTER
            or game_state.competition == Competition.GUESS_COMPETITION
            and game_state.currentRole == Role.OPERATIVE
        )

        should_skip_turn = False

        bt.logging.info(
            f"Current Role: {game_state.currentTeam.value} {game_state.currentRole.value} ({'Miner' if is_miner_turn else 'Validator'})"
        )

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

        synapse = CodenamesSynapse(
            your_team=your_team,
            your_role=your_role,
            remaining_red=remaining_red,
            remaining_blue=remaining_blue,
            your_clue=your_clue,
            your_number=your_number,
            cards=cards,
            chat_history=[
                CodenamesChatMessage(
                    team=chat.team.value,
                    sender=chat.sender.value,
                    message=chat.message,
                    clueText=chat.clueText,
                    number=chat.number,
                    guesses=chat.guesses,
                )
                for chat in game_state.chatHistory
            ],
        )

        # 2. Main Game Logic
        started_at = time.time()
        # 2.1 Query the participant
        response = None

        if is_miner_turn:
            axon = self.metagraph.axons[to_uid]
            bt.logging.info(
                f"⏬ Sending game query to miner {to_uid}, ({axon.ip}:{axon.port}, {axon.hotkey})"
            )
            for i in range(3):
                sent_at = time.time()
                response = await self.dendrite(
                    axons=axon,
                    synapse=synapse,
                    deserialize=True,
                    timeout=30,
                )
                if response or (time.time() - sent_at) > 3:
                    break
                bt.logging.warning(f"⏳ No response from miner {to_uid} ({i+1}/3)")
            bt.logging.info(
                f"⏫ Response from miner {to_uid} took {time.time() - started_at:.2f}s"
            )
        else:
            bt.logging.info(f"⏬ Sending game query to LLM for {your_role}")
            response = await get_llm_response(synapse)
            if response is None:
                bt.logging.error("Failed to get response from LLM, exiting.")
                time.sleep(10)
                return

        # 2.2 Check response
        if response is None:
            should_skip_turn = True
            invalid_respond_counts[to_uid] += 1
            bt.logging.warning(
                f"No response from miner {to_uid} ({invalid_respond_counts[to_uid]}/2)"
            )
            if invalid_respond_counts[to_uid] < 2:
                # Switch turn to the other team
                game_state.chatHistory.append(
                    ChatMessage(
                        sender=your_role,
                        message="⚠️ No response received! Switching turn to the other team.",
                        team=game_state.currentTeam,
                        reasoning="No response received.",
                    )
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
                        message=f"💀 No response received! Game over.",
                        team=game_state.currentTeam,
                        reasoning="No response received.",
                    )
                )
                # End the game and remove from gameboard after 10 seconds
                await update_room(self, game_state, roomId)
                break

        # 2.3 Turn/Role-based game logic
        elif game_state.currentRole == Role.SPYMASTER:
            # Get the clue and number from the response
            clue = response.clue_text
            number = response.number
            reasoning = response.reasoning

            async def check_valid_clue(clue, number, board_words):
                if clue is None or number is None:
                    return False, "Clue or number is None"

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
                    if result_json.get("valid") is False:
                        bt.logging.info(f"Clue check: {result_json}")
                        return False, result_json.get("reasoning", "Invalid clue")
                except Exception as e:  # noqa: BLE001
                    bt.logging.warning(f"Rule validation error: {e}")

                bt.logging.info(f"✅ Clue '{clue}' with number {number} is valid")
                return True, "Clue is valid"

            bt.logging.info(f"Clue: {clue}, Number: {number}")
            # bt.logging.info(f"Reasoning: {reasoning}")

            board_words = [
                card.word for card in game_state.cards if not card.is_revealed
            ]

            game_state.currentClue = Clue(clueText=clue, number=number)
            game_state.currentClue.clueText = clue
            game_state.currentClue.number = number

            is_valid_clue, reason = (
                (await check_valid_clue(clue, number, board_words))
                if is_miner_turn
                else (True, "validator clue")
            )

            if not is_valid_clue:
                should_skip_turn = True
                invalid_respond_counts[to_uid] += 1
                if invalid_respond_counts[to_uid] < 2:
                    bt.logging.info(
                        f"❌ Invalid clue '{clue}' provided by miner {to_uid} for board words {board_words}. Reason: {reason}"
                    )
                    bt.logging.info(f"Skipping turn to the other team.")
                    game_state.chatHistory.append(
                        ChatMessage(
                            sender=Role.SPYMASTER,
                            message=f"Gave invalid clue '{clue}' with number {number}. Reason: {reason} Skipping turn.",
                            team=game_state.currentTeam,
                            clueText="null" if clue is None else clue,
                            number=-1 if number is None else number,
                            reasoning=reasoning,
                        )
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
                        f"💀 Invalid clue provided! Game over. Winner: {game_state.gameWinner}"
                    )
                    game_state.chatHistory.append(
                        ChatMessage(
                            sender=your_role,
                            message=f"💀 Invalid clue provided! ({reason}) Game over.",
                            team=game_state.currentTeam,
                            reasoning="Invalid clue provided.",
                        )
                    )
                    # End the game and remove from gameboard after 10 seconds
                    await update_room(self, game_state, roomId)
                    break

            else:
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
            # bt.logging.info(f"Reasoning: {reasoning}")
            if guesses is None:
                invalid_respond_counts[to_uid] += 1
                bt.logging.info(f"⚠️ No guesses '{guesses}' provided by miner {to_uid}.")
                if invalid_respond_counts[to_uid] < 2:
                    # Switch turn to the other team
                    game_state.chatHistory.append(
                        ChatMessage(
                            sender=Role.OPERATIVE,
                            message="⚠️ No guesses provided! Switching turn to the other team.",
                            team=game_state.currentTeam,
                            reasoning="No guesses provided.",
                        )
                    )
                else:
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
            else:
                # Update the game state
                choose_assasin = False

                if len(guesses) > your_number + 1:
                    bt.logging.info(
                        f"⚠️ Too many guesses '{guesses}' provided by miner {to_uid} (allowed: {your_number + 1})."
                    )
                    guesses = guesses[: your_number + 1]
                    bt.logging.info(f"Truncated guesses to: {guesses}")
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
                                message=f"🎉 All red cards found!",
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
                                message=f"🎉 All blue cards found!",
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
                                message=f"💀 Assassin card '{card.word}' found! Game over.",
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

        # change the role
        game_state.previousRole = game_state.currentRole
        game_state.previousTeam = game_state.currentTeam

        if game_state.currentRole == Role.SPYMASTER:
            if should_skip_turn:
                if game_state.currentTeam == TeamColor.RED:
                    game_state.currentTeam = TeamColor.BLUE
                else:
                    game_state.currentTeam = TeamColor.RED
            else:
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
    bt.logging.info("════════════════════════════════════════════════════════════════")
    bt.logging.info(
        f"               🎉 GAME OVER 🏆 WINNER: {game_state.gameWinner.value.upper()} TEAM                "
    )
    bt.logging.info(
        "════════════════════════════════════════════════════════════════\n"
    )
    # Adjust the scores based on responses from miners.
    rewards = get_rewards(
        self,
        competition=competition,
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
        await self.score_store.upload_score(
            room_id=roomId,
            competition=competition.value,
            rs=rs_hotkey,
            ro=ro_hotkey,
            bs=bs_hotkey,
            bo=bo_hotkey,
            score_rs=_score_at(0),
            score_ro=_score_at(1),
            score_bs=_score_at(2),
            score_bo=_score_at(3),
            reason=end_reason,
        )
    except Exception as err:  # noqa: BLE001
        bt.logging.error(f"Failed to persist game score {roomId}: {err}")

    time.sleep(1)
