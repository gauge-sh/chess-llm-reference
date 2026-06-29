"""Database layer: SQLAlchemy 2.0 models + a session factory.

Schema (all in one SQLite file so games, moves, and agent traces are jointly
queryable for rewind and analysis):

    games   ── one row per game
      └─ moves   ── one row per ply, with FEN before/after for rewind
      └─ traces  ── one row per LLM turn (request/response, tokens, latency)
           └─ spans  ── one row per tool call inside that turn
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    white_player: Mapped[str] = mapped_column(String(64))
    black_player: Mapped[str] = mapped_column(String(64))
    # in_progress | white_win | black_win | draw | abandoned
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    result: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 1-0, 0-1, 1/2-1/2
    termination: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    initial_fen: Mapped[str] = mapped_column(Text)
    pgn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    moves: Mapped[list["Move"]] = relationship(
        back_populates="game", order_by="Move.ply", cascade="all, delete-orphan"
    )
    traces: Mapped[list["Trace"]] = relationship(
        back_populates="game", order_by="Trace.id", cascade="all, delete-orphan"
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
    thinking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    game: Mapped["Game"] = relationship(back_populates="moves")
    trace: Mapped[Optional["Trace"]] = relationship(back_populates="move", uselist=False)


class Trace(Base):
    """One LLM turn: the full request/response envelope plus usage + latency."""

    __tablename__ = "traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    move_id: Mapped[Optional[int]] = mapped_column(ForeignKey("moves.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), default="llm_turn")
    model: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok | error
    request_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    game: Mapped["Game"] = relationship(back_populates="traces")
    move: Mapped[Optional["Move"]] = relationship(back_populates="trace")
    spans: Mapped[list["Span"]] = relationship(
        back_populates="trace", order_by="Span.sequence", cascade="all, delete-orphan"
    )


class Span(Base):
    """One tool call within a trace (e.g. get_legal_moves, make_move)."""

    __tablename__ = "spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[int] = mapped_column(ForeignKey("traces.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)  # order within the trace
    tool_name: Mapped[str] = mapped_column(String(64))
    tool_use_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tool_input: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    trace: Mapped["Trace"] = relationship(back_populates="spans")


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
