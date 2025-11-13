# define card type
import hashlib
import random
import time
from enum import Enum
from typing import NamedTuple

from pydantic import BaseModel

with open("game/utils/wordlist-eng.txt") as f:
    words = f.readlines()


class Competition(Enum):
    CLUE_COMPETITION = "clue_competition"
    GUESS_COMPETITION = "guess_competition"

    @property
    def mechid(self) -> int:
        if self == Competition.CLUE_COMPETITION:
            return 0
        elif self == Competition.GUESS_COMPETITION:
            return 1
        return None


class TeamColor(Enum):
    RED = "red"
    BLUE = "blue"
    OBSERVER = "neutral"


class CardColor(Enum):
    RED = "red"
    BLUE = "blue"
    BYSTANDER = "bystander"
    ASSASSIN = "assassin"


class CardType(BaseModel):
    word: str
    color: str | None
    is_revealed: bool
    was_recently_revealed: bool


class Role(Enum):
    SPYMASTER = "spymaster"
    OPERATIVE = "operative"
    OBSERVER = "observer"


class ChatMessage(NamedTuple):
    sender: Role
    message: str
    team: TeamColor
    clueText: str | None = None
    number: int | None = None
    guesses: list[str] | None = None
    reasoning: str | None = None


class Clue(BaseModel):
    clueText: str | None
    number: int | None


class TParticipant(BaseModel):
    name: str
    hotkey: str
    team: TeamColor
    role: Role


class GameState:
    id: str = None
    competition: Competition
    cards: list[CardType]
    chatHistory: list[ChatMessage]
    currentTeam: TeamColor
    currentRole: Role
    previousTeam: TeamColor | None = None
    previousRole: Role | None = None
    remainingRed: int
    remainingBlue: int
    currentClue: Clue = None
    currentGuesses: list[str] = None
    gameWinner: TeamColor = None
    participants: list[TParticipant] = []

    def __init__(self, competition, participants, seed: str | int | None = None):
        self.competition = competition
        self.participants = participants
        seed_source = str(time.time_ns())
        # Seed a dedicated RNG per game so the board stays consistent for the game lifetime.
        self.seed = hashlib.sha256(seed_source.encode("utf-8")).hexdigest()
        rng = random.Random(int(self.seed, 16))

        self.words = rng.sample(words, 25)
        rng.shuffle(self.words)
        self.cards = [
            CardType(
                word=word.strip(),
                color=color,
                is_revealed=False,
                was_recently_revealed=False,
            )
            for word, color in zip(
                self.words,
                [CardColor.RED] * 9
                + [CardColor.BLUE] * 8
                + [CardColor.BYSTANDER] * 7
                + [CardColor.ASSASSIN],
            )
        ]
        rng.shuffle(self.cards)
        self.chatHistory = []
        self.currentTeam = TeamColor.RED
        self.currentRole = Role.SPYMASTER
        self.remainingRed = 9
        self.remainingBlue = 8
