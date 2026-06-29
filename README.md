# Chess vs. LLM

Play chess against an LLM (or watch it play itself). Games and moves are persisted so
positions can be rewound and analyzed. Python core + FastAPI backend + a Next.js board
UI.

Status: early, under active development. The core loop is working end to end; the
[roadmap](#roadmap) tracks what's left.

## Stack

- **Core / API** — Python 3.11+, `python-chess` for rules, SQLAlchemy, FastAPI.
- **LLM** — any chat-completions HTTP endpoint (configured by env; no SDK lock-in).
- **Frontend** — Next.js (App Router) with a hand-rolled board.
- **Storage** — SQLite by default; any SQLAlchemy-supported Postgres via `DATABASE_URL`.

## Getting started

Prerequisites: Python 3.11+, Node 20+.

```bash
python3 -m venv .venv && source .venv/bin/activate
make install                  # pip install -e ".[dev]"
cp .env.example .env          # set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
make dev                      # API on :8000
```

Frontend (separate shell):

```bash
make web                      # installs deps + runs Next.js on :3000
```

`make` targets: `install`, `dev`, `web`, `test`, `lint`, `fmt`.

### CLI

The terminal client covers everything the UI does, plus inspection:

```bash
chess-llm play                # play a game in the terminal
chess-llm llm-vs-llm          # watch the model play itself
chess-llm games               # list games
chess-llm show 1              # move list
chess-llm rewind 1 --ply 6    # board after N half-moves
chess-llm analyze 1           # per-game / per-player metrics
```

## Configuration

All via env (`.env` is loaded automatically):

- **LLM** — `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`. Any endpoint speaking the
  standard chat-completions JSON protocol. The API runs without it; LLM moves return
  503 until it's set.
- **Database** — `DATABASE_URL`, any SQLAlchemy URL. Defaults to local SQLite. For
  Postgres: `pip install -e ".[postgres]"` and set a `postgresql+psycopg://…` URL
  (`pool_pre_ping` is on, so serverless instances that drop idle connections are fine).
- **CORS** — `CORS_ORIGINS` (comma-separated), defaults to `http://localhost:3000`.

## Project layout

```
chess_llm/
  engine.py       chess rules (python-chess): legal moves, apply, end detection
  llm.py          LLM player — chat-completions tool-call loop over plain HTTP
  tools.py        the two tools (get_legal_moves / make_move) + prompts
  game.py         orchestration: load/apply a move, persist, detect game over
  repository.py   DB reads/writes
  db.py           SQLAlchemy models + engine/session
  analysis.py     rewind to any ply + per-game/player metrics
  api.py          FastAPI HTTP layer
  cli.py          terminal client
web/              Next.js board UI
tests/            engine + persistence tests
```

## Architecture

- The engine is the only authority on legality. The LLM's `make_move` tool *proposes* a
  UCI; `game.py` is the single place that validates, applies, and persists it.
- The API is stateless — each request rehydrates the game from the DB (engine state is
  reconstructed from the last move's FEN).
- Data model is `games → moves`; each move stores the FEN before/after, so rewind is a
  lookup. There are deliberately no LLM-observability tables — per-move detail (tokens,
  latency, chosen move) is logged and returned from the API so a tracing platform can be
  added later without removing a baked-in one.

## Roadmap

Near-term:

- [ ] Make `/llm-move` non-blocking (streaming or a job/poll model) — it currently holds
      the request for the whole turn, which is slow with reasoning models.
- [ ] Surface `analyze` data in the web UI (endpoint + CLI already exist).
- [ ] Pawn-promotion picker in the board UI (currently auto-queens).
- [ ] API/adapter tests (only engine + persistence are covered today).

Later:

- [ ] Move off `create_all` to managed migrations.
- [ ] Per-user scoping + auth (games are currently global).
- [ ] Replace the material-count `analyze` with real position evaluation.
- [ ] Board-flip / orientation controls in the UI.

## Development

- `make test` runs the suite (no API key needed).
- `make lint` / `make fmt` run Ruff over the backend.
- To add a different LLM backend, implement the `Player` protocol (`choose_move →
  MoveChoice`) in a new module, reuse `tools.execute_tool` so the engine still validates,
  and return it from `make_player`.
