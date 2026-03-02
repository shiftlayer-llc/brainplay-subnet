"""SQLite migration runner for the generic storage tables."""

from __future__ import annotations

import sqlite3


CURRENT_SCHEMA_VERSION = 1


def get_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version={int(version)}")


def migrate(conn: sqlite3.Connection) -> int:
    version = get_schema_version(conn)
    if version >= CURRENT_SCHEMA_VERSION:
        return version
    # Future migrations go here. Version 1 schema is created in store.init().
    set_schema_version(conn, CURRENT_SCHEMA_VERSION)
    return CURRENT_SCHEMA_VERSION
