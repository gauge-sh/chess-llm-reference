"""Move tools and prompts, independent of any LLM vendor.

The LLM player is given two tools (``get_legal_moves`` / ``make_move``) and executes
them through :func:`execute_tool`, so the engine stays the single authority on legality
and the trace/span shape is identical no matter which gateway or model is configured.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .engine import ChessEngine

TOOL_GET_LEGAL_MOVES = "get_legal_moves"
TOOL_MAKE_MOVE = "make_move"

_GET_LEGAL_MOVES_DESC = (
    "List every legal move in the current position. Returns each move in both UCI "
    "(e.g. 'e2e4', 'e7e8q' for promotion) and SAN (e.g. 'Nf3'), and flags captures and "
    "checks. Call this before deciding so you only consider legal moves."
)
_MAKE_MOVE_DESC = (
    "Play exactly one move and end your turn. Provide the move in UCI notation "
    "(from-square + to-square, plus a promotion piece letter if promoting, e.g. 'e2e4' "
    "or 'e7e8q'). The move must be legal; an illegal move is rejected and you must retry."
)
_MAKE_MOVE_PARAMS = {
    "type": "object",
    "properties": {
        "uci": {"type": "string", "description": "Move in UCI notation, e.g. 'g1f3'."},
        "comment": {"type": "string", "description": "Optional one-line rationale for the move."},
    },
    "required": ["uci"],
    "additionalProperties": False,
}
_EMPTY_PARAMS = {"type": "object", "properties": {}, "additionalProperties": False}

SYSTEM_PROMPT = (
    "You are a strong chess engine playing a real game. On each turn you are given the "
    "current position. Call get_legal_moves to see your options, reason briefly about the "
    "best practical move (material, king safety, development, tactics), then call make_move "
    "exactly once with a legal UCI move to end your turn. Always play a legal move."
)


def tool_specs() -> list[dict]:
    """Function/tool specs in the standard chat-completions shape understood by
    compatible endpoints."""
    return [
        {"type": "function", "function": {"name": TOOL_GET_LEGAL_MOVES, "description": _GET_LEGAL_MOVES_DESC, "parameters": _EMPTY_PARAMS}},
        {"type": "function", "function": {"name": TOOL_MAKE_MOVE, "description": _MAKE_MOVE_DESC, "parameters": _MAKE_MOVE_PARAMS}},
    ]


@dataclass
class ToolOutcome:
    output: dict
    is_error: bool
    picked_uci: Optional[str] = None
    comment: Optional[str] = None


def execute_tool(engine: ChessEngine, name: str, tool_input: dict) -> ToolOutcome:
    """Run one tool against the engine. Never mutates the board (game.py applies the move)."""
    if name == TOOL_GET_LEGAL_MOVES:
        return ToolOutcome(
            output={
                "fen": engine.fen,
                "turn": engine.turn,
                "legal_moves": [
                    {"uci": m.uci, "san": m.san, "capture": m.is_capture, "check": m.is_check}
                    for m in engine.legal_moves()
                ],
            },
            is_error=False,
        )
    if name == TOOL_MAKE_MOVE:
        uci = str((tool_input or {}).get("uci", "")).strip()
        mv = engine.parse_move(uci)
        if mv is None:
            return ToolOutcome(
                output={
                    "ok": False,
                    "error": f"{uci!r} is not legal here. Call get_legal_moves and pick a 'uci' from the list.",
                },
                is_error=True,
            )
        return ToolOutcome(
            output={"ok": True, "played": mv.uci()},
            is_error=False,
            picked_uci=mv.uci(),
            comment=(tool_input or {}).get("comment"),
        )
    return ToolOutcome(output={"error": f"unknown tool {name!r}"}, is_error=True)


def position_prompt(engine: ChessEngine) -> str:
    return (
        f"You are playing as {engine.turn.upper()}.\n\n"
        f"FEN: {engine.fen}\n"
        f"Move number: {engine.fullmove_number}\n\n"
        f"Board (uppercase = White, lowercase = Black):\n{engine.ascii_board()}\n\n"
        "It is your turn. Inspect the legal moves, then play one."
    )


@dataclass
class MoveChoice:
    uci: str
    thinking: str
    comment: Optional[str]
    trace_id: int
    fallback: bool  # True if the player (not the model) had to pick a legal move
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass
class TurnTrace:
    """Accumulates spans + usage for one turn as the tool loop runs."""

    spans: list[dict] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def add_span(self, name: str, tool_use_id: Optional[str], tool_input: Any, outcome: ToolOutcome, started: float) -> None:
        self.spans.append(
            {
                "tool_name": name,
                "tool_use_id": tool_use_id,
                "tool_input": tool_input,
                "tool_output": outcome.output,
                "is_error": outcome.is_error,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        )
