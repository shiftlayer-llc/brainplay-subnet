from __future__ import annotations

import os
import sqlite3
import time
import threading
from collections import defaultdict
from typing import Dict, Iterable, Optional, Sequence

import aiohttp
import bittensor as bt
from game.utils.misc import parse_ts
from game.utils.game import Competition


class ScoreStore:
    """SQLite-backed store for finished game snapshots and backend synchronisation."""

    def __init__(
        self,
        db_path: str,
        backend_url: str,
        fetch_url: Optional[str] = None,
        signer=None,
    ):
        self.db_path = db_path
        self.backend_url = backend_url
        self.fetch_url = fetch_url
        self.signer = signer
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
                        self.db_path,
                        isolation_level=None,
                        check_same_thread=False,
                    )
                    self._conn.execute("PRAGMA journal_mode=WAL;")
                    self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    def init(self, hotkeys):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL UNIQUE,
                competition TEXT,
                rs TEXT NOT NULL,
                ro TEXT NOT NULL,
                bs TEXT NOT NULL,
                bo TEXT NOT NULL,
                winner TEXT,
                started_at INTEGER NOT NULL,
                ended_at INTEGER NOT NULL,
                score_rs REAL NOT NULL,
                score_ro REAL NOT NULL,
                score_bs REAL NOT NULL,
                score_bo REAL NOT NULL,
                reason TEXT,
                synced_at INTEGER
            );
            """
        )
        try:
            cur.execute("ALTER TABLE scores ADD COLUMN competition TEXT")
        except sqlite3.OperationalError:
            pass
        cur.close()
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS selection_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hotkey TEXT NOT NULL,
                    uid INTEGER NOT NULL,
                    competition TEXT NOT NULL,
                    ts INTEGER NOT NULL
                );
                """
            )
            try:
                cur.execute("ALTER TABLE selection_events ADD COLUMN competition TEXT")
            except sqlite3.OperationalError:
                pass
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_selection_events_hotkey ON selection_events(hotkey);"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_selection_events_ts ON selection_events(ts);"
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scores_all (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id TEXT NOT NULL,
                    competition TEXT,
                    validator TEXT NOT NULL,
                    rs TEXT NOT NULL,
                    ro TEXT NOT NULL,
                    bs TEXT NOT NULL,
                    bo TEXT NOT NULL,
                    winner TEXT,
                    started_at INTEGER NOT NULL,
                    ended_at INTEGER NOT NULL,
                    score_rs REAL NOT NULL,
                    score_ro REAL NOT NULL,
                    score_bs REAL NOT NULL,
                    score_bo REAL NOT NULL,
                    reason TEXT,
                    synced_at INTEGER
                );
                """
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_scores_all_room_validator ON scores_all(room_id, validator);"
            )
            try:
                cur.execute("ALTER TABLE scores_all ADD COLUMN competition TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE scores_all ADD COLUMN synced_at INTEGER")
            except sqlite3.OperationalError:
                pass

            # Seed selection events so every hotkey/competition pair appears at least once.
            now = int(time.time())
            competitions = [comp.value for comp in Competition]
            for uid, hotkey in enumerate(hotkeys):
                for comp in competitions:
                    cur.execute(
                        "SELECT 1 FROM selection_events WHERE hotkey=? AND competition=? LIMIT 1",
                        (hotkey, comp),
                    )
                    if cur.fetchone() is None:
                        cur.execute(
                            """
                            INSERT INTO selection_events(hotkey, uid, competition, ts)
                            VALUES(?, ?, ?, ?)
                            """,
                            (hotkey, uid, comp, now),
                        )

            cur.close()

    def record_game(
        self,
        *,
        room_id: str,
        competition: str,
        rs: str,
        ro: str,
        bs: str,
        bo: str,
        winner: Optional[str],
        started_at: float,
        ended_at: float,
        score_rs: float,
        score_ro: float,
        score_bs: float,
        score_bo: float,
        reason: Optional[str],
    ) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO scores(
                    room_id, competition, rs, ro, bs, bo, winner,
                    started_at, ended_at,
                    score_rs, score_ro, score_bs, score_bo,
                    reason, synced_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?, ?, NULL)
                ON CONFLICT(room_id) DO UPDATE SET
                    competition=excluded.competition,
                    rs=excluded.rs,
                    ro=excluded.ro,
                    bs=excluded.bs,
                    bo=excluded.bo,
                    winner=excluded.winner,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    score_rs=excluded.score_rs,
                    score_ro=excluded.score_ro,
                    score_bs=excluded.score_bs,
                    score_bo=excluded.score_bo,
                    reason=excluded.reason,
                    synced_at=NULL
                ;
                """,
                (
                    room_id,
                    competition,
                    rs,
                    ro,
                    bs,
                    bo,
                    winner,
                    int(started_at),
                    int(ended_at),
                    float(score_rs),
                    float(score_ro),
                    float(score_bs),
                    float(score_bo),
                    reason,
                ),
            )
            cur.close()

    def pending(self) -> Iterable[Dict[str, object]]:
        columns = [
            "room_id",
            "competition",
            "rs",
            "ro",
            "bs",
            "bo",
            "winner",
            "started_at",
            "ended_at",
            "score_rs",
            "score_ro",
            "score_bs",
            "score_bo",
            "reason",
        ]
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT {} FROM scores WHERE synced_at IS NULL ORDER BY ended_at ASC".format(
                    ", ".join(columns)
                )
            )
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            cur.close()
        return rows

    def window_scores_by_hotkey(
        self, since_ts: float, competition: Optional[str] = None
    ) -> Dict[str, float]:
        totals: Dict[str, float] = defaultdict(float)
        with self._lock:
            cur = self.conn.cursor()
            params = [int(since_ts)]
            query = """
                SELECT rs, ro, bs, bo,
                       score_rs, score_ro, score_bs, score_bo
                FROM scores_all
                WHERE ended_at >= ?
            """
            if competition is not None:
                query += " AND competition = ?"
                params.append(competition)
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            if not rows:
                params = [int(since_ts)]
                query = """
                    SELECT rs, ro, bs, bo,
                           score_rs, score_ro, score_bs, score_bo
                    FROM scores
                    WHERE ended_at >= ?
                """
                if competition is not None:
                    query += " AND competition = ?"
                    params.append(competition)
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
            for row in rows:
                rs, ro, bs, bo, score_rs, score_ro, score_bs, score_bo = row
                if rs:
                    totals[rs] += float(score_rs or 0.0)
                if ro:
                    totals[ro] += float(score_ro or 0.0)
                if bs:
                    totals[bs] += float(score_bs or 0.0)
                if bo:
                    totals[bo] += float(score_bo or 0.0)
            cur.close()
        return dict(totals)

    def increment_selection_count(
        self, hotkey: str, uid: int, competition: str
    ) -> None:
        if not hotkey:
            return
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO selection_events(hotkey, uid, competition, ts)
                VALUES(?, ?, ?, ?)
                """,
                (hotkey, uid, competition, int(time.time())),
            )
            cur.close()

    def selection_counts_since(
        self, since_ts: float, competition: Optional[str] = None
    ) -> Dict[str, int]:
        with self._lock:
            cur = self.conn.cursor()
            if competition is None:
                cur.execute(
                    "SELECT hotkey, COUNT(*) FROM selection_events WHERE ts >= ? GROUP BY hotkey",
                    (int(since_ts),),
                )
            else:
                cur.execute(
                    "SELECT hotkey, COUNT(*) FROM selection_events WHERE ts >= ? AND competition = ? GROUP BY hotkey",
                    (int(since_ts), competition),
                )
            rows = cur.fetchall()
            cur.close()
        return {hotkey: int(count) for hotkey, count in rows}

    def max_scores_all_id(self) -> int:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT MAX(id) FROM scores_all")
            row = cur.fetchone()
            cur.close()
        if not row or row[0] is None:
            return 0
        return int(row[0])

    def latest_scores_all_timestamp(self) -> int:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT MAX(ended_at) FROM scores_all")
            row = cur.fetchone()
            if not row or row[0] is None:
                cur.execute("SELECT MAX(ended_at) FROM scores")
                row = cur.fetchone()
            cur.close()
        if not row or row[0] is None:
            return 0
        return int(row[0])

    def games_in_window(
        self, since_ts: float, end_ts: float, competition: Optional[str] = None
    ) -> int:
        with self._lock:
            cur = self.conn.cursor()
            params = [int(since_ts), int(end_ts)]
            query = (
                "SELECT COUNT(*) FROM scores_all WHERE ended_at >= ? AND ended_at < ?"
            )
            if competition is not None:
                query += " AND competition = ?"
                params.append(competition)
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            if row and row[0]:
                count = int(row[0])
            else:
                params = [int(since_ts)]
                query = "SELECT COUNT(*) FROM scores WHERE ended_at >= ?"
                if competition is not None:
                    query += " AND competition = ?"
                    params.append(competition)
                cur.execute(query, tuple(params))
                (count,) = cur.fetchone()
            cur.close()
        return int(count)

    def mark_synced(self, room_id: str) -> None:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE scores SET synced_at=? WHERE room_id=?",
                (int(time.time()), room_id),
            )
            cur.close()

    async def sync_pending(self) -> int:
        """Pushes unsynced rows to the backend API.

        Returns the number of rows marked as synced.
        """

        if not self.backend_url:
            bt.logging.warning("No backend URL configured for score syncing.")
            return 0

        to_sync = list(self.pending())
        synced = 0
        async with aiohttp.ClientSession() as session:
            for row in to_sync:
                payload = {
                    "red": {
                        "spymaster": {
                            "hotkey": row["rs"],
                            "score": row["score_rs"],
                        },
                        "operative": {
                            "hotkey": row["ro"],
                            "score": row["score_ro"],
                        },
                    },
                    "blue": {
                        "spymaster": {
                            "hotkey": row["bs"],
                            "score": row["score_bs"],
                        },
                        "operative": {
                            "hotkey": row["bo"],
                            "score": row["score_bo"],
                        },
                    },
                    "reason": row["reason"],
                    "competition": row["competition"],
                }
                headers = self.signer() if self.signer else {}
                try:
                    async with session.patch(
                        self.backend_url + "/" + row["room_id"],
                        json=payload,
                        headers=headers,
                        timeout=10,
                    ) as resp:
                        if resp.status in (200, 201, 202, 204):
                            self.mark_synced(row["room_id"])
                            synced += 1
                        else:
                            text = await resp.text()
                            bt.logging.error(
                                f"Failed to sync score {row['room_id']}: {resp.status} {text}"
                            )
                except Exception as err:  # noqa: BLE001
                    bt.logging.error(f"Exception syncing score {row['room_id']}: {err}")
                bt.logging.info(f"Upload {synced} scores")
            await self.sync_scores_all(session=session)
        return synced

    async def sync_scores_all(
        self, session: Optional[aiohttp.ClientSession] = None
    ) -> int:
        if not self.fetch_url:
            bt.logging.debug("No fetch URL configured; skipping scores_all sync.")
            return 0

        close_session = False
        if session is None:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            headers = self.signer() if self.signer else {}
            params = {}
            since_id = self.max_scores_all_id()
            params["since_id"] = since_id
            params["limit"] = 100
            while True:
                async with session.get(
                    self.fetch_url, headers=headers, params=params, timeout=15
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        bt.logging.error(
                            f"Failed to sync scores_all: {resp.status} {text}"
                        )
                        return 0
                    payload = await resp.json(content_type=None)
                    if not isinstance(payload["data"], list):
                        bt.logging.error(
                            "Unexpected payload when syncing scores_all; expected list."
                        )
                        return
                    self._upsert_scores_all(payload["data"])
                    bt.logging.info(
                        f"Synced Score: {params['since_id'] + payload['meta']['count']} / {payload['meta']['total']}"
                    )
                    if not payload["meta"]["has_more"]:
                        break
                    params["since_id"] = payload["meta"]["next_since_id"]
        except Exception as err:  # noqa: BLE001
            bt.logging.error(f"Exception refreshing scores_all: {err}")
            return 0
        finally:
            if close_session:
                await session.close()

    def _upsert_scores_all(self, rows: Sequence[dict]) -> None:
        mapped_rows = []
        synced_at = int(time.time())
        for row in rows:
            try:
                started_at = parse_ts(row.get("started_at")) or parse_ts(
                    row.get("startedAt")
                )
                ended_at = parse_ts(row.get("ended_at")) or parse_ts(row.get("endedAt"))
                competition = row.get("competition") or ""
                mapped_rows.append(
                    (
                        str(row.get("room_id") or row.get("roomId") or ""),
                        competition,
                        str(row.get("validator") or ""),
                        str(row.get("rs") or ""),
                        str(row.get("ro") or ""),
                        str(row.get("bs") or ""),
                        str(row.get("bo") or ""),
                        row.get("winner"),
                        int(started_at or 0),
                        int(ended_at or 0),
                        float(row.get("score_rs") or row.get("scoreRs") or 0.0),
                        float(row.get("score_ro") or row.get("scoreRo") or 0.0),
                        float(row.get("score_bs") or row.get("scoreBs") or 0.0),
                        float(row.get("score_bo") or row.get("scoreBo") or 0.0),
                        row.get("reason"),
                        int(row.get("synced_at") or row.get("syncedAt") or synced_at),
                    )
                )
            except Exception as err:  # noqa: BLE001
                bt.logging.error(f"Skipping malformed scores_all row {row}: {err}")

        if not mapped_rows:
            return

        with self._lock:
            cur = self.conn.cursor()
            cur.executemany(
                """
                INSERT INTO scores_all(
                    room_id, competition, validator, rs, ro, bs, bo,
                    winner, started_at, ended_at,
                    score_rs, score_ro, score_bs, score_bo,
                    reason, synced_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(room_id, validator) DO UPDATE SET
                    competition=excluded.competition,
                    rs=excluded.rs,
                    ro=excluded.ro,
                    bs=excluded.bs,
                    bo=excluded.bo,
                    winner=excluded.winner,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    score_rs=excluded.score_rs,
                    score_ro=excluded.score_ro,
                    score_bs=excluded.score_bs,
                    score_bo=excluded.score_bo,
                    reason=excluded.reason,
                    synced_at=excluded.synced_at
                ;
                """,
                mapped_rows,
            )
            cur.close()

    def close(self):
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None
