# SuperMario Integration Tasks

## Subnet

- add canonical `supermario` support to `game/core/codes.py`
- accept `mario` as an alias only
- register `game/plugins/supermario/*`
- move non-codenames endpoint resolution onto generic competition-code lookup
- publish weights through shared `weight_group` and `publish_mechid` state
- add `deploy/profiles/supermario.json`
- make `deploy/miner.py --competition mario` normalize to `supermario`

## Backend

- keep `src/App/games_v2/supermario/*` as the canonical backend module
- enable codenames-style auth and rate-limit middleware on SuperMario write/sync routes
- keep room, step, and frame persistence contracts unchanged
- update `docs/supermario.md` to reflect current implementation

## Miner Image

- keep existing run lifecycle endpoints
- add `GET /runs/{run_id}/steps`
- export normalized step payloads with backend-compatible JPG frame data
- preserve Epistula auth on all Mario endpoints

## Tests

- subnet unit tests for canonical codes and SuperMario scoring
- backend route/service/controller tests
- image runtime tests for step export and authenticated route exposure

## Rollout Defaults

- canonical competition key on-chain: `supermario`
- temporary CLI/profile alias: `mario`
- default level: `1-1`
- default step limit: `3000`
- default weight lane: `vision`
- default publish mechid: `1`
