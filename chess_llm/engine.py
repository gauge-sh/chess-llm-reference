"""A thin chess engine built on python-chess.

Owns the rules: legal-move generation, applying moves, and detecting game end.
Everything else (persistence, the LLM, the CLI) talks to the board through here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chess
import chess.pgn


@dataclass
class LegalMove:
    uci: str
    san: str
    is_capture: bool
    is_check: bool


@dataclass
class AppliedMove:
    ply: int
    move_number: int
    color: str  # "white" | "black"
    uci: str
    san: str
    fen_before: str
    fen_after: str
    is_capture: bool
    is_check: bool


@dataclass
class GameOutcome:
    over: bool
    result: Optional[str]  # "1-0" | "0-1" | "1/2-1/2" | None
    status: Optional[str]  # "white_win" | "black_win" | "draw" | None
    termination: Optional[str]  # e.g. "checkmate", "stalemate", "insufficient_material"


class ChessEngine:
    """Stateful wrapper around a single ``chess.Board``."""

    def __init__(self, fen: Optional[str] = None):
        self.board = chess.Board(fen) if fen else chess.Board()

    # --- introspection -------------------------------------------------------

    @property
    def fen(self) -> str:
        return self.board.fen()

    @property
    def turn(self) -> str:
        return "white" if self.board.turn == chess.WHITE else "black"

    @property
    def ply(self) -> int:
        """1-based count of half-moves played so far."""
        return len(self.board.move_stack)

    @property
    def fullmove_number(self) -> int:
        return self.board.fullmove_number

    def legal_moves(self) -> list[LegalMove]:
        moves: list[LegalMove] = []
        for mv in self.board.legal_moves:
            san = self.board.san(mv)
            is_capture = self.board.is_capture(mv)
            self.board.push(mv)
            is_check = self.board.is_check()
            self.board.pop()
            moves.append(LegalMove(mv.uci(), san, is_capture, is_check))
        moves.sort(key=lambda m: m.san)
        return moves

    def ascii_board(self) -> str:
        """A coordinate-labelled ASCII board from the side-to-move's reference."""
        return str(self.board)

    # --- mutation ------------------------------------------------------------

    def parse_move(self, move_str: str) -> Optional[chess.Move]:
        """Accept either UCI (e2e4) or SAN (Nf3); return None if illegal/unparsable."""
        move_str = move_str.strip()
        # Try UCI first.
        try:
            mv = chess.Move.from_uci(move_str)
            if mv in self.board.legal_moves:
                return mv
        except (ValueError, chess.InvalidMoveError):
            pass
        # Fall back to SAN.
        try:
            return self.board.parse_san(move_str)
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            return None

    def apply(self, move_str: str) -> AppliedMove:
        """Validate and play a move. Raises ValueError if it is not legal."""
        mv = self.parse_move(move_str)
        if mv is None:
            raise ValueError(f"Illegal or unparseable move: {move_str!r}")

        color = self.turn
        move_number = self.fullmove_number
        fen_before = self.fen
        san = self.board.san(mv)
        is_capture = self.board.is_capture(mv)
        self.board.push(mv)
        return AppliedMove(
            ply=self.ply,
            move_number=move_number,
            color=color,
            uci=mv.uci(),
            san=san,
            fen_before=fen_before,
            fen_after=self.fen,
            is_capture=is_capture,
            is_check=self.board.is_check(),
        )

    # --- termination ---------------------------------------------------------

    def outcome(self) -> GameOutcome:
        oc = self.board.outcome(claim_draw=True)
        if oc is None:
            return GameOutcome(False, None, None, None)

        if oc.winner is True:
            status = "white_win"
        elif oc.winner is False:
            status = "black_win"
        else:
            status = "draw"
        return GameOutcome(
            over=True,
            result=oc.result(),
            status=status,
            termination=oc.termination.name.lower(),
        )

    def to_pgn(self, white: str, black: str, result: Optional[str]) -> str:
        """Reconstruct a PGN from the move stack."""
        game = chess.pgn.Game()
        game.headers["White"] = white
        game.headers["Black"] = black
        if result:
            game.headers["Result"] = result
        node = game
        replay = chess.Board()
        for mv in self.board.move_stack:
            node = node.add_variation(mv)
            replay.push(mv)
        return str(game)
