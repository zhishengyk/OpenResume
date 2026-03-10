import json
import sqlite3

from openresume_api.db import _migrate_search_sessions


def test_search_session_migration_rebuilds_legacy_platform_column():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            """
            CREATE TABLE searchsession (
                id TEXT NOT NULL PRIMARY KEY,
                platform TEXT NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                job_targets JSON,
                cities JSON,
                salary_floor INTEGER NOT NULL,
                must_have_keywords JSON,
                blocked_reason TEXT,
                summary TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO searchsession (
                id,
                platform,
                mode,
                status,
                job_targets,
                cities,
                salary_floor,
                must_have_keywords,
                blocked_reason,
                summary,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "session-1",
                "official",
                "recommend_only",
                "ready",
                json.dumps(["Frontend Engineer"]),
                json.dumps(["Shanghai"]),
                25000,
                json.dumps(["React"]),
                None,
                "done",
                "2026-03-09T00:00:00",
                "2026-03-09T00:00:00",
            ),
        )

        _migrate_search_sessions(connection)

        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(searchsession)")
        }
        assert "platform" not in columns
        assert "requested_platforms" in columns
        row = connection.execute(
            """
            SELECT
                id,
                requested_platforms,
                analysis_provider,
                analysis_degraded,
                source_variants,
                source_companies,
                force_refresh
            FROM searchsession
            """
        ).fetchone()
        assert row == ("session-1", '["official"]', "heuristic", 0, "[]", "[]", 0)
    finally:
        connection.close()
