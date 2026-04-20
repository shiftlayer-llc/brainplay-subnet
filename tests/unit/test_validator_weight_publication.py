from types import SimpleNamespace

import numpy as np

from game.base.validator import BaseValidatorNeuron


class DummyValidatorNeuron(BaseValidatorNeuron):
    async def forward(self):
        return None


class FakeWeightState:
    def __init__(self):
        self.publication = None

    def get_fresh_snapshots(self, *, validator_hotkey, weight_group, freshness_ttl_sec):
        return {
            "supermario": {
                "competition_code": "supermario",
                "publish_mechid": 1,
                "weights": [0.0, 1.0, 0.0],
                "scores_summary": {"games": 0},
                "status": "insufficient_games",
            }
        }

    def get_publication(self, *, validator_hotkey, weight_group):
        return {
            "publish_mechid": 1,
            "weights": [0.0, 1.0, 0.0],
            "published_at": 1,
            "source_competitions": ["supermario"],
        }

    def upsert_publication(
        self,
        *,
        validator_hotkey,
        weight_group,
        publish_mechid,
        weights,
        source_competitions,
    ):
        self.publication = {
            "validator_hotkey": validator_hotkey,
            "weight_group": weight_group,
            "publish_mechid": publish_mechid,
            "weights": np.asarray(weights, dtype=float).tolist(),
            "source_competitions": source_competitions,
        }


def test_non_ready_weight_snapshot_forces_burn_even_with_previous_publication():
    validator = DummyValidatorNeuron.__new__(DummyValidatorNeuron)
    validator.metagraph = SimpleNamespace(n=3)
    validator.weight_state = FakeWeightState()
    emitted = {}

    def capture_set_weights(mechid, weights):
        emitted["mechid"] = mechid
        emitted["weights"] = np.asarray(weights, dtype=float).tolist()

    validator._set_weights = capture_set_weights

    validator._publish_weight_group(
        validator_hotkey="validator-hotkey",
        weight_group="vision",
        publish_mechid=1,
    )

    assert emitted == {"mechid": 1, "weights": [1.0, 0.0, 0.0]}
    assert validator.weight_state.publication["weights"] == [1.0, 0.0, 0.0]
