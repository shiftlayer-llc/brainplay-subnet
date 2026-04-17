# SuperMario Subnet Architecture

## Design Goal
Implement `supermario` as the first vision competition on Brainplay by reusing the shared validator lifecycle, backend room flow, and generic score persistence introduced for multi-game support.

Canonical names:
- game code: `supermario`
- competition code: `supermario`
- temporary miner/deploy alias: `mario`

Weight metadata:
- `weight_group=vision`
- `publish_mechid=1`

## Reused Core Architecture

SuperMario keeps these shared paths:
- validator entry and lifecycle in `neurons/validator.py` and `game/base/validator.py`
- plugin registry in `game/core/registry.py`
- signed backend API client in `game/providers/backend_client.py`
- endpoint commitment resolution in `game/core/endpoint_resolver.py`
- generic session/attempt persistence in `game/storage/store.py`
- shared weight publication through `game/storage/weight_state.py`

## SuperMario-Specific Modules

The game-specific validator implementation lives in:
- `game/plugins/supermario/plugin.py`
- `game/plugins/supermario/validator_runner.py`
- `game/plugins/supermario/protocol.py`
- `game/plugins/supermario/models.py`
- `game/plugins/supermario/backend_mapper.py`
- `game/plugins/supermario/scoring.py`

## Validator Round Model

Each validator round creates one shared backend room and one isolated Mario benchmark run per selected miner.

Round flow:
1. sync historical scores from backend
2. resolve committed miner endpoints for `supermario`
3. create backend room at `/api/v1/games/supermario/create`
4. submit `POST /runs` to each selected miner image
5. poll `GET /runs/{run_id}` and `GET /runs/{run_id}/steps`
6. patch backend room state incrementally with step/frame data
7. normalize final scores across miners
8. finalize backend room and publish weights through the shared `vision` group path

## Miner Image Contract

The Brainplay image exposes:
- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/steps?cursor=<n>`
- `GET /runs/{run_id}/video`

The validator uploads normalized step data to backend. Backend remains the canonical history store for:
- room snapshots
- per-step records
- frame metadata
- persisted JPG content

## Scoring

Final ranking is round-relative:
- rank by `(level_complete, progress_from_start, env_score, steps_used asc, elapsed_s asc)`
- top miner gets `1.0`
- remaining successful miners get `progress_from_start / best_progress`
- failed, invalid, or artifact-less attempts get `0.0`

## Compatibility Notes

- `mario` remains accepted as an alias in deploy/profile selection, but chain commitments and runtime code standardize on `supermario`
- `codenames` and `twentyq` publish through the shared `llm` group
- `supermario` publishes through the shared `vision` group
