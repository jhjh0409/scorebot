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


def _normalize_url(url: str) -> str:
    """Managed hosts (Railway, Heroku) hand out postgres:// URLs; SQLAlchemy
    needs the explicit psycopg3 dialect."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(database_url: str = None):
    url = _normalize_url(database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
    if url.startswith("sqlite"):
        # tests: one shared in-memory connection, usable across threads
        from sqlalchemy.pool import StaticPool

        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    # pre-ping: serverless Postgres (Neon) drops idle connections when it
    # scales to zero; without this the first request after idle 500s
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_missing_presets(session: Session) -> int:
    """Insert any seed preset whose id isn't in the table yet, so new roles
    reach existing databases. Rows the team edited or soft-deleted are never
    touched — a deliberate delete stays deleted. Returns rows inserted."""
    from ..pipeline.presets import SEED_PRESETS

    existing = {row_id for (row_id,) in session.query(PresetRow.id).all()}
    inserted = 0
    for preset in SEED_PRESETS:
        if preset.id in existing:
            continue
        session.add(
            PresetRow(id=preset.id, name=preset.name, data=preset.model_dump())
        )
        inserted += 1
    if inserted:
        session.commit()
    return inserted
