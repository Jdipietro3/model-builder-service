from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def _set_sqlite_wal(dbapi_conn, _record):
    # WAL lets the training thread write progress while API requests read.
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine) -> None:
    """Poor-man's migration for a prototype: add columns introduced after a table
    already existed. SQLite's ADD COLUMN + DEFAULT handles this fine; idempotent
    since each column is only added if PRAGMA table_info doesn't already list it."""
    additions = {
        "datasets": [
            ("version", "INTEGER NOT NULL DEFAULT 1"),
            ("parent_dataset_id", "VARCHAR(32)"),
        ],
        "runs": [
            ("parent_run_id", "VARCHAR(32)"),
            ("tournament_id", "VARCHAR(32)"),
            ("tournament_role", "VARCHAR(20)"),
            ("tournament_interpreted", "BOOLEAN NOT NULL DEFAULT 0"),
        ],
        "projects": [
            ("recommended_run_id", "VARCHAR(32)"),
            ("recommendation_reason", "TEXT"),
            ("user_id", "VARCHAR(32)"),
        ],
    }
    with engine.connect() as conn:
        for table, columns in additions.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl_type in columns:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_runs_tournament_id ON runs(tournament_id)")
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
