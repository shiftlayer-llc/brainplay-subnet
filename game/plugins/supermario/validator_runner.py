"""SuperMario validator runner implementation."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from typing import Any
from uuid import uuid4

import bittensor as bt
import httpx

from game.common.epistula import generate_header
from game.common.targon import normalize_endpoint_url
from game.core.endpoint_resolver import read_endpoints_for_competition
from game.core.interfaces import AttemptResult, SessionResult
from game.plugins.supermario.backend_mapper import (
    make_create_payload,
    make_score_payload,
    make_update_payload,
)
from game.plugins.supermario.models import (
    SuperMarioAttemptState,
    SuperMarioFramePayload,
    SuperMarioProgress,
    SuperMarioRoomState,
    SuperMarioStepPayload,
)
from game.plugins.supermario.protocol import SuperMarioRunRequest, SuperMarioRunStatus
from game.plugins.supermario.scoring import compute_supermario_scores
from game.providers.backend_client import BackendClient
from game.providers.targon_client import check_endpoints


class SuperMarioValidatorRunner:
    def __init__(self, validator) -> None:
        self.validator = validator
        self.backend = BackendClient(
            base_url=self.validator.backend_base,
            signer=self.validator.build_signed_headers,
            timeout_sec=20,
        )
        self.level = os.getenv("SUPERMARIO_LEVEL", "1-1")
        self.step_limit = int(os.getenv("SUPERMARIO_STEP_LIMIT", "3000"))
        self.poll_interval_sec = float(os.getenv("SUPERMARIO_POLL_INTERVAL_SEC", "5"))
        self.request_timeout_sec = float(
            os.getenv("SUPERMARIO_REQUEST_TIMEOUT_SEC", "30")
        )
        self.max_create_room_attempts = 3
        self.progress_log_interval_sec = float(
            os.getenv("SUPERMARIO_PROGRESS_LOG_INTERVAL_SEC", "30")
        )

    async def run_round(self) -> SessionResult:
        started_at = time.time()
        bt.logging.info("[SUPERMARIO] Round start: syncing prior scores.")
        try:
            await asyncio.wait_for(
                self.validator.score_store.sync_scores_all(), timeout=600
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.warning(
                f"[SUPERMARIO] Score history sync failed before round: {err}"
            )

        selected_uids, endpoints = await self._discover_participants()
        if not selected_uids:
            ended_at = time.time()
            bt.logging.info(
                "[SUPERMARIO] Round skipped: no available miners after endpoint discovery."
            )
            return SessionResult(
                session_id=f"supermario-{uuid4().hex}",
                game_code="supermario",
                competition_code="supermario",
                status="skipped",
                started_at=started_at,
                ended_at=ended_at,
                attempts=(),
                metadata={"reason": "no_available_miners"},
            )

        room = SuperMarioRoomState(
            room_id=f"supermario-{uuid4().hex}",
            validator_key=self.validator.wallet.hotkey.ss58_address,
            level=self.level,
            step_limit=self.step_limit,
            started_at=int(started_at),
            participants=[
                SuperMarioAttemptState(
                    uid=uid,
                    hotkey=self.validator.metagraph.hotkeys[uid],
                    endpoint=endpoints[uid],
                )
                for uid in selected_uids
            ],
        )
        bt.logging.info(
            f"[SUPERMARIO] Creating backend room for {len(room.participants)} participant(s): "
            f"uids={selected_uids} level={room.level} step_limit={room.step_limit}"
        )
        created = await self._create_room(room)
        if not created:
            ended_at = time.time()
            bt.logging.warning(
                "[SUPERMARIO] Round skipped: backend room creation failed."
            )
            return SessionResult(
                session_id=room.room_id,
                game_code="supermario",
                competition_code="supermario",
                status="skipped",
                started_at=started_at,
                ended_at=ended_at,
                attempts=(),
                metadata={"reason": "create_room_failed"},
            )

        bt.logging.info(
            f"[SUPERMARIO] Backend room ready: room_id={room.room_id}. Starting miner runs."
        )
        await asyncio.gather(
            *(
                self._run_attempt(room, participant)
                for participant in room.participants
            ),
            return_exceptions=False,
        )

        bt.logging.info(
            f"[SUPERMARIO] All miner attempts finished for room_id={room.room_id}. Computing scores."
        )
        scores = compute_supermario_scores(room.participants)
        for participant in room.participants:
            participant.score = float(scores.get(participant.hotkey, 0.0))

        room.status = "completed"
        room.ended_at = int(time.time())
        room.step_count = max(
            (participant.steps_count for participant in room.participants), default=0
        )
        await self._update_room(room)
        bt.logging.info(
            f"[SUPERMARIO] Final room update sent for room_id={room.room_id}; "
            f"max_steps={room.step_count}. Uploading scores."
        )
        await self._sync_scores(room)

        ended_at = time.time()
        attempts = tuple(
            AttemptResult(
                miner_hotkey=participant.hotkey,
                status=participant.finish_reason or "completed",
                score=float(participant.score),
                started_at=started_at,
                ended_at=ended_at,
                attempt_id=f"{room.room_id}:{participant.uid}",
                turns_used=participant.steps_count,
                metadata={
                    "uid": participant.uid,
                    "run_id": participant.run_id,
                    "level_complete": participant.level_complete,
                    "progress_from_start": participant.progress_from_start,
                    "env_score": participant.env_score,
                    "elapsed_s": participant.elapsed_s,
                },
            )
            for participant in room.participants
        )
        return SessionResult(
            session_id=room.room_id,
            game_code="supermario",
            competition_code="supermario",
            status=room.status,
            started_at=started_at,
            ended_at=ended_at,
            attempts=attempts,
            metadata={"level": room.level, "participants": len(room.participants)},
        )

    async def _discover_participants(self) -> tuple[list[int], dict[int, str]]:
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
        bt.logging.info(
            f"[SUPERMARIO] Discovering participants: eligible_uids={len(uids_to_ping)} "
            f"excluded={len(exclude_set)}"
        )
        endpoints = read_endpoints_for_competition(
            self.validator,
            competition_code="supermario",
            uids=uids_to_ping,
        )
        if not endpoints:
            bt.logging.info(
                "[SUPERMARIO] No committed supermario endpoints found for eligible miners."
            )
            return [], {}
        bt.logging.info(
            f"[SUPERMARIO] Found {len(endpoints)} committed endpoint(s). Checking responsiveness."
        )
        responsive_uids = await check_endpoints(self.validator, endpoints, timeout=30)
        if not responsive_uids:
            bt.logging.info(
                "[SUPERMARIO] No responsive supermario endpoints passed health checks."
            )
            return [], {}
        bt.logging.info(
            f"[SUPERMARIO] Responsive miners selected: uids={sorted(responsive_uids)}"
        )
        return sorted(responsive_uids), {uid: endpoints[uid] for uid in responsive_uids}

    async def _create_room(self, room: SuperMarioRoomState) -> bool:
        payload = make_create_payload(room)
        for attempt_idx in range(self.max_create_room_attempts):
            try:
                bt.logging.info(
                    f"[SUPERMARIO] Creating backend room attempt {attempt_idx + 1}/"
                    f"{self.max_create_room_attempts}."
                )
                response = await self.backend.create_room("supermario", payload)
            except Exception as err:  # noqa: BLE001
                bt.logging.warning(
                    f"[SUPERMARIO] Failed to create room on backend: {err}"
                )
                return False
            room_id = (
                (response.get("data") or {}).get("id")
                if isinstance(response, dict)
                else None
            )
            if room_id:
                room.room_id = str(room_id)
                bt.logging.info(
                    f"[SUPERMARIO] Backend room created successfully: room_id={room.room_id}"
                )
                return True
            await asyncio.sleep(2)
        return False

    async def _update_room(
        self,
        room: SuperMarioRoomState,
        changed: list[SuperMarioAttemptState] | None = None,
        *,
        steps_by_hotkey: dict[str, list[SuperMarioStepPayload]] | None = None,
    ) -> None:
        payload = make_update_payload(room, changed, steps_by_hotkey=steps_by_hotkey)
        try:
            await self.backend.update_room("supermario", room.room_id, payload)
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(
                f"[SUPERMARIO] Failed to update room {room.room_id}: {err}"
            )

    async def _sync_scores(self, room: SuperMarioRoomState) -> None:
        reason = "completed" if room.status == "completed" else "aborted"
        payload = make_score_payload(room, reason=reason)
        try:
            bt.logging.info(
                f"[SUPERMARIO] Uploading {len(payload['scores'])} score(s) for room_id={room.room_id}."
            )
            await self.validator.score_store.upload_scores(
                room_id=room.room_id,
                competition="supermario",
                scores=payload["scores"],
                reason=reason,
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.error(
                f"[SUPERMARIO] Failed to persist scores for {room.room_id}: {err}"
            )
            return
        try:
            await self.backend.score_room("supermario", room.room_id, payload)
        except Exception as err:  # noqa: BLE001
            bt.logging.debug(
                f"[SUPERMARIO] score endpoint patch failed for {room.room_id}: {err}"
            )

    async def _run_attempt(
        self,
        room: SuperMarioRoomState,
        participant: SuperMarioAttemptState,
    ) -> None:
        last_progress_log_at = 0.0
        try:
            bt.logging.info(
                f"[SUPERMARIO] Starting miner run: uid={participant.uid} "
                f"hotkey={participant.hotkey} endpoint={participant.endpoint}"
            )
            run_id = await self._start_run(participant, room)
        except Exception as err:  # noqa: BLE001
            participant.is_finished = True
            participant.finish_reason = "error"
            bt.logging.warning(
                f"[SUPERMARIO] Failed to start run for uid={participant.uid}: {err}"
            )
            await self._update_room(room, [participant])
            return

        participant.run_id = run_id
        bt.logging.info(
            f"[SUPERMARIO] Miner run started: uid={participant.uid} run_id={participant.run_id}"
        )
        try:
            while True:
                fetched_steps = await self._fetch_steps(participant)
                if fetched_steps:
                    participant.steps_count = max(
                        participant.steps_count, fetched_steps[-1].step_index
                    )
                    participant.last_control = fetched_steps[-1].control
                    participant.progress = fetched_steps[-1].progress
                    participant.had_artifacts = True
                    room.step_count = max(room.step_count, participant.steps_count)
                    await self._update_room(
                        room,
                        [participant],
                        steps_by_hotkey={participant.hotkey: fetched_steps},
                    )
                    bt.logging.info(
                        f"[SUPERMARIO] Step update: uid={participant.uid} run_id={participant.run_id} "
                        f"steps={participant.steps_count} progress={participant.progress_from_start:.1f} "
                        f"env_score={participant.env_score:.1f} cursor={participant.step_cursor}"
                    )

                status = await self._fetch_status(participant)
                if status.current is not None:
                    participant.progress_from_start = float(
                        status.current.progress_from_start
                    )
                    participant.env_score = float(status.current.score)
                    participant.elapsed_s = float(status.current.elapsed_s)
                now = time.time()
                if now - last_progress_log_at >= self.progress_log_interval_sec:
                    bt.logging.info(
                        f"[SUPERMARIO] Polling run: uid={participant.uid} run_id={participant.run_id} "
                        f"state={status.state} steps={participant.steps_count} "
                        f"progress={participant.progress_from_start:.1f} "
                        f"env_score={participant.env_score:.1f} elapsed_s={participant.elapsed_s:.1f}"
                    )
                    last_progress_log_at = now
                if status.state in {"succeeded", "failed"}:
                    bt.logging.info(
                        f"[SUPERMARIO] Run reached terminal state: uid={participant.uid} "
                        f"run_id={participant.run_id} state={status.state}"
                    )
                    break
                await asyncio.sleep(self.poll_interval_sec)

            trailing_steps = await self._fetch_steps(participant)
            if trailing_steps:
                participant.steps_count = max(
                    participant.steps_count, trailing_steps[-1].step_index
                )
                participant.last_control = trailing_steps[-1].control
                participant.progress = trailing_steps[-1].progress
                participant.had_artifacts = True
                room.step_count = max(room.step_count, participant.steps_count)
                await self._update_room(
                    room,
                    [participant],
                    steps_by_hotkey={participant.hotkey: trailing_steps},
                )

            await self._finalize_attempt(participant, status)
            await self._upload_video_artifact(room, participant, status)
        except Exception as err:  # noqa: BLE001
            participant.is_finished = True
            participant.finish_reason = "error"
            bt.logging.warning(
                f"[SUPERMARIO] Attempt failed for uid={participant.uid} run_id={participant.run_id}: {err}"
            )
        bt.logging.info(
            f"[SUPERMARIO] Attempt finished: uid={participant.uid} run_id={participant.run_id} "
            f"finish_reason={participant.finish_reason} steps={participant.steps_count} "
            f"progress={participant.progress_from_start:.1f} env_score={participant.env_score:.1f}"
        )
        await self._update_room(room, [participant])

    async def _finalize_attempt(
        self,
        participant: SuperMarioAttemptState,
        status: SuperMarioRunStatus,
    ) -> None:
        participant.is_finished = True
        if (
            status.state != "succeeded"
            or status.result is None
            or not status.result.episodes
        ):
            participant.finish_reason = "error"
            return

        episode = status.result.episodes[0]
        participant.had_artifacts = True
        participant.env_score = float(episode.score)
        participant.progress_from_start = float(episode.progress_from_start)
        participant.elapsed_s = float(episode.elapsed_s)
        participant.steps_count = max(participant.steps_count, int(episode.steps))
        finish_reason = str(episode.finish_reason or "").lower()
        participant.level_complete = bool(
            participant.progress.done
            or finish_reason in {"terminated", "level_complete"}
        )
        participant.finish_reason = self._map_finish_reason(
            finish_reason, participant.progress.done
        )

    @staticmethod
    def _map_finish_reason(raw_reason: str, done: bool) -> str:
        if done or raw_reason in {"terminated", "level_complete"}:
            return "level_complete"
        if raw_reason in {"timeout", "truncated", "max_steps"}:
            return "timeout"
        if "death" in raw_reason or "die" in raw_reason:
            return "death"
        if "stuck" in raw_reason:
            return "stuck"
        if raw_reason == "invalid_response":
            return "invalid_response"
        return "error"

    async def _start_run(
        self, participant: SuperMarioAttemptState, room: SuperMarioRoomState
    ) -> str:
        payload = SuperMarioRunRequest(
            max_steps_per_episode=room.step_limit
        ).model_dump()
        response = await self._request_json(
            participant=participant,
            method="POST",
            path="/runs",
            body=payload,
        )
        run_id = str(response.get("run_id") or "")
        if not run_id:
            raise RuntimeError(f"run_id missing from response: {response}")
        return run_id

    async def _fetch_status(
        self, participant: SuperMarioAttemptState
    ) -> SuperMarioRunStatus:
        response = await self._request_json(
            participant=participant,
            method="GET",
            path=f"/runs/{participant.run_id}",
            body=None,
        )
        return SuperMarioRunStatus.model_validate(response)

    async def _fetch_steps(
        self, participant: SuperMarioAttemptState
    ) -> list[SuperMarioStepPayload]:
        response = await self._request_json(
            participant=participant,
            method="GET",
            path=f"/runs/{participant.run_id}/steps?cursor={participant.step_cursor}",
            body=None,
        )
        raw_steps = response.get("steps") or []
        next_cursor = int(response.get("next_cursor") or participant.step_cursor)
        steps = [SuperMarioStepPayload.model_validate(step) for step in raw_steps]
        participant.step_cursor = max(participant.step_cursor, next_cursor)
        return steps

    async def _upload_video_artifact(
        self,
        room: SuperMarioRoomState,
        participant: SuperMarioAttemptState,
        status: SuperMarioRunStatus,
    ) -> None:
        video_url = None
        if status.result is not None:
            video_url = status.result.video_url or video_url
        video_url = video_url or status.video_url
        if not video_url:
            bt.logging.info(
                f"[SUPERMARIO] No video artifact reported for uid={participant.uid} run_id={participant.run_id}."
            )
            return

        try:
            video_bytes, mime_type = await self._fetch_video_bytes(
                participant=participant,
                video_url=video_url,
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.warning(
                f"[SUPERMARIO] Failed to fetch video for uid={participant.uid} run_id={participant.run_id}: {err}"
            )
            return

        payload = {
            "validatorKey": room.validator_key,
            "participant_hotkey": participant.hotkey,
            "run_id": participant.run_id,
            "mime_type": mime_type,
            "mp4_base64": base64.b64encode(video_bytes).decode("ascii"),
        }
        try:
            response = await self.backend.upload_room_video(
                "supermario", room.room_id, payload
            )
        except Exception as err:  # noqa: BLE001
            bt.logging.warning(
                f"[SUPERMARIO] Failed to upload video for uid={participant.uid} run_id={participant.run_id}: {err}"
            )
            return

        data = response.get("data") if isinstance(response, dict) else None
        video_id = data.get("id") if isinstance(data, dict) else None
        if video_id:
            participant.last_video_id = str(video_id)
            bt.logging.info(
                f"[SUPERMARIO] Uploaded final video: uid={participant.uid} run_id={participant.run_id} video_id={participant.last_video_id}"
            )

    async def _fetch_video_bytes(
        self,
        *,
        participant: SuperMarioAttemptState,
        video_url: str,
    ) -> tuple[bytes, str]:
        endpoint = normalize_endpoint_url(participant.endpoint)
        request_body = b""
        headers = generate_header(
            self.validator.wallet.hotkey,
            request_body,
            signed_for=participant.hotkey,
        )
        target_url = (
            video_url
            if video_url.startswith("http://") or video_url.startswith("https://")
            else f"{endpoint}{video_url}"
        )
        async with httpx.AsyncClient(
            timeout=max(self.request_timeout_sec, 120)
        ) as client:
            response = await client.get(target_url, headers=headers)
            response.raise_for_status()
            mime_type = response.headers.get("content-type", "video/mp4").split(";")[0]
            return response.content, mime_type

    async def _request_json(
        self,
        *,
        participant: SuperMarioAttemptState,
        method: str,
        path: str,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        endpoint = normalize_endpoint_url(participant.endpoint)
        content: bytes | None = None
        if body is not None:
            content = json.dumps(body, separators=(",", ":")).encode("utf-8")
            request_body: dict[str, Any] | bytes = content
        else:
            request_body = b""

        headers = generate_header(
            self.validator.wallet.hotkey,
            request_body,
            signed_for=participant.hotkey,
        )
        request_kwargs = {"headers": headers}
        if body is not None:
            request_kwargs["content"] = content
            request_kwargs["headers"] = {
                **headers,
                "Content-Type": "application/json",
            }
        async with httpx.AsyncClient(timeout=self.request_timeout_sec) as client:
            response = await client.request(
                method,
                f"{endpoint}{path}",
                **request_kwargs,
            )
            response.raise_for_status()
            return response.json()
