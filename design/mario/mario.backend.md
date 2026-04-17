# SuperMario Backend Integration

## Canonical Backend Module

The backend implementation already exists under:
- `/root/evm/backend/src/App/games_v2/supermario/*`

Base route prefix:
- `/api/v1/games/supermario`

## Active Contracts Used by the Validator

### Create room
- `POST /api/v1/games/supermario/create`
- signed validator headers required
- whitelist validation required

Request:
- `validatorKey`
- `competition=supermario`
- `participants`
- `level`
- `seed`
- `step_limit`

### Incremental room updates
- `PATCH /api/v1/games/supermario/:roomId`

Per-participant update payload includes:
- `hotkey`
- `is_finished`
- `finish_reason`
- `score`
- `steps_count`
- `last_frame_id`
- `last_control`
- `progress`
- incremental `steps[]`

Each step carries:
- `step_index`
- `control`
- `captured_at`
- `reward_delta`
- `progress`
- `frame { mime_type, jpg_base64, width, height }`

### Final score sync
- `PATCH /api/v1/games/supermario/score/:roomId`

Payload:
- `reason`
- `participants[{ hotkey, score }]`

### Final video upload
- `PATCH /api/v1/games/supermario/video/:roomId`

Payload:
- `participant_hotkey`
- `run_id`
- `mime_type=video/mp4`
- `video_base64`

## Storage Behavior

Backend persistence uses:
- Redis active room: `supermario:room:{roomId}`
- Redis save queue: `supermario:saveQueue:{roomId}`
- Mongo room history: `supermario_room_history`
- Mongo step history: `supermario_step_history`
- Mongo frame metadata: `supermario_frame_assets`

Frame bytes are stored by backend according to backend config:
- `SUPERMARIO_FRAME_STORAGE_MODE=memory` for live step frames
- `SUPERMARIO_FRAME_STORAGE_MODE=filesystem` for filesystem-backed frame persistence
- `SUPERMARIO_FRAME_STORAGE_MODE=db` only as a compatibility mode

Final videos are stored by backend according to backend config:
- `SUPERMARIO_VIDEO_STORAGE_MODE=r2`
- `SUPERMARIO_VIDEO_STORAGE_MODE=filesystem`
- `SUPERMARIO_VIDEO_STORAGE_MODE=db` only as a compatibility mode

## Security Requirements

SuperMario uses the same middleware posture as codenames:
- `CustomRateLimitMiddleware`
- `ValidateGameRequestMiddlewares.validateGameRequest`
- `ValidatorMiddleware.validateWhitelistHotkey`

Applied to:
- `/create`
- `/:roomId`
- `/score/:roomId`
- `/video/:roomId`
- `/sync`

## Validator Expectations

The subnet validator assumes:
- create returns `{ ok: true, data: { id } }`
- update returns `{ ok: true }`
- score returns `{ ok: true }`
- sync exposes finalized sessions for score refresh

If frame storage is on filesystem, backend still remains the source of truth because it owns the frame metadata table.
