"""Game orchestration: ties the engine, persistence, and the LLM player together."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .llm import Player
from .engine import ChessEngine
from .logging_setup import get_logger
from . import repository

log = get_logger("game")

HUMAN = "human"


@dataclass
class GameSession:
    game_id: int
    engine: ChessEngine
    white_player: str
    black_player: str
    llm: Optional[Player] = None

    @classmethod
    def new(cls, white_player: str, black_player: str, llm: Optional[Player] = None) -> "GameSession":
        engine = ChessEngine()
        game_id = repository.create_game(white_player, black_player, engine.fen)
        log.info(
            "game created",
            extra={"context": {"game_id": game_id, "white": white_player, "black": black_player}},
        )
        return cls(game_id, engine, white_player, black_player, llm)

    @classmethod
    def load(cls, game_id: int, llm: Optional[Player] = None) -> Optional["GameSession"]:
        """Rehydrate an existing game from the DB (engine state from the last move's FEN)."""
        game = repository.get_game(game_id)
        if game is None:
            return None
        moves = repository.get_moves(game_id)
        fen = moves[-1].fen_after if moves else game.initial_fen
        return cls(game_id, ChessEngine(fen), game.white_player, game.black_player, llm)

    @property
    def current_player_label(self) -> str:
        return self.white_player if self.engine.turn == "white" else self.black_player

    @property
    def human_color(self) -> Optional[str]:
        if self.white_player == HUMAN:
            return "white"
        if self.black_player == HUMAN:
            return "black"
        return None  # LLM vs LLM

    @property
    def is_humans_turn(self) -> bool:
        return self.engine.turn == self.human_color

    def play_human_move(self, move_str: str) -> None:
        """Apply a human move (UCI or SAN); raises ValueError if illegal."""
        applied = self.engine.apply(move_str)
        repository.record_move(self.game_id, applied, player=HUMAN)

    def play_llm_move(self):
        """Ask the LLM for a move, apply it, and link the trace to the move row."""
        assert self.llm is not None, "no LLM player configured"
        choice = self.llm.choose_move(self.engine, self.game_id)
        applied = self.engine.apply(choice.uci)
        move_id = repository.record_move(
            self.game_id, applied, player=self.llm.model, thinking=choice.thinking
        )
        repository.link_trace_to_move(choice.trace_id, move_id)
        return applied, choice

    def maybe_finish(self) -> bool:
        """If the game is over, persist the outcome. Returns True if finished."""
        outcome = self.engine.outcome()
        if not outcome.over:
            return False
        pgn = self.engine.to_pgn(self.white_player, self.black_player, outcome.result)
        repository.finish_game(
            self.game_id, outcome.status, outcome.result, outcome.termination, pgn
        )
        log.info(
            "game finished",
            extra={
                "context": {
                    "game_id": self.game_id,
                    "status": outcome.status,
                    "result": outcome.result,
                    "termination": outcome.termination,
                }
            },
        )
        return True

    def abandon(self) -> None:
        pgn = self.engine.to_pgn(self.white_player, self.black_player, None)
        repository.finish_game(self.game_id, "abandoned", None, "abandoned", pgn)
