"""Rewind and performance analysis over stored games.

Because every move stores the FEN before and after it, we can rewind to any ply
without re-deriving state, and compute simple metrics (material balance, captures,
checks) straight from the DB.
"""

from __future__ import annotations

from dataclasses import dataclass

import chess

from . import repository

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


@dataclass
class PositionAtPly:
    ply: int
    fen: str
    last_move_san: str | None
    ascii_board: str


def position_at_ply(game_id: int, ply: int) -> PositionAtPly | None:
    """Return the board state after ``ply`` half-moves (ply=0 is the start)."""
    moves = repository.get_moves(game_id)
    game = repository.get_game(game_id)
    if game is None:
        return None

    if ply <= 0:
        fen = game.initial_fen
        last_san = None
    else:
        if ply > len(moves):
            ply = len(moves)
        mv = moves[ply - 1]
        fen = mv.fen_after
        last_san = mv.san

    board = chess.Board(fen)
    return PositionAtPly(ply=ply, fen=fen, last_move_san=last_san, ascii_board=str(board))


def _material(fen: str) -> tuple[int, int]:
    board = chess.Board(fen)
    white = black = 0
    for _square, piece in board.piece_map().items():
        val = PIECE_VALUES[piece.piece_type]
        if piece.color == chess.WHITE:
            white += val
        else:
            black += val
    return white, black


def material_timeline(game_id: int) -> list[dict]:
    """Material count for each side after every ply (handy for spotting swings)."""
    moves = repository.get_moves(game_id)
    timeline = []
    for mv in moves:
        white, black = _material(mv.fen_after)
        timeline.append(
            {
                "ply": mv.ply,
                "move_number": mv.move_number,
                "color": mv.color,
                "san": mv.san,
                "white_material": white,
                "black_material": black,
                "balance": white - black,  # >0 favours White
            }
        )
    return timeline


def game_summary(game_id: int) -> dict | None:
    """Per-game and per-player performance metrics."""
    game = repository.get_game(game_id)
    if game is None:
        return None
    moves = repository.get_moves(game_id)

    def player_stats(color: str) -> dict:
        side_moves = [m for m in moves if m.color == color]
        return {
            "player": game.white_player if color == "white" else game.black_player,
            "moves": len(side_moves),
            "captures": sum(1 for m in side_moves if m.is_capture),
            "checks_given": sum(1 for m in side_moves if m.is_check),
        }

    final_white, final_black = (
        _material(moves[-1].fen_after) if moves else _material(game.initial_fen)
    )

    return {
        "game_id": game.id,
        "status": game.status,
        "result": game.result,
        "termination": game.termination,
        "total_plies": len(moves),
        "white": player_stats("white"),
        "black": player_stats("black"),
        "final_material": {
            "white": final_white,
            "black": final_black,
            "balance": final_white - final_black,
        },
    }
