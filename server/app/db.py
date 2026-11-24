"""Database engine and the per-request session dependency."""

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from . import config

engine = create_engine(
    config.DATABASE_URL,
    # SQLite + FastAPI's thread pool: allow use across threads.
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {},
)


def create_tables() -> None:
    from . import models  # noqa: F401  (registers the tables)

    SQLModel.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one database session per request."""
    with Session(engine) as db:
        yield db
