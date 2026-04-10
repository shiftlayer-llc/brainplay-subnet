"""Shared SQLite store for cross-competition weight snapshots."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

import numpy as np


class WeightStateStore:
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
            CREATE TABLE IF NOT EXISTS competition_weight_snapshots (
                validator_hotkey TEXT NOT NULL,
                competition_code TEXT NOT NULL,
                weight_group TEXT NOT NULL,
                publish_mechid INTEGER NOT NULL,
                window_since_ts INTEGER NOT NULL,
                window_end_ts INTEGER NOT NULL,
                weights_json TEXT NOT NULL,
                scores_json TEXT,
                status TEXT NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (validator_hotkey, competition_code)
            )
            """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS aggregate_weight_publications (
                validator_hotkey TEXT NOT NULL,
                weight_group TEXT NOT NULL,
                publish_mechid INTEGER NOT NULL,
                published_weights_json TEXT NOT NULL,
                published_at INTEGER NOT NULL,
                source_competitions_json TEXT,
                PRIMARY KEY (validator_hotkey, weight_group)
            )
            """)
        cur.close()

    def upsert_snapshot(
        self,
        *,
        validator_hotkey: str,
        competition_code: str,
        weight_group: str,
        publish_mechid: int,
        window_since_ts: int,
        window_end_ts: int,
        weights: np.ndarray,
        scores_summary: dict[str, Any],
        status: str,
    ) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO competition_weight_snapshots(
                    validator_hotkey, competition_code, weight_group, publish_mechid,
                    window_since_ts, window_end_ts, weights_json, scores_json, status,
                    updated_at
                )
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(validator_hotkey, competition_code) DO UPDATE SET
                    weight_group=excluded.weight_group,
                    publish_mechid=excluded.publish_mechid,
                    window_since_ts=excluded.window_since_ts,
                    window_end_ts=excluded.window_end_ts,
                    weights_json=excluded.weights_json,
                    scores_json=excluded.scores_json,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    validator_hotkey,
                    competition_code,
                    weight_group,
                    int(publish_mechid),
                    int(window_since_ts),
                    int(window_end_ts),
                    json.dumps(np.asarray(weights, dtype=float).tolist()),
                    json.dumps(scores_summary or {}, sort_keys=True),
                    status,
                    int(time.time()),
                ),
            )

    def get_fresh_snapshots(
        self,
        *,
        validator_hotkey: str,
        weight_group: str,
        freshness_ttl_sec: int,
    ) -> dict[str, dict[str, Any]]:
        cutoff = int(time.time()) - int(freshness_ttl_sec)
        rows = self.conn.execute(
            """
            SELECT competition_code, publish_mechid, weights_json, scores_json, status
            FROM competition_weight_snapshots
            WHERE validator_hotkey = ? AND weight_group = ? AND updated_at >= ?
            """,
            (validator_hotkey, weight_group, cutoff),
        ).fetchall()
        snapshots: dict[str, dict[str, Any]] = {}
        for row in rows:
            snapshots[str(row[0])] = {
                "competition_code": str(row[0]),
                "publish_mechid": int(row[1]),
                "weights": json.loads(row[2] or "[]"),
                "scores_summary": json.loads(row[3] or "{}"),
                "status": str(row[4]),
            }
        return snapshots

    def upsert_publication(
        self,
        *,
        validator_hotkey: str,
        weight_group: str,
        publish_mechid: int,
        weights: np.ndarray,
        source_competitions: list[str],
    ) -> None:
        with self._lock:
            self.conn.execute(
                """
                INSERT INTO aggregate_weight_publications(
                    validator_hotkey, weight_group, publish_mechid,
                    published_weights_json, published_at, source_competitions_json
                )
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(validator_hotkey, weight_group) DO UPDATE SET
                    publish_mechid=excluded.publish_mechid,
                    published_weights_json=excluded.published_weights_json,
                    published_at=excluded.published_at,
                    source_competitions_json=excluded.source_competitions_json
                """,
                (
                    validator_hotkey,
                    weight_group,
                    int(publish_mechid),
                    json.dumps(np.asarray(weights, dtype=float).tolist()),
                    int(time.time()),
                    json.dumps(source_competitions, sort_keys=True),
                ),
            )

    def get_publication(
        self,
        *,
        validator_hotkey: str,
        weight_group: str,
    ) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT publish_mechid, published_weights_json, published_at,
                   source_competitions_json
            FROM aggregate_weight_publications
            WHERE validator_hotkey = ? AND weight_group = ?
            """,
            (validator_hotkey, weight_group),
        ).fetchone()
        if row is None:
            return None
        return {
            "publish_mechid": int(row[0]),
            "weights": json.loads(row[1] or "[]"),
            "published_at": int(row[2]),
            "source_competitions": json.loads(row[3] or "[]"),
        }
