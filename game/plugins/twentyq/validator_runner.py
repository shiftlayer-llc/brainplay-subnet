"""TwentyQ validator runner implementation."""

from __future__ import annotations

import asyncio
import csv
from collections import deque
from pathlib import Path
import random
import re
import time
from uuid import uuid4

import bittensor as bt
import httpx
from openai import OpenAI

from game.common.epistula import generate_header
from game.common.misc import extract_json
from game.core.commitment_reader import read_endpoints
from game.core.interfaces import AttemptResult, SessionResult
from game.plugins.codenames.game_types import Competition
from game.plugins.twentyq.backend_mapper import (
    make_create_payload,
    make_score_payload,
    make_update_payload,
)
from game.plugins.twentyq.models import TwentyQAttemptState, TwentyQRoomState
from game.plugins.twentyq.protocol import (
    TwentyQMinerOutput,
    TwentyQPayload,
    TwentyQTurn,
)
from game.plugins.twentyq.scoring import score_twentyq_attempt
from game.providers.backend_client import BackendClient
from game.providers.judge.chutes_ai import ChutesAIJudge
from game.providers.targon_client import check_endpoints, get_metadata

DATASET_PATH = (
    Path(__file__).resolve().parent / "data" / "20q_dataset_30000_72properties.csv"
)


class TwentyQValidatorRunner:
    def __init__(self, validator) -> None:
        self.validator = validator
        self.max_questions = 20
        self.max_bonus_questions = 10
        self.max_total_turns = self.max_questions + self.max_bonus_questions
        self.max_create_room_attempts = 5
        self.active_game_retry_sleep_sec = 60
        self.word_history_size = 64
        self.judge = ChutesAIJudge()
        self.backend = BackendClient(
            base_url=self.validator.backend_base,
            signer=self.validator.build_signed_headers,
            timeout_sec=10,
        )
        if not hasattr(self.validator, "_twentyq_recent_words"):
            self.validator._twentyq_recent_words = deque(maxlen=self.word_history_size)
        self._recent_words: deque[str] = self.validator._twentyq_recent_words
        if not self.judge.api_key or not self.judge.base_url:
            bt.logging.warning(
                "[20Q] Judge API config missing (CHUTES_API_KEY/CHUTES_BASE_URL); "
                "using local heuristic answers."
            )
        else:
            bt.logging.info(
                f"[20Q] Judge configured with model={self.judge.model} "
                f"base_url={self.judge.base_url}"
            )

    async def run_round(self) -> SessionResult:
        started_at = time.time()
        try:
            await asyncio.wait_for(
                self.validator.score_store.sync_scores_all(), timeout=600
            )
        except asyncio.TimeoutError:
            bt.logging.warning(
                "Score history sync timed out after 600s; continuing round."
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.warning(f"Score history sync failed before 20Q round: {err}")

        selected_uids, metadata = await self._discover_participants()
        if not selected_uids:
            now = time.time()
            return SessionResult(
                session_id=f"twentyq-{uuid4().hex}",
                game_code="twentyq",
                competition_code="twentyq",
                status="skipped",
                started_at=started_at,
                ended_at=now,
                attempts=(),
                metadata={"reason": "no_available_miners"},
            )

        secret_word = await self._pick_secret_word()
        room = TwentyQRoomState(
            room_id=f"twentyq-{uuid4().hex}",
            validator_key=self.validator.wallet.hotkey.ss58_address,
            word=secret_word,
            started_at=int(started_at),
            participants=[
                TwentyQAttemptState(
                    uid=uid,
                    hotkey=self.validator.metagraph.hotkeys[uid],
                    endpoint=metadata[uid]["endpoint"],
                    reasoning_effort=metadata[uid].get("reasoning", "none"),
                )
                for uid in selected_uids
            ],
        )

        created = await self._create_room(room)
        if not created:
            now = time.time()
            bt.logging.warning(
                f"[20Q] Game creation failed; skipping round for word={room.word!r}"
            )
            return SessionResult(
                session_id=room.room_id,
                game_code="twentyq",
                competition_code="twentyq",
                status="skipped",
                started_at=started_at,
                ended_at=now,
                attempts=(),
                metadata={"reason": "create_room_failed", "word": room.word},
            )
        bt.logging.info(
            f"[20Q] Game created: room_id={room.room_id} "
            f"participant_uids={selected_uids} word={room.word}"
        )

        concurrency = max(
            1, min(16, int(self.validator.config.neuron.num_concurrent_forwards) * 4)
        )
        semaphore = asyncio.Semaphore(concurrency)

        async def _wrapped_attempt(p: TwentyQAttemptState) -> AttemptResult:
            async with semaphore:
                return await self._run_attempt(room, p)

        attempts = await asyncio.gather(
            *[_wrapped_attempt(p) for p in room.participants],
            return_exceptions=False,
        )

        room.status = "completed"
        room.ended_at = int(time.time())
        room.question_count = max(
            (p.question_count for p in room.participants), default=0
        )
        await self._update_room(room)

        await self._sync_scores(room)

        ended_at = time.time()
        return SessionResult(
            session_id=room.room_id,
            game_code="twentyq",
            competition_code="twentyq",
            status=room.status,
            started_at=started_at,
            ended_at=ended_at,
            attempts=tuple(attempts),
            metadata={
                "word": secret_word,
                "participants": len(room.participants),
            },
        )

    async def _discover_participants(self) -> tuple[list[int], dict[int, dict]]:
        exclude_set = {
            int(uid)
            for uid in self.validator.metagraph.uids
            if self.validator.metagraph.S[uid]
            < self.validator.config.neuron.minimum_stake_requirement
            or self.validator.metagraph.S[uid]
            > self.validator.config.blacklist.minimum_stake_requirement
        }
        uids_to_ping = [
            int(uid)
            for uid in self.validator.metagraph.uids
            if int(uid) not in exclude_set
        ]
        bt.logging.info(f"[20Q] Uids to ping: {uids_to_ping}")

        endpoints = read_endpoints(self.validator, Competition.TWENTYQ, uids_to_ping)
        if not endpoints:
            bt.logging.warning("[20Q] No committed endpoints found.")
            return [], {}
        bt.logging.info(
            f"[20Q] Uids with committed endpoints: {sorted(endpoints.keys())}"
        )

        responsive_uids = await check_endpoints(self.validator, endpoints, timeout=30)
        if not responsive_uids:
            bt.logging.warning("[20Q] No responsive miners found.")
            return [], {}
        bt.logging.info(f"[20Q] Available uids: {sorted(responsive_uids)}")

        metadata = {}
        for uid in responsive_uids:
            reasoning = "none"
            try:
                meta = await get_metadata(
                    self.validator,
                    endpoints[uid],
                    self.validator.metagraph.hotkeys[uid],
                )
                if isinstance(meta, dict):
                    reasoning = str(meta.get("reasoning") or "none")
            except Exception as err:  # noqa: BLE001
                bt.logging.debug(f"[20Q] metadata fetch failed for uid={uid}: {err}")
            metadata[uid] = {"endpoint": endpoints[uid], "reasoning": reasoning}

        return sorted(responsive_uids), metadata

    async def _pick_secret_word(self) -> str:
        word = self._pick_secret_word_from_dataset()
        self._remember_secret_word(word)
        bt.logging.info(f"[20Q] Word selected from dataset: {word}")
        return word

    @staticmethod
    def _normalize_secret_word(word: str) -> str | None:
        candidate = (word or "").strip().lower()
        if not candidate:
            return None
        if " " in candidate:
            return None
        if not re.fullmatch(r"[a-z][a-z-]{1,23}", candidate):
            return None
        too_broad = {
            "thing",
            "object",
            "person",
            "place",
            "animal",
            "plant",
            "food",
            "tool",
            "vehicle",
            "item",
        }
        if candidate in too_broad:
            return None
        ambiguous = {
            "roll",
            "shaft",
            "second",
            "spring",
            "match",
            "bat",
            "bank",
            "crane",
            "seal",
            "mole",
            "date",
            "jam",
            "current",
            "bolt",
            "clip",
            "light",
            "watch",
        }
        if candidate in ambiguous:
            return None
        return candidate

    @staticmethod
    def _normalize_dataset_word(raw_word: str) -> str | None:
        candidate = str(raw_word or "").strip().lower()
        if not candidate:
            return None
        candidate = re.sub(r"_\d+$", "", candidate)
        candidate = candidate.replace("_", "-")
        return TwentyQValidatorRunner._normalize_secret_word(candidate)

    def _load_secret_word_pool(self) -> list[str]:
        cached = getattr(self.validator, "_twentyq_secret_word_pool", None)
        if cached:
            return list(cached)

        words: list[str] = []
        try:
            with DATASET_PATH.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    normalized = self._normalize_dataset_word(row.get("word") or "")
                    if normalized:
                        words.append(normalized)
        except Exception as err:  # noqa: BLE001
            bt.logging.warning(f"[20Q] Failed to load dataset {DATASET_PATH}: {err}")

        deduped_words = list(dict.fromkeys(words))
        self.validator._twentyq_secret_word_pool = deduped_words
        return list(deduped_words)

    def _pick_secret_word_from_dataset(self) -> str:
        dataset_words = self._load_secret_word_pool()
        if dataset_words:
            recent = self._recent_word_set()
            candidates = [word for word in dataset_words if word not in recent]
            pool = candidates or dataset_words
            return random.choice(pool)

        # Safe local fallback if dataset loading fails.
        safe_words = [
            "apple",
            "bicycle",
            "hammer",
            "pillow",
            "dolphin",
            "toaster",
            "mountain",
            "guitar",
            "umbrella",
            "suitcase",
            "airplane",
            "notebook",
        ]
        recent = self._recent_word_set()
        candidates = [word for word in safe_words if word not in recent]
        pool = candidates or safe_words
        fallback_word = random.choice(pool).lower()
        normalized = self._normalize_secret_word(fallback_word)
        if normalized:
            return normalized
        return "apple"

    def _recent_word_set(self) -> set[str]:
        return {str(word).strip().lower() for word in self._recent_words if word}

    def _remember_secret_word(self, word: str) -> None:
        normalized = self._normalize_secret_word(word)
        if normalized:
            self._recent_words.append(normalized)

    async def _create_room(self, room: TwentyQRoomState) -> bool:
        payload = make_create_payload(room)
        for attempt in range(1, self.max_create_room_attempts + 1):
            try:
                response = await self.backend.create_room("twentyq", payload)
            except Exception as err:  # noqa: BLE001
                bt.logging.warning(f"[20Q] Failed to create room on backend: {err}")
                return False

            if not isinstance(response, dict):
                bt.logging.warning(
                    "[20Q] Failed to create room on backend: "
                    f"unexpected response type={type(response).__name__}"
                )
                return False

            room_id = (response.get("data") or {}).get("id") or response.get("id")
            if room_id:
                room.room_id = str(room_id)
                return True

            if (
                self._is_active_game_exists_error(response)
                and attempt < self.max_create_room_attempts
            ):
                bt.logging.info(
                    "[20Q] Active game already exists for this validator; "
                    f"sleeping {self.active_game_retry_sleep_sec}s before retry "
                    f"({attempt}/{self.max_create_room_attempts})."
                )
                await asyncio.sleep(self.active_game_retry_sleep_sec)
                continue

            bt.logging.warning(
                f"[20Q] Failed to create room on backend: response={response}"
            )
            return False
        return False

    @staticmethod
    def _is_active_game_exists_error(response: dict) -> bool:
        text = str(response).lower()
        if "active game" in text and ("exist" in text or "already" in text):
            return True
        status = response.get("statusCode")
        message = str(response.get("message") or "").lower()
        return status == 409 and "active" in message

    async def _update_room(
        self, room: TwentyQRoomState, changed: list[TwentyQAttemptState] | None = None
    ) -> None:
        payload = make_update_payload(room, changed)
        try:
            await self.backend.update_room("twentyq", room.room_id, payload)
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(f"[20Q] Failed to update room {room.room_id}: {err}")

    async def _sync_scores(self, room: TwentyQRoomState) -> None:
        reason = "completed" if room.status == "completed" else "aborted"
        score_payload = make_score_payload(room, reason=reason)
        scores = score_payload["scores"]
        participants = score_payload["participants"]
        try:
            await self.validator.score_store.upload_scores(
                room_id=room.room_id,
                competition="twentyq",
                scores=scores,
                reason=reason,
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.error(
                f"[20Q] Failed to persist/upload scores for {room.room_id}: {err}"
            )
            return
        try:
            await self.backend.score_room(
                "twentyq",
                room.room_id,
                {
                    "reason": reason,
                    "scores": scores,
                    "participants": participants,
                },
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(
                f"[20Q] score endpoint patch failed for {room.room_id}: {err}"
            )

    async def _run_attempt(
        self, room: TwentyQRoomState, participant: TwentyQAttemptState
    ) -> AttemptResult:
        started_at = time.time()
        last_answer = None

        for turn_index in range(1, self.max_total_turns + 1):
            bt.logging.info(
                f"[20Q] Step start: room_id={room.room_id} uid={participant.uid} "
                f"turn={turn_index}/{self.max_total_turns}"
            )
            payload = TwentyQPayload(
                room_id=room.room_id,
                attempt_id=f"{room.room_id}:{participant.uid}",
                turn_index=turn_index,
                max_questions=self.max_questions,
                max_bonus_questions=self.max_bonus_questions,
                history=participant.qa_history,
                last_answer=last_answer,
            )
            response = await self._query_miner_turn(participant, payload)
            if not response.has_action():
                retry_response = await self._query_miner_turn(
                    participant, payload, retry=True
                )
                if retry_response.has_action():
                    response = retry_response
                    bt.logging.info(
                        f"[20Q] uid={participant.uid} turn={turn_index} "
                        "recovered with retry response"
                    )
                else:
                    participant.invalid_turns += 1
                    bt.logging.info(
                        f"[20Q] uid={participant.uid} turn={turn_index} "
                        "empty response (no question/guess)"
                    )
                    if participant.invalid_turns >= 3:
                        participant.is_finished = True
                        participant.finish_reason = "invalid_response"
                        break
                    continue

            guess = (response.guess or "").strip().lower()
            is_correct_guess = bool(guess) and guess == room.word

            question = (response.question or "").strip()
            answer = "unknown"
            if question:
                answer = await self.judge.answer(secret=room.word, question=question)
                participant.question_count += 1
                last_answer = answer
                bt.logging.info(
                    f"[20Q] uid={participant.uid} turn={turn_index} "
                    f"question={question!r} answer={answer}"
                )

            if guess:
                bt.logging.info(
                    f"[20Q] uid={participant.uid} turn={turn_index} "
                    f"guess={guess!r} correct={is_correct_guess}"
                )

            turn = TwentyQTurn(
                turn=turn_index,
                question=question or "<guess>",
                answer=answer,
                guess=response.guess,
                is_correct_guess=is_correct_guess if response.guess else None,
                ts=int(time.time()),
            )
            participant.qa_history.append(turn)
            room.question_count = max(room.question_count, participant.question_count)

            if is_correct_guess:
                participant.solved = True
                participant.solved_at_turn = turn_index
                participant.score = score_twentyq_attempt(
                    solved=True, question_index=turn_index
                )
                participant.is_finished = True
                participant.finish_reason = "solved"
                await self._update_room(room, [participant])
                break

            await self._update_room(room, [participant])

        if not participant.is_finished:
            participant.is_finished = True
            participant.finish_reason = "max_questions_reached"
            participant.score = 0.0
            await self._update_room(room, [participant])

        bt.logging.info(
            f"[20Q] Attempt finished: room_id={room.room_id} uid={participant.uid} "
            f"reason={participant.finish_reason} score={participant.score} "
            f"questions={participant.question_count}"
        )

        ended_at = time.time()
        return AttemptResult(
            miner_hotkey=participant.hotkey,
            status=participant.finish_reason or "completed",
            score=float(participant.score),
            started_at=started_at,
            ended_at=ended_at,
            attempt_id=f"{room.room_id}:{participant.uid}",
            turns_used=len(participant.qa_history),
            metadata={
                "uid": participant.uid,
                "solved": participant.solved,
                "solved_at_turn": participant.solved_at_turn,
                "question_count": participant.question_count,
            },
        )

    async def _query_miner_turn(
        self,
        participant: TwentyQAttemptState,
        payload: TwentyQPayload,
        retry: bool = False,
    ) -> TwentyQMinerOutput:
        endpoint_url = self._endpoint_base_url(participant.endpoint)
        history_text = self._format_history_text(payload.history, limit=10)
        retry_suffix = (
            "This is a retry because previous output was empty. "
            "Be concise and always emit valid JSON with at least one action.\n"
            if retry
            else ""
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are playing 20 Questions.\n"
                    'Return exactly one JSON object: {"question": string|null, '
                    '"guess": string|null, "reasoning": string|null}.\n'
                    "Choose one action per turn:\n"
                    "- Ask one strong yes/no question, or\n"
                    "- Make one direct guess if confidence is high.\n"
                    "Rules:\n"
                    "- Do not repeat an incorrect guess.\n"
                    "- Do not repeat a question already answered by history.\n"
                    "- Prefer broad-to-narrow elimination.\n"
                    "- Do not ask about spelling, letters, characters, prefixes, "
                    "suffixes, or substring patterns.\n"
                    "- Avoid low-value orthographic questions such as whether the "
                    "word contains a specific letter.\n"
                    "- If guessing, set question to null.\n"
                    "- If asking, set guess to null.\n"
                    "- Keep reasoning brief.\n"
                    "- Any guess must be lowercase letters only a-z, with no "
                    "numbers, punctuation, or spaces."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Turn: {payload.turn_index}/{self.max_total_turns}\n"
                    f"History:\n{history_text}\n"
                    f"Last answer: {payload.last_answer or 'none'}\n"
                    "Target word format: lowercase letters only a-z, no numbers, "
                    "no punctuation, no spaces.\n"
                    "Do not ask spelling-based questions such as whether the word "
                    "contains a specific letter or starts/ends with certain letters.\n"
                    "Use the history to eliminate candidates. Treat prior "
                    "incorrect guesses as impossible. Only guess when the history "
                    "supports a strong single candidate; otherwise ask the highest-"
                    "value yes/no question."
                    f"{retry_suffix}"
                    "Respond with the JSON object only."
                ),
            },
        ]

        def _epistula_hook(request: httpx.Request) -> None:
            body = request.read()
            headers = generate_header(
                self.validator.wallet.hotkey, body, signed_for=participant.hotkey
            )
            for key, value in headers.items():
                request.headers[key] = value

        def _call_completion():
            http_client = httpx.Client(event_hooks={"request": [_epistula_hook]})
            client = OpenAI(
                api_key="", base_url=f"{endpoint_url}/v1", http_client=http_client
            )
            try:
                return client.chat.completions.create(
                    model="brainplay",
                    messages=messages,
                    temperature=0.5,
                    reasoning_effort=participant.reasoning_effort,
                )
            except TypeError:
                return client.chat.completions.create(
                    model="brainplay",
                    messages=messages,
                    temperature=0.5,
                )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_call_completion), timeout=(35 if retry else 80)
            )
            message = result.choices[0].message if result.choices else None
            content = (
                str(getattr(message, "content", "") or "")
                or str(getattr(message, "reasoning_content", "") or "")
                or str(getattr(message, "reasoning", "") or "")
            )
            data = extract_json(content)
        except asyncio.TimeoutError:
            bt.logging.warning(
                f"[20Q] miner query timeout for uid={participant.uid} "
                f"turn={payload.turn_index} retry={retry}"
            )
            return TwentyQMinerOutput()
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(
                f"[20Q] miner query failed for uid={participant.uid}: {err}"
            )
            return TwentyQMinerOutput()

        # Some miners may return JSON arrays/null instead of an object.
        # Treat malformed roots as empty action rather than crashing the round.
        if isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict)), None)
        if not isinstance(data, dict):
            bt.logging.debug(
                f"[20Q] miner query non-object json for uid={participant.uid} "
                f"turn={payload.turn_index}: {type(data).__name__}"
            )
            return TwentyQMinerOutput()

        question = str(data.get("question") or "").strip()
        guess = str(data.get("guess") or "").strip()
        reasoning = str(data.get("reasoning") or "").strip() or None
        if len(question) > 512:
            question = question[:512]
        if len(guess) > 128:
            guess = guess[:128]
        return TwentyQMinerOutput(
            question=question or None, guess=guess or None, reasoning=reasoning
        )

    @staticmethod
    def _format_history_text(history: list[TwentyQTurn], limit: int = 10) -> str:
        if not history:
            return "No prior turns."

        lines: list[str] = []
        for item in history[-limit:]:
            if item.question and item.question != "<guess>":
                lines.append(f"Q{item.turn}: {item.question}")
                lines.append(f"A{item.turn}: {item.answer}")
            if item.guess:
                lines.append(f"G{item.turn}: {item.guess}")
                if item.is_correct_guess is not None:
                    lines.append(
                        f"G{item.turn}_correct: "
                        f"{'yes' if item.is_correct_guess else 'no'}"
                    )
        return "\n".join(lines) if lines else "No prior turns."

    @staticmethod
    def _endpoint_base_url(endpoint: str) -> str:
        endpoint = (endpoint or "").strip().rstrip("/")
        if endpoint.startswith(("http://", "https://")):
            if endpoint.endswith(".serverless.targon.com"):
                return endpoint
            return endpoint
        if ".serverless.targon.com" in endpoint:
            return f"https://{endpoint}"
        return f"https://{endpoint}.serverless.targon.com"
