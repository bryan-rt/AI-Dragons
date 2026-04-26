"""Session-scoped SQLite cache for Foundry Rule Element data.

Created fresh (or reused) at session start. Disposable between sessions.
Stores Rule Elements extracted from local character JSONs and fetched from
GitHub for bestiary entries.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

DEFAULT_CACHE_PATH = "/tmp/pf2e_session_cache.sqlite"

SCHEMA = """\
CREATE TABLE IF NOT EXISTS cached_items (
    slug            TEXT PRIMARY KEY,
    pack            TEXT NOT NULL,
    item_type       TEXT NOT NULL,
    name            TEXT NOT NULL,
    raw_json        TEXT NOT NULL,
    rule_elements   TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'local',
    fetched_at      TEXT NOT NULL,
    rule_count      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_item_type ON cached_items(item_type);
CREATE INDEX IF NOT EXISTS idx_rule_count ON cached_items(rule_count);
CREATE INDEX IF NOT EXISTS idx_source ON cached_items(source);
"""


class SessionCache:
    """Session-scoped SQLite cache for Foundry Rule Element data."""

    def __init__(self, path: str = DEFAULT_CACHE_PATH):
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def store_item(
        self,
        slug: str,
        pack: str,
        item_type: str,
        name: str,
        raw_json: str,
        rule_elements: str,
        source: str = "local",
    ) -> None:
        """Store item in cache. If slug exists, keep version with more rules."""
        new_count = len(json.loads(rule_elements))
        existing = self._conn.execute(
            "SELECT rule_count FROM cached_items WHERE slug = ?", (slug,)
        ).fetchone()

        if existing is not None:
            if existing["rule_count"] >= new_count:
                return  # existing version has at least as many rules

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO cached_items
               (slug, pack, item_type, name, raw_json, rule_elements,
                source, fetched_at, rule_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, pack, item_type, name, raw_json,
             rule_elements, source, now, new_count),
        )
        self._conn.commit()

    def get_item(self, slug: str) -> dict | None:
        """Retrieve cached item by slug. Returns dict or None."""
        row = self._conn.execute(
            "SELECT * FROM cached_items WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_rule_elements(self, slug: str) -> list[dict]:
        """Retrieve Rule Elements for a slug. Returns [] if not cached."""
        row = self._conn.execute(
            "SELECT rule_elements FROM cached_items WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return []
        return json.loads(row["rule_elements"])

    def is_cached(self, slug: str) -> bool:
        """Check if slug is in the cache."""
        row = self._conn.execute(
            "SELECT 1 FROM cached_items WHERE slug = ?", (slug,)
        ).fetchone()
        return row is not None

    def list_items(self) -> list[dict]:
        """Return summary of all cached items."""
        rows = self._conn.execute(
            "SELECT slug, name, item_type, source, rule_count FROM cached_items"
            " ORDER BY item_type, name"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> SessionCache:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
