"""TwentyQ validator runner implementation."""

from __future__ import annotations

import asyncio
import random
import time
from pathlib import Path
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

WORD_FILES = (
    "game/data/words/default.txt",
    "game/data/words/duet.txt",
    "game/data/words/thegamegal.txt",
    "game/data/words/undercover.txt",
)


class TwentyQValidatorRunner:
    def __init__(self, validator) -> None:
        self.validator = validator
        self.max_questions = 20
        self.max_bonus_questions = 5
        self.max_total_turns = self.max_questions + self.max_bonus_questions
        self.judge = ChutesAIJudge()
        self.backend = BackendClient(
            base_url=self.validator.backend_base,
            signer=self.validator.build_signed_headers,
            timeout_sec=10,
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
                session_id=f"20q-{uuid4().hex}",
                game_code="20q",
                competition_code="20q",
                status="skipped",
                started_at=started_at,
                ended_at=now,
                attempts=(),
                metadata={"reason": "no_available_miners"},
            )

        secret_word = self._pick_secret_word()
        room = TwentyQRoomState(
            room_id=f"20q-{uuid4().hex}",
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

        await self._create_room(room)

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
            game_code="20q",
            competition_code="20q",
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

        responsive_uids = await check_endpoints(self.validator, endpoints, timeout=30)
        if not responsive_uids:
            bt.logging.warning("[20Q] No responsive miners found.")
            return [], {}

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

    def _pick_secret_word(self) -> str:
        file_path = Path(random.choice(WORD_FILES))
        try:
            words = [line.strip() for line in file_path.read_text().splitlines()]
        except Exception:
            words = ["apple", "planet", "piano", "eagle", "river"]
        clean_words = [w for w in words if w and " " not in w and len(w) <= 24]
        if not clean_words:
            clean_words = ["apple", "planet", "piano", "eagle", "river"]
        return random.choice(clean_words).lower()

    async def _create_room(self, room: TwentyQRoomState) -> None:
        payload = make_create_payload(room)
        try:
            response = await self.backend.create_room("20q", payload)
            if isinstance(response, dict):
                room_id = (
                    (response.get("data") or {}).get("id")
                    or response.get("id")
                    or room.room_id
                )
                room.room_id = str(room_id)
                return
        except Exception as err:  # noqa: BLE001
            bt.logging.warning(f"[20Q] Failed to create room on backend: {err}")

    async def _update_room(
        self, room: TwentyQRoomState, changed: list[TwentyQAttemptState] | None = None
    ) -> None:
        payload = make_update_payload(room, changed)
        try:
            await self.backend.update_room("20q", room.room_id, payload)
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(f"[20Q] Failed to update room {room.room_id}: {err}")

    async def _sync_scores(self, room: TwentyQRoomState) -> None:
        reason = "completed" if room.status == "completed" else "aborted"
        scores = make_score_payload(room, reason=reason)["scores"]
        try:
            await self.validator.score_store.upload_scores(
                room_id=room.room_id,
                competition="20q",
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
                "20q", room.room_id, {"reason": reason, "scores": scores}
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
                participant.invalid_turns += 1
                if participant.invalid_turns >= 2:
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
        self, participant: TwentyQAttemptState, payload: TwentyQPayload
    ) -> TwentyQMinerOutput:
        endpoint_url = self._endpoint_base_url(participant.endpoint)
        history_lines = []
        for item in payload.history[-10:]:
            history_lines.append(f"Q{item.turn}: {item.question}")
            history_lines.append(f"A{item.turn}: {item.answer}")
        history_text = (
            "\n".join(history_lines) if history_lines else "No prior questions."
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are playing 20 Questions. "
                    'Respond with JSON only: {"question": string|null, "guess": string|null, "reasoning": string|null}. '
                    "Provide at least one of question or guess."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Turn: {payload.turn_index}/{self.max_total_turns}\n"
                    f"History:\n{history_text}\n"
                    f"Last answer: {payload.last_answer or 'none'}\n"
                    "Ask your next best yes/no question or make a direct guess."
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
                    reasoning_effort=participant.reasoning_effort,
                )
            except TypeError:
                return client.chat.completions.create(
                    model="brainplay",
                    messages=messages,
                )

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_call_completion), timeout=80
            )
            content = result.choices[0].message.content if result.choices else ""
            data = extract_json(content)
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(
                f"[20Q] miner query failed for uid={participant.uid}: {err}"
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
    def _endpoint_base_url(endpoint: str) -> str:
        endpoint = (endpoint or "").strip().rstrip("/")
        if endpoint.startswith(("http://", "https://")):
            if endpoint.endswith(".serverless.targon.com"):
                return endpoint
            return endpoint
        if ".serverless.targon.com" in endpoint:
            return f"https://{endpoint}"
        return f"https://{endpoint}.serverless.targon.com"
