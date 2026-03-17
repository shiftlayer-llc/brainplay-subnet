from game.storage.store import GenericStore


def test_generic_store_aggregates_attempt_scores(tmp_path):
    store = GenericStore(str(tmp_path / "generic.db"))
    store.init()

    store.upsert_session(
        {
            "session_id": "room-1",
            "game_code": "twentyq",
            "competition_code": "twentyq",
            "validator_hotkey": "validator-1",
            "status": "completed",
            "started_at": 100,
            "ended_at": 120,
            "metadata_json": "{}",
        }
    )
    store.upsert_attempt(
        {
            "attempt_id": "room-1:miner-1",
            "session_id": "room-1",
            "miner_hotkey": "miner-1",
            "status": "solved",
            "score": 1.0,
            "started_at": 100,
            "ended_at": 120,
            "summary_json": "{}",
        }
    )
    store.upsert_attempt(
        {
            "attempt_id": "room-1:miner-2",
            "session_id": "room-1",
            "miner_hotkey": "miner-2",
            "status": "completed",
            "score": 0.0,
            "started_at": 100,
            "ended_at": 120,
            "summary_json": "{}",
        }
    )

    avg_scores, total_scores, counts = store.window_average_scores_by_hotkey(
        "twentyq", 0, 1_000
    )
    wins, losses = store.win_loss_counts_in_window("twentyq", 0, 1_000)

    assert store.games_in_window("twentyq", 0, 1_000) == 1
    assert store.latest_timestamp("twentyq") == 120
    assert avg_scores["miner-1"] == 1.0
    assert total_scores["miner-2"] == 0.0
    assert counts["miner-1"] == 1.0
    assert wins["miner-1"] == 1
    assert losses["miner-2"] == 1
