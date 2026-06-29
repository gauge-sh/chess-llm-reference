"""Persistence operations for games and moves.

Keeps SQLAlchemy session handling in one place so the engine/LLM/CLI never touch the
ORM directly.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .db import Game, Move, get_session
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
    thinking: str | None = None,
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


def finish_game(
    game_id: int, status: str, result: str | None, termination: str | None, pgn: str
) -> None:
    with get_session() as s:
        game = s.get(Game, game_id)
        if game is None:
            return
        game.status = status
        game.result = result
        game.termination = termination
        game.pgn = pgn
        game.completed_at = datetime.now(UTC)
        s.commit()


# --- read side ---------------------------------------------------------------


def get_game(game_id: int) -> Game | None:
    with get_session() as s:
        return s.get(Game, game_id)


def list_games() -> list[Game]:
    with get_session() as s:
        return list(s.query(Game).order_by(Game.id.desc()).all())


def get_moves(game_id: int) -> list[Move]:
    with get_session() as s:
        return list(s.query(Move).filter_by(game_id=game_id).order_by(Move.ply).all())
