import typing
import bittensor as bt
from pydantic import BaseModel
import random
import asyncio

with open("game/data/words/default.txt") as f:
    words = f.readlines()
# select 25 random words
words = random.sample(words, 25)


class CardType(BaseModel):
    word: str
    color: str | None
    is_revealed: bool
    was_recently_revealed: bool


class GameSynapseOutput(BaseModel):
    clue_text: typing.Optional[str] = None
    number: typing.Optional[int] = None
    guesses: typing.Optional[typing.List[str]] = None
    reasoning: typing.Optional[str] = None


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


async def forward(uid: int, synapse: GameSynapse, dendrite, metagraph):
    print(synapse)
    responses = await dendrite(
        # Send the query to selected miner axons in the network.
        axons=[metagraph.axons[uid]],
        # Construct a query.
        synapse=synapse,
        # All responses have the deserialize function called on them before returning.
        # You are encouraged to define your own deserialization function.
        deserialize=True,
        timeout=10,
    )
    return responses[0] if responses else None


async def main():
    # Example usage of GameSynapse
    subtensor = bt.subtensor(network="test")
    metagraph = subtensor.metagraph(netuid=335)
    wallet = bt.wallet(name="brainplay-test-owner", hotkey="default")
    dendrite = bt.dendrite(wallet=wallet)
    game_synapse = GameSynapse(
        your_team="red",
        your_role="spymaster",
        remaining_red=9,
        remaining_blue=8,
        cards=[
            CardType(
                word=word.strip(),
                color=color,
                is_revealed=False,
                was_recently_revealed=False,
            )
            for word, color in zip(
                words, ["red"] * 9 + ["blue"] * 8 + ["bystander"] * 7 + ["assassin"]
            )
        ],
        your_clue=None,
        your_number=None,
    )
    response = await forward(2, game_synapse, dendrite, metagraph)
    print(response)
    await dendrite.aclose_session()


if __name__ == "__main__":
    asyncio.run(main())
