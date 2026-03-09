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


def _migrate_job_listings(connection: sqlite3.Connection) -> None:
    if not _table_columns(connection, "joblisting"):
        return

    _add_column_if_missing(connection, "joblisting", "detail_url", "detail_url TEXT")
    _add_column_if_missing(connection, "joblisting", "apply_url", "apply_url TEXT")
    _add_column_if_missing(
        connection,
        "joblisting",
        "source_company_url",
        "source_company_url TEXT",
    )
    _add_column_if_missing(
        connection,
        "joblisting",
        "apply_requires_login",
        "apply_requires_login INTEGER NOT NULL DEFAULT 0",
    )
    connection.execute(
        "UPDATE joblisting SET detail_url = url WHERE detail_url IS NULL OR detail_url = ''"
    )


def _migrate_job_matches(connection: sqlite3.Connection) -> None:
    if not _table_columns(connection, "jobmatch"):
        return

    _add_column_if_missing(
        connection,
        "jobmatch",
        "analysis_provider",
        "analysis_provider TEXT NOT NULL DEFAULT 'heuristic'",
    )
    _add_column_if_missing(
        connection,
        "jobmatch",
        "analysis_degraded",
        "analysis_degraded INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        connection,
        "jobmatch",
        "analysis_notice",
        "analysis_notice TEXT",
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
    _add_column_if_missing(connection, "applicationattempt", "launch_url", "launch_url TEXT")
    _add_column_if_missing(
        connection,
        "applicationattempt",
        "context",
        "context TEXT NOT NULL DEFAULT '{}'",
    )


def _migrate_llm_cache(connection: sqlite3.Connection) -> None:
    if not _table_columns(connection, "llmanalysiscache"):
        return
    _add_column_if_missing(
        connection,
        "llmanalysiscache",
        "provider",
        "provider TEXT NOT NULL DEFAULT 'heuristic'",
    )


def run_compat_migrations() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    try:
        _migrate_search_sessions(connection)
        _migrate_job_listings(connection)
        _migrate_job_matches(connection)
        _migrate_application_attempts(connection)
        _migrate_llm_cache(connection)
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    run_compat_migrations()
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
