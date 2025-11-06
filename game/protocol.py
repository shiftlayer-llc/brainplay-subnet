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

import typing
import bittensor as bt
from game.utils.game import CardType
from pydantic import BaseModel, Field
from game import __version__


class Ping(bt.Synapse):
    """Lightweight ping used by validators to discover available miners."""

    version: str = __version__
    is_available: bool = False


class GameChatMessage(BaseModel):
    team: str
    sender: str
    message: str
    clueText: str | None = None
    number: int | None = None
    guesses: list[str] | None = None


class GameSynapseOutput(BaseModel):
    clue_text: typing.Optional[str] = None
    number: typing.Optional[int] = None
    guesses: typing.Optional[typing.List[str]] = None
    reasoning: typing.Optional[str] = None
    clue_validity: typing.Optional[bool] = None


class GameSynapse(bt.Synapse):
    """
    The GameSynapse class is a synapse that represents the status of the game.
    Attributes:
    - your_team: TeamColor
    - your_role: Role
    - remaining_red: int
    - remaining_blue: int
    - your_clue: Optional[str]
    - your_number: Optional[int]
    - cards: List[CardType]
    - output: GameSynapseOutput
    """

    your_team: str = None
    your_role: str = None
    remaining_red: int = 0
    remaining_blue: int = 0
    your_clue: typing.Optional[str] = None
    your_number: typing.Optional[int] = None
    cards: typing.List[CardType] = None
    chat_history: typing.List[GameChatMessage] = None
    output: GameSynapseOutput | None = None

    def deserialize(self) -> GameSynapseOutput | None:
        """
        Deserialize the output. This method retrieves the response from
        the miner in the form of output, deserializes it and returns it
        as the output of the dendrite.query() call.

        Returns:
        - GameSynapseOutput: The deserialized response.

        Example:
        Assuming a GameSynapse instance has an output value:
        >>> synapse_instance = GameSynapse(your_team=TeamColor.RED, your_role=Role.SPYMASTER, remaining_red=9, remaining_blue=8, cards=[])
        >>> synapse_instance.output = GameSynapseOutput(clue_text="example", number=1)
        >>> synapse_instance.deserialize()
        GameSynapseOutput(clue_text="example", number=1)
        """
        return self.output
