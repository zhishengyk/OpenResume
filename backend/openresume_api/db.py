from collections.abc import Iterator
import json
import sqlite3

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(connection, table_name):
        return set()
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    if column_name in _table_columns(connection, table_name):
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def _migrate_search_sessions(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "searchsession")
    if not columns:
        return

    if "platform" in columns:
        requested_platforms_expr = (
            "requested_platforms" if "requested_platforms" in columns else "NULL"
        )
        analysis_provider_expr = (
            "analysis_provider" if "analysis_provider" in columns else "'heuristic'"
        )
        analysis_degraded_expr = (
            "analysis_degraded" if "analysis_degraded" in columns else "0"
        )
        analysis_notice_expr = (
            "analysis_notice" if "analysis_notice" in columns else "NULL"
        )
        rows = connection.execute(
            f"""
            SELECT
                id,
                platform,
                {requested_platforms_expr},
                mode,
                status,
                job_targets,
                cities,
                salary_floor,
                must_have_keywords,
                blocked_reason,
                summary,
                {analysis_provider_expr},
                {analysis_degraded_expr},
                {analysis_notice_expr},
                created_at,
                updated_at
            FROM searchsession
            """
        ).fetchall()
        connection.execute(
            """
            CREATE TABLE searchsession_v2 (
                id TEXT NOT NULL PRIMARY KEY,
                requested_platforms TEXT,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                job_targets JSON,
                cities JSON,
                salary_floor INTEGER NOT NULL,
                must_have_keywords JSON,
                blocked_reason TEXT,
                summary TEXT,
                analysis_provider TEXT NOT NULL DEFAULT 'heuristic',
                analysis_degraded INTEGER NOT NULL DEFAULT 0,
                analysis_notice TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        for row in rows:
            (
                session_id,
                platform,
                requested_platforms,
                mode,
                status,
                job_targets,
                cities,
                salary_floor,
                must_have_keywords,
                blocked_reason,
                summary,
                analysis_provider,
                analysis_degraded,
                analysis_notice,
                created_at,
                updated_at,
            ) = row
            normalized_platforms = requested_platforms or json.dumps(
                [platform] if platform else [],
                ensure_ascii=False,
            )
            connection.execute(
                """
                INSERT INTO searchsession_v2 (
                    id,
                    requested_platforms,
                    mode,
                    status,
                    job_targets,
                    cities,
                    salary_floor,
                    must_have_keywords,
                    blocked_reason,
                    summary,
                    analysis_provider,
                    analysis_degraded,
                    analysis_notice,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    normalized_platforms,
                    mode,
                    status,
                    job_targets,
                    cities,
                    salary_floor,
                    must_have_keywords,
                    blocked_reason,
                    summary,
                    analysis_provider or "heuristic",
                    analysis_degraded or 0,
                    analysis_notice,
                    created_at,
                    updated_at,
                ),
            )
        connection.execute("DROP TABLE searchsession")
        connection.execute("ALTER TABLE searchsession_v2 RENAME TO searchsession")
        columns = _table_columns(connection, "searchsession")

    _add_column_if_missing(
        connection,
        "searchsession",
        "requested_platforms",
        "requested_platforms TEXT",
    )
    _add_column_if_missing(
        connection,
        "searchsession",
        "analysis_provider",
        "analysis_provider TEXT NOT NULL DEFAULT 'heuristic'",
    )
    _add_column_if_missing(
        connection,
        "searchsession",
        "analysis_degraded",
        "analysis_degraded INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        connection,
        "searchsession",
        "analysis_notice",
        "analysis_notice TEXT",
    )

    if "platform" in columns:
        rows = connection.execute(
            "SELECT id, platform, requested_platforms FROM searchsession"
        ).fetchall()
        for session_id, platform, requested_platforms in rows:
            if requested_platforms:
                continue
            platforms = [platform] if platform else []
            connection.execute(
                "UPDATE searchsession SET requested_platforms = ? WHERE id = ?",
                (json.dumps(platforms, ensure_ascii=False), session_id),
            )


def _migrate_application_attempts(connection: sqlite3.Connection) -> None:
    if not _table_columns(connection, "applicationattempt"):
        return

    _add_column_if_missing(
        connection,
        "applicationattempt",
        "verification_url",
        "verification_url TEXT",
    )
    _add_column_if_missing(
        connection,
        "applicationattempt",
        "launch_url",
        "launch_url TEXT",
    )
    _add_column_if_missing(
        connection,
        "applicationattempt",
        "context",
        "context TEXT NOT NULL DEFAULT '{}'",
    )


def _drop_table_if_columns_mismatch(
    connection: sqlite3.Connection,
    table_name: str,
    expected_columns: set[str],
) -> None:
    columns = _table_columns(connection, table_name)
    if not columns:
        return
    if columns == expected_columns:
        return
    connection.execute(f"DROP TABLE {table_name}")


def _rebuild_derived_tables_if_needed(connection: sqlite3.Connection) -> None:
    _drop_table_if_columns_mismatch(
        connection,
        "jobmatch",
        {
            "id",
            "session_id",
            "job_id",
            "rule_score",
            "llm_score",
            "final_score",
            "highlights",
            "missing_keywords",
            "risk_flags",
            "llm_summary",
            "cached_llm",
            "analysis_provider",
            "analysis_degraded",
            "analysis_notice",
            "created_at",
            "updated_at",
        },
    )
    _drop_table_if_columns_mismatch(
        connection,
        "joblisting",
        {
            "id",
            "session_id",
            "platform",
            "source_company",
            "source_site",
            "job_id",
            "title",
            "department",
            "employment_type",
            "location_raw",
            "location_city",
            "location_country",
            "remote_type",
            "description_html",
            "description_text",
            "requirements_text",
            "skills_extracted",
            "posted_at",
            "apply_url",
            "salary_raw",
            "salary_min",
            "salary_max",
            "lang",
            "crawl_time",
            "raw_payload",
            "created_at",
        },
    )
    _drop_table_if_columns_mismatch(
        connection,
        "llmanalysiscache",
        {
            "cache_key",
            "provider",
            "platform",
            "source_site",
            "job_id",
            "content_hash",
            "llm_score",
            "highlights",
            "missing_keywords",
            "risk_flags",
            "llm_summary",
            "updated_at",
        },
    )


def run_compat_migrations() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    try:
        _migrate_search_sessions(connection)
        _migrate_application_attempts(connection)
        _rebuild_derived_tables_if_needed(connection)
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    run_compat_migrations()
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
