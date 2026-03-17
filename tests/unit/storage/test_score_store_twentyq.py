import asyncio

from game.storage.store import GenericStore
from game.validator.score_store import ScoreStore


def test_upload_scores_persists_fractional_values(tmp_path):
    db_path = str(tmp_path / "scores.db")
    store = ScoreStore(
        db_path,
        backend_url="",
        fetch_url=None,
        signer=lambda: {"X-Validator-Hotkey": "validator-hotkey"},
    )
    store.init()

    asyncio.run(
        store.upload_scores(
            room_id="room-1",
            competition="twentyq",
            scores=[
                {"hotkey": "miner-1", "score": 0.9},
                {"hotkey": "miner-2", "score": 0.5},
            ],
            reason="completed",
        )
    )

    avg_scores, total_scores, counts = store.window_average_scores_by_hotkey(
        "twentyq", 0, 2_000_000_000
    )
    assert avg_scores["miner-1"] == 0.9
    assert total_scores["miner-2"] == 0.5
    assert counts["miner-1"] == 1.0


def test_sync_scores_all_populates_generic_store_for_twentyq(tmp_path):
    db_path = str(tmp_path / "scores.db")
    generic_store = GenericStore(db_path)
    generic_store.init()
    store = ScoreStore(
        db_path,
        backend_url="",
        fetch_url=None,
        signer=lambda: {"X-Validator-Hotkey": "validator-hotkey"},
        generic_store=generic_store,
    )
    store.init()

    store._upsert_scores_all(
        [
            {
                "id": 1,
                "room_id": "room-1",
                "competition": "twentyq",
                "validator": "validator-hotkey",
                "started_at": 100,
                "ended_at": 120,
                "reason": "completed",
                "participants": [
                    {
                        "hotkey": "miner-1",
                        "score": 1.0,
                        "finish_reason": "solved",
                    },
                    {
                        "hotkey": "miner-2",
                        "score": 0.0,
                        "finish_reason": "max_questions_reached",
                    },
                ],
            }
        ]
    )

    avg_scores, total_scores, counts = generic_store.window_average_scores_by_hotkey(
        "twentyq", 0, 1_000
    )
    wins, losses = generic_store.win_loss_counts_in_window("twentyq", 0, 1_000)

    assert generic_store.games_in_window("twentyq", 0, 1_000) == 1
    assert avg_scores["miner-1"] == 1.0
    assert total_scores["miner-2"] == 0.0
    assert counts["miner-1"] == 1.0
    assert wins["miner-1"] == 1
    assert losses["miner-2"] == 1
