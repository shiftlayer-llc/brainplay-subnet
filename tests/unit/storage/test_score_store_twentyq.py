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


def test_legacy_score_queries_filter_by_validator(tmp_path):
    db_path = str(tmp_path / "scores.db")
    store = ScoreStore(
        db_path,
        backend_url="",
        fetch_url=None,
        signer=lambda: {"X-Validator-Hotkey": "validator-a"},
    )
    store.init()

    store._upsert_scores_all(
        [
            {
                "id": 1,
                "room_id": "room-a",
                "competition": "codenames",
                "validator": "validator-a",
                "rs": "miner-1",
                "ro": "miner-2",
                "bs": "miner-3",
                "bo": "miner-4",
                "started_at": 100,
                "ended_at": 120,
                "score_rs": 1.0,
                "score_ro": 0.0,
                "score_bs": 0.0,
                "score_bo": 0.0,
                "participants": ["miner-1", "miner-2", "miner-3", "miner-4"],
            },
            {
                "id": 2,
                "room_id": "room-b",
                "competition": "codenames",
                "validator": "validator-b",
                "rs": "miner-1",
                "ro": "miner-2",
                "bs": "miner-3",
                "bo": "miner-4",
                "started_at": 130,
                "ended_at": 150,
                "score_rs": 0.0,
                "score_ro": 1.0,
                "score_bs": 0.0,
                "score_bo": 0.0,
                "participants": ["miner-1", "miner-2", "miner-3", "miner-4"],
            },
        ]
    )

    avg_scores, total_scores, counts = store.window_average_scores_by_hotkey(
        "codenames", 0, 1_000, validator_hotkey="validator-a"
    )
    wins, losses = store.win_loss_counts_in_window(
        "codenames", 0, 1_000, validator_hotkey="validator-a"
    )

    assert store.max_scores_all_id(validator_hotkey="validator-a") == 1
    assert store.max_scores_all_id(validator_hotkey="validator-b") == 2
    assert store.latest_scores_all_timestamp(validator_hotkey="validator-a") == 120
    assert (
        store.games_in_window(0, 1_000, "codenames", validator_hotkey="validator-a")
        == 1
    )
    assert avg_scores["miner-1"] == 1.0
    assert total_scores["miner-2"] == 0.0
    assert counts["miner-1"] == 1.0
    assert wins["miner-1"] == 1
    assert losses["miner-2"] == 1


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
                "id": 12,
                "room_id": "69b8700dae8068000cccf421",
                "competition": "twentyq",
                "validator": "validator-hotkey",
                "status": "completed",
                "reason": "validator_finalized",
                "question_count": 30,
                "question_limit": 20,
                "bonus_limit": 10,
                "started_at": 100,
                "ended_at": 120,
                "participants": [
                    {
                        "hotkey": "miner-1",
                        "uid": 58,
                        "score": 1.0,
                        "question_count": 30,
                        "is_finished": True,
                        "finish_reason": "max_questions_reached",
                    },
                    {
                        "hotkey": "miner-2",
                        "uid": 47,
                        "score": 0.0,
                        "question_count": 30,
                        "is_finished": True,
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

    session_row = generic_store.conn.execute(
        "SELECT status, metadata_json FROM sessions WHERE session_id = ?",
        ("69b8700dae8068000cccf421",),
    ).fetchone()
    assert session_row[0] == "completed"
    assert '"reason": "validator_finalized"' in session_row[1]
    assert '"question_limit": 20' in session_row[1]

    attempt_row = generic_store.conn.execute(
        "SELECT status, score FROM attempts WHERE attempt_id = ?",
        ("69b8700dae8068000cccf421:miner-1",),
    ).fetchone()
    assert attempt_row == ("max_questions_reached", 1.0)
