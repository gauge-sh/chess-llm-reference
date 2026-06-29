"""Persistence operations for games, moves, and traces.

Keeps SQLAlchemy session handling in one place so the engine/agent/CLI never touch
the ORM directly.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from .db import Game, Move, Span, Trace, get_session
from .engine import AppliedMove


def create_game(white_player: str, black_player: str, initial_fen: str) -> int:
    with get_session() as s:
        game = Game(
            white_player=white_player,
            black_player=black_player,
            initial_fen=initial_fen,
            status="in_progress",
        )
        s.add(game)
        s.commit()
        return game.id


def record_move(
    game_id: int,
    applied: AppliedMove,
    player: str,
    thinking: Optional[str] = None,
) -> int:
    with get_session() as s:
        move = Move(
            game_id=game_id,
            ply=applied.ply,
            move_number=applied.move_number,
            color=applied.color,
            player=player,
            san=applied.san,
            uci=applied.uci,
            fen_before=applied.fen_before,
            fen_after=applied.fen_after,
            is_capture=applied.is_capture,
            is_check=applied.is_check,
            thinking=thinking,
        )
        s.add(move)
        s.commit()
        return move.id


def record_trace(
    game_id: int,
    model: str,
    *,
    move_id: Optional[int] = None,
    kind: str = "llm_turn",
    status: str = "ok",
    request: object = None,
    response: object = None,
    error: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    spans: Optional[list[dict]] = None,
) -> int:
    """Persist one LLM turn and its tool-call spans."""
    with get_session() as s:
        trace = Trace(
            game_id=game_id,
            move_id=move_id,
            kind=kind,
            model=model,
            status=status,
            request_json=_dumps(request),
            response_json=_dumps(response),
            error=error,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        s.add(trace)
        s.flush()  # assign trace.id
        for i, span in enumerate(spans or []):
            s.add(
                Span(
                    trace_id=trace.id,
                    sequence=i,
                    tool_name=span.get("tool_name", "?"),
                    tool_use_id=span.get("tool_use_id"),
                    tool_input=_dumps(span.get("tool_input")),
                    tool_output=_dumps(span.get("tool_output")),
                    is_error=bool(span.get("is_error", False)),
                    latency_ms=int(span.get("latency_ms", 0)),
                )
            )
        s.commit()
        return trace.id


def link_trace_to_move(trace_id: int, move_id: int) -> None:
    with get_session() as s:
        trace = s.get(Trace, trace_id)
        if trace is not None:
            trace.move_id = move_id
            s.commit()


def finish_game(
    game_id: int, status: str, result: Optional[str], termination: Optional[str], pgn: str
) -> None:
    with get_session() as s:
        game = s.get(Game, game_id)
        if game is None:
            return
        game.status = status
        game.result = result
        game.termination = termination
        game.pgn = pgn
        game.completed_at = datetime.now(timezone.utc)
        s.commit()


# --- read side ---------------------------------------------------------------


def get_game(game_id: int) -> Optional[Game]:
    with get_session() as s:
        return s.get(Game, game_id)


def list_games() -> list[Game]:
    with get_session() as s:
        return list(s.query(Game).order_by(Game.id.desc()).all())


def get_moves(game_id: int) -> list[Move]:
    with get_session() as s:
        return list(s.query(Move).filter_by(game_id=game_id).order_by(Move.ply).all())


def get_traces(game_id: int) -> list[Trace]:
    with get_session() as s:
        traces = list(s.query(Trace).filter_by(game_id=game_id).order_by(Trace.id).all())
        for t in traces:
            _ = t.spans  # force-load while the session is open
        return traces


def _dumps(obj: object) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=str)
