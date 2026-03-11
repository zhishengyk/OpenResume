import json
import sqlite3

from openresume_api.db import _migrate_candidate_profiles, _migrate_search_sessions


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
                analysis_status,
                analysis_provider,
                analysis_degraded,
                source_variants,
                source_companies,
                force_refresh
            FROM searchsession
            """
        ).fetchone()
        assert row == ("session-1", '["official"]', "ready", "heuristic", 0, "[]", "[]", 0)
    finally:
        connection.close()


def test_candidate_profile_migration_adds_enriched_columns():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            """
            CREATE TABLE candidateprofile (
                id INTEGER NOT NULL PRIMARY KEY,
                full_name TEXT NOT NULL,
                headline TEXT NOT NULL,
                summary TEXT NOT NULL,
                target_roles JSON,
                preferred_cities JSON,
                salary_floor INTEGER NOT NULL,
                years_experience INTEGER NOT NULL,
                degree TEXT NOT NULL,
                skills JSON,
                must_have_keywords JSON,
                source_filename TEXT,
                source_language TEXT NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO candidateprofile (
                id,
                full_name,
                headline,
                summary,
                target_roles,
                preferred_cities,
                salary_floor,
                years_experience,
                degree,
                skills,
                must_have_keywords,
                source_filename,
                source_language,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "Candidate",
                "Frontend Engineer",
                "summary",
                json.dumps(["Frontend Engineer"]),
                json.dumps(["Shanghai"]),
                20000,
                5,
                "Bachelor",
                json.dumps(["React"]),
                json.dumps(["React"]),
                None,
                "zh-CN",
                "2026-03-09T00:00:00",
            ),
        )

        _migrate_candidate_profiles(connection)

        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(candidateprofile)")
        }
        assert "raw_text" in columns
        assert "tech_stack" in columns
        assert "project_experiences" in columns
        assert "awards" in columns
        row = connection.execute(
            """
            SELECT raw_text, tech_stack, project_experiences, awards
            FROM candidateprofile
            """
        ).fetchone()
        assert row == ("", "[]", "[]", "[]")
    finally:
        connection.close()
