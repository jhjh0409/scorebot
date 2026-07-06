"""
Database setup: Postgres holds presets/config only — never candidate data
(stateless-v1 decision). Screening results live in memory (see jobs.py).
"""

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://scorebot:scorebot@localhost:5434/scorebot"


class Base(DeclarativeBase):
    pass


class PresetRow(Base):
    """A role preset. `data` is the full Preset JSON, validated at the API edge."""

    __tablename__ = "presets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


def make_engine(database_url: str = None):
    url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if url.startswith("sqlite"):
        # tests: one shared in-memory connection, usable across threads
        from sqlalchemy.pool import StaticPool

        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_presets_if_empty(session: Session) -> int:
    """Idempotent seed of the three starter presets. Returns rows inserted."""
    from ..pipeline.presets import SEED_PRESETS

    if session.query(PresetRow).count() > 0:
        return 0
    for preset in SEED_PRESETS:
        session.add(
            PresetRow(id=preset.id, name=preset.name, data=preset.model_dump())
        )
    session.commit()
    return len(SEED_PRESETS)
