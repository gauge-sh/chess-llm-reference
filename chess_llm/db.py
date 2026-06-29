"""Database layer: SQLAlchemy 2.0 models + a session factory.

Schema:

    games   ── one row per game
      └─ moves   ── one row per ply, with FEN before/after for rewind

(No LLM-observability tables here on purpose — bring your own platform; see README.)
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import settings


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    white_player: Mapped[str] = mapped_column(String(64))
    black_player: Mapped[str] = mapped_column(String(64))
    # in_progress | white_win | black_win | draw | abandoned
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 1-0, 0-1, 1/2-1/2
    termination: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initial_fen: Mapped[str] = mapped_column(Text)
    pgn: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    moves: Mapped[list[Move]] = relationship(
        back_populates="game", order_by="Move.ply", cascade="all, delete-orphan"
    )


class Move(Base):
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    ply: Mapped[int] = mapped_column(Integer)  # 1-based half-move count
    move_number: Mapped[int] = mapped_column(Integer)  # full-move number (1, 1, 2, 2, ...)
    color: Mapped[str] = mapped_column(String(5))  # white | black
    player: Mapped[str] = mapped_column(String(64))  # human | model id
    san: Mapped[str] = mapped_column(String(16))
    uci: Mapped[str] = mapped_column(String(8))
    fen_before: Mapped[str] = mapped_column(Text)
    fen_after: Mapped[str] = mapped_column(Text)
    is_capture: Mapped[bool] = mapped_column(Boolean, default=False)
    is_check: Mapped[bool] = mapped_column(Boolean, default=False)
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    game: Mapped[Game] = relationship(back_populates="moves")


_engine = None
_SessionLocal = None


def init_db(db_url: str | None = None):
    """Create the engine, tables, and session factory. Safe to call repeatedly.

    ``db_url`` is any SQLAlchemy URL (defaults to ``DATABASE_URL``). SQLite needs
    ``check_same_thread=False`` because the API serves sync handlers across a thread
    pool; ``pool_pre_ping`` keeps hosted/serverless Postgres connections healthy.
    """
    global _engine, _SessionLocal
    if _engine is None:
        url = db_url or settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        Base.metadata.create_all(_engine)
        _SessionLocal = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def get_session():
    """Return a new session, initializing the DB on first use."""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()
