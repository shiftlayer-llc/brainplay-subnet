"""Generic sessions/attempts/event store (additive scaffold)."""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Dict, Iterable, Optional

from .migrations import migrate


class GenericStore:
    """SQLite store for generic multi-game session and attempt records."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        folder = os.path.dirname(db_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    self._conn = sqlite3.connect(
                        self.db_path, isolation_level=None, check_same_thread=False
                    )
                    self._conn.execute("PRAGMA journal_mode=WAL;")
                    self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    def init(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                game_code TEXT NOT NULL,
                competition_code TEXT NOT NULL,
                validator_hotkey TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                metadata_json TEXT
            )
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                miner_hotkey TEXT NOT NULL,
                status TEXT NOT NULL,
                score REAL NOT NULL,
                started_at INTEGER NOT NULL,
                ended_at INTEGER,
                summary_json TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attempt_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attempt_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT,
                ts INTEGER NOT NULL,
                FOREIGN KEY(attempt_id) REFERENCES attempts(attempt_id)
            )
            """)
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_attempts_comp_hotkey ON attempts(session_id, miner_hotkey)"
        )
        cur.close()
        migrate(self.conn)

    def upsert_session(self, row: Dict[str, Any]) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO sessions(session_id, game_code, competition_code, validator_hotkey, status, started_at, ended_at, metadata_json)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                    game_code=excluded.game_code,
                    competition_code=excluded.competition_code,
                    validator_hotkey=excluded.validator_hotkey,
                    status=excluded.status,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    metadata_json=excluded.metadata_json
                """,
                (
                    row["session_id"],
                    row["game_code"],
                    row["competition_code"],
                    row["validator_hotkey"],
                    row["status"],
                    int(row["started_at"]),
                    int(row["ended_at"]) if row.get("ended_at") is not None else None,
                    row.get("metadata_json"),
                ),
            )

    def upsert_attempt(self, row: Dict[str, Any]) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO attempts(attempt_id, session_id, miner_hotkey, status, score, started_at, ended_at, summary_json)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(attempt_id) DO UPDATE SET
                    session_id=excluded.session_id,
                    miner_hotkey=excluded.miner_hotkey,
                    status=excluded.status,
                    score=excluded.score,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    summary_json=excluded.summary_json
                """,
                (
                    row["attempt_id"],
                    row["session_id"],
                    row["miner_hotkey"],
                    row["status"],
                    float(row["score"]),
                    int(row["started_at"]),
                    int(row["ended_at"]) if row.get("ended_at") is not None else None,
                    row.get("summary_json"),
                ),
            )

    def window_average_scores_by_hotkey(
        self, competition_code: str, since_ts: float, end_ts: float
    ):
        query = """
            SELECT a.miner_hotkey, AVG(a.score), SUM(a.score), COUNT(*)
            FROM attempts a
            JOIN sessions s ON s.session_id = a.session_id
            WHERE s.competition_code = ? AND a.ended_at >= ? AND a.ended_at < ?
            GROUP BY a.miner_hotkey
        """
        rows = self.conn.execute(
            query, (competition_code, int(since_ts), int(end_ts))
        ).fetchall()
        avg_scores = {hotkey: float(avg or 0.0) for hotkey, avg, _, _ in rows}
        total_scores = {hotkey: float(total or 0.0) for hotkey, _, total, _ in rows}
        counts = {hotkey: float(count or 0.0) for hotkey, _, _, count in rows}
        return avg_scores, total_scores, counts

    def win_loss_counts_in_window(
        self, competition_code: str, since_ts: float, end_ts: float
    ) -> tuple[Dict[str, int], Dict[str, int]]:
        query = """
            SELECT
                a.miner_hotkey,
                SUM(CASE WHEN a.score > 0 THEN 1 ELSE 0 END),
                SUM(CASE WHEN a.score <= 0 THEN 1 ELSE 0 END)
            FROM attempts a
            JOIN sessions s ON s.session_id = a.session_id
            WHERE s.competition_code = ? AND a.ended_at >= ? AND a.ended_at < ?
            GROUP BY a.miner_hotkey
        """
        rows = self.conn.execute(
            query, (competition_code, int(since_ts), int(end_ts))
        ).fetchall()
        wins = {str(hotkey): int(win_count or 0) for hotkey, win_count, _ in rows}
        losses = {str(hotkey): int(loss_count or 0) for hotkey, _, loss_count in rows}
        return wins, losses

    def games_in_window(
        self, competition_code: str, since_ts: float, end_ts: float
    ) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(DISTINCT s.session_id)
            FROM sessions s
            WHERE s.competition_code = ? AND s.ended_at >= ? AND s.ended_at < ?
            """,
            (competition_code, int(since_ts), int(end_ts)),
        ).fetchone()
        return int(row[0] or 0) if row else 0

    def latest_timestamp(self, competition_code: Optional[str] = None) -> int:
        if competition_code is None:
            row = self.conn.execute("SELECT MAX(ended_at) FROM attempts").fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT MAX(a.ended_at)
                FROM attempts a
                JOIN sessions s ON s.session_id = a.session_id
                WHERE s.competition_code = ?
                """,
                (competition_code,),
            ).fetchone()
        return int(row[0] or 0) if row else 0

    def iter_attempts(self) -> Iterable[tuple]:
        return self.conn.execute("SELECT * FROM attempts ORDER BY rowid ASC")

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
