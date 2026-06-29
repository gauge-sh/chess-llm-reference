"""HTTP API over the game core (FastAPI).

Stateless: every request rehydrates the game from the DB via ``GameSession.load`` and
applies one move. This is the surface the Next.js frontend talks to; it is also a clean
example of wrapping the vendor-neutral core in a web layer.

Run:  uvicorn chess_llm.api:app --reload
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import analysis, repository
from .config import settings
from .db import init_db
from .game import HUMAN, GameSession
from .llm import LLMNotConfigured, make_player

app = FastAPI(title="Chess vs. LLM", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


# --- request bodies ----------------------------------------------------------


class NewGame(BaseModel):
    human_color: str = "white"  # "white" | "black" | "none" (LLM vs LLM)
    model: Optional[str] = None


class MoveBody(BaseModel):
    move: str  # UCI or SAN


# --- serialization -----------------------------------------------------------


def _state(session: GameSession) -> dict:
    eng = session.engine
    outcome = eng.outcome()
    return {
        "id": session.game_id,
        "white_player": session.white_player,
        "black_player": session.black_player,
        "human_color": session.human_color,
        "llm_configured": settings.llm_configured,
        "fen": eng.fen,
        "turn": eng.turn,
        "fullmove_number": eng.fullmove_number,
        "ply": eng.ply,
        "in_check": eng.board.is_check(),
        "is_over": outcome.over,
        "status": outcome.status if outcome.over else "in_progress",
        "result": outcome.result,
        "termination": outcome.termination,
        "legal_moves": [
            {"uci": m.uci, "san": m.san, "capture": m.is_capture, "check": m.is_check}
            for m in eng.legal_moves()
        ],
        "moves": [
            {"ply": m.ply, "move_number": m.move_number, "color": m.color,
             "san": m.san, "uci": m.uci, "player": m.player}
            for m in repository.get_moves(session.game_id)
        ],
    }


def _load_or_404(game_id: int, llm=None) -> GameSession:
    session = GameSession.load(game_id, llm=llm)
    if session is None:
        raise HTTPException(404, "game not found")
    return session


# --- routes ------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_configured": settings.llm_configured, "model": settings.llm_model}


@app.get("/api/games")
def list_games() -> list[dict]:
    return [
        {"id": g.id, "white_player": g.white_player, "black_player": g.black_player,
         "status": g.status, "result": g.result, "created_at": g.created_at.isoformat()}
        for g in repository.list_games()
    ]


@app.post("/api/games")
def create_game(body: NewGame) -> dict:
    model_label = body.model or settings.llm_model or "llm"
    if body.human_color == "white":
        white, black = HUMAN, model_label
    elif body.human_color == "black":
        white, black = model_label, HUMAN
    else:
        white, black = f"{model_label} (W)", f"{model_label} (B)"
    session = GameSession.new(white, black)
    return _state(session)


@app.get("/api/games/{game_id}")
def get_game(game_id: int) -> dict:
    return _state(_load_or_404(game_id))


@app.post("/api/games/{game_id}/moves")
def play_move(game_id: int, body: MoveBody) -> dict:
    session = _load_or_404(game_id)
    if session.engine.outcome().over:
        raise HTTPException(409, "game is already over")
    if session.human_color is not None and not session.is_humans_turn:
        raise HTTPException(409, "it is not the human's turn")
    try:
        session.play_human_move(body.move)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    session.maybe_finish()
    return _state(session)


@app.post("/api/games/{game_id}/llm-move")
def llm_move(game_id: int, body: NewGame | None = None) -> dict:
    if not settings.llm_configured:
        raise HTTPException(503, "LLM not configured — set LLM_BASE_URL and LLM_MODEL.")
    try:
        llm = make_player(model=body.model if body else None)
    except LLMNotConfigured as exc:
        raise HTTPException(503, str(exc))

    session = _load_or_404(game_id, llm=llm)
    if session.engine.outcome().over:
        raise HTTPException(409, "game is already over")
    if session.human_color is not None and session.is_humans_turn:
        raise HTTPException(409, "it is the human's turn, not the LLM's")

    applied, choice = session.play_llm_move()
    session.maybe_finish()
    state = _state(session)
    state["last_llm_move"] = {
        "san": applied.san, "uci": applied.uci, "comment": choice.comment,
        "fallback": choice.fallback, "input_tokens": choice.input_tokens,
        "output_tokens": choice.output_tokens, "latency_ms": choice.latency_ms,
        "trace_id": choice.trace_id,
    }
    return state


@app.get("/api/games/{game_id}/traces")
def get_traces(game_id: int) -> list[dict]:
    return [
        {"id": t.id, "move_id": t.move_id, "model": t.model, "status": t.status,
         "input_tokens": t.input_tokens, "output_tokens": t.output_tokens,
         "latency_ms": t.latency_ms,
         "spans": [
             {"tool_name": s.tool_name, "tool_input": s.tool_input,
              "tool_output": s.tool_output, "is_error": s.is_error, "latency_ms": s.latency_ms}
             for s in t.spans
         ]}
        for t in repository.get_traces(game_id)
    ]


@app.get("/api/games/{game_id}/analysis")
def get_analysis(game_id: int) -> dict:
    summary = analysis.game_summary(game_id)
    if summary is None:
        raise HTTPException(404, "game not found")
    return summary
