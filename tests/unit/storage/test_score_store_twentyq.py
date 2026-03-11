import asyncio

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
