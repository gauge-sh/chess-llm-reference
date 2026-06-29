"""Game orchestration: connects the engine, persistence, and the LLM player."""

from __future__ import annotations

from dataclasses import dataclass

from . import repository
from .engine import ChessEngine
from .llm import Player
from .logging_setup import get_logger

log = get_logger("game")

HUMAN = "human"


@dataclass
class GameSession:
    game_id: int
    engine: ChessEngine
    white_player: str
    black_player: str
    llm: Player | None = None

    @classmethod
    def new(cls, white_player: str, black_player: str, llm: Player | None = None) -> GameSession:
        engine = ChessEngine()
        game_id = repository.create_game(white_player, black_player, engine.fen)
        log.info(
            "game created",
            extra={"context": {"game_id": game_id, "white": white_player, "black": black_player}},
        )
        return cls(game_id, engine, white_player, black_player, llm)

    @classmethod
    def load(cls, game_id: int, llm: Player | None = None) -> GameSession | None:
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
    def human_color(self) -> str | None:
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
        """Ask the LLM for a move, apply it, and persist it."""
        assert self.llm is not None, "no LLM player configured"
        choice = self.llm.choose_move(self.engine, self.game_id)
        applied = self.engine.apply(choice.uci)
        repository.record_move(
            self.game_id, applied, player=self.llm.model, thinking=choice.thinking
        )
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
