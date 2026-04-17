# SuperMario Validator Workflow

## Round Setup

Inputs:
- competition code `supermario`
- miner commitments under `supermario`
- deployed Brainplay image with Mario run API

Validator actions:
1. refresh score sync state from backend
2. read committed `supermario` endpoints from chain
3. probe `/meta` and keep only responsive miners
4. create backend room with selected hotkeys

## Per-Miner Attempt Workflow

For each selected miner:
1. submit `POST /runs`
2. store returned `run_id`
3. poll `GET /runs/{run_id}`
4. poll `GET /runs/{run_id}/steps?cursor=<n>`
5. forward new steps to backend room patch endpoint
6. continue until status becomes `succeeded` or `failed`
7. finalize participant status and include score after round normalization

## Step Export Workflow

The miner image exports normalized steps in cursor order.

Each step is converted by the validator into backend-compatible data and uploaded immediately. This keeps:
- live room state visible in Redis/socket views
- step history persisted incrementally
- frame assets persisted by backend rather than left only on miner disk

## Finalization Workflow

Once all participants finish:
1. compute normalized round scores
2. patch backend room with final participant states
3. call backend score endpoint
4. persist generic session/attempt rows locally
5. publish the resulting weight snapshot through the shared `vision` aggregation path

## Failure Handling

If no miners are available:
- skip the round cleanly

If room creation fails:
- skip the round and keep no partial session

If a miner run fails:
- mark that participant with `finish_reason=error`
- score `0.0`
- continue the round for other miners

If the shared `vision` group cannot publish:
- keep the latest successful aggregate if one exists
- otherwise publish burn weights for `mechid=1`
