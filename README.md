# Chess vs. LLM — a vendor-neutral full-stack reference

A working full-stack app you can fork as a building block: a chess engine, an LLM
opponent driven by **tool calls**, persistence, AI-agent **observability**, an HTTP
API, and a **Next.js** board UI.

Every vendor decision is an interchangeable adapter behind a config seam. There are
**two knobs** and nothing is hardcoded:

| Seam | How you choose a vendor | Works with |
|---|---|---|
| **LLM** | `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | Any endpoint that speaks the standard chat-completions JSON protocol |
| **Database** | `DATABASE_URL` (any SQLAlchemy URL) | Local SQLite out of the box; any hosted Postgres by swapping the URL |

The point: swap the gateway or the database by editing `.env`, never the code.

## Architecture

```
web/  (Next.js)  ──HTTP──▶  chess_llm/api.py  (FastAPI)
                                  │
                 ┌────────────────┼─────────────────┐
              game.py          llm.py            analysis.py
           (orchestration)  (chat-completions     (rewind +
                                tool-call loop)     metrics)
                 │                │                   │
              engine.py      repository.py  ◀──────────┘
            (python-chess)   (persistence)
                                  │
                               db.py  ── DATABASE_URL (SQLite | Postgres | …)
```

Design notes:

- **The engine is the only authority on legality.** The LLM's `make_move` tool only
  *proposes* a UCI; `game.py` is the single place that validates + applies + persists.
- **Observability is a write-through spine.** Each LLM turn is a `trace` with one
  `span` per tool call, linked to the `move` it produced — all in the same DB:

  ```
  games ─┬─ moves   (fen_before/fen_after per ply → enables rewind)
         └─ traces  (one per LLM turn: request, response, tokens, latency, status)
              └─ spans  (one per tool call: name, input, output, errors)
  ```
- **The LLM is a swappable adapter.** `llm.py` speaks the standard chat-completions
  JSON protocol over plain HTTP (no third-party client SDK). To use an endpoint with a
  different wire format, implement the `Player` protocol in a new module and return it
  from `make_player`.

## Quick start

### 1. Backend

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL (and DATABASE_URL if not SQLite)
./.venv/bin/uvicorn chess_llm.api:app --reload --port 8000
```

The API boots even without LLM config; `/api/llm-move` returns 503 until you set it.

### 2. Frontend

```bash
cd web
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                        # http://localhost:3000
```

Open the app, start a game as White or Black, and play click-to-move against the
configured model. The sidebar shows the LLM's last move, its rationale, token spend,
latency, and trace id.

### CLI (no frontend needed)

```bash
./.venv/bin/python -m chess_llm.cli play              # play in the terminal
./.venv/bin/python -m chess_llm.cli llm-vs-llm        # watch the model play itself
./.venv/bin/python -m chess_llm.cli games             # list games
./.venv/bin/python -m chess_llm.cli show 1            # move list
./.venv/bin/python -m chess_llm.cli rewind 1 --ply 6  # board after N half-moves
./.venv/bin/python -m chess_llm.cli analyze 1         # performance metrics
./.venv/bin/python -m chess_llm.cli traces 1          # agent traces + tool calls
```

## HTTP API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | LLM-configured status |
| `GET` | `/api/games` | list games |
| `POST` | `/api/games` | create (`{human_color}`) |
| `GET` | `/api/games/{id}` | full state (FEN, legal moves, history) |
| `POST` | `/api/games/{id}/moves` | apply a human move (`{move}`, UCI or SAN) |
| `POST` | `/api/games/{id}/llm-move` | ask the LLM to move |
| `GET` | `/api/games/{id}/traces` | agent traces + spans |
| `GET` | `/api/games/{id}/analysis` | per-player + LLM metrics |

## Choosing your vendors

**LLM** — set three env vars; the code is identical for every endpoint:

```bash
LLM_BASE_URL=https://<your-host>/v1
LLM_API_KEY=...            # blank is fine for endpoints that need no auth
LLM_MODEL=<model-id>
```

**Database** — default is SQLite (`sqlite:///./chess.db`). For hosted Postgres,
uncomment `psycopg[binary]` in `requirements.txt` and set:

```bash
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

`pool_pre_ping` is on, so serverless Postgres that drops idle connections is fine.
Tables are auto-created on startup; add a schema-migration tool if you need migrations
in production.

## Tests

```bash
./.venv/bin/python -m pytest -q     # engine rules, persistence, rewind, analysis — no API key needed
```

## Extending

- **New LLM adapter** (different wire format): implement `Player.choose_move` returning
  a `MoveChoice`, reuse `tools.execute_tool` so the engine still validates moves, and
  return it from `make_player`. Nothing else changes.
- **External tracing** (e.g. an analytics or error platform): traces already live in
  the DB — add a sink inside `repository.record_trace`.
- **Stronger analysis**: drop in a dedicated chess engine to score moves and turn
  `analyze` into real blunder detection.
- **Auth / multi-user**: add per-user scoping in `repository` and an auth layer in
  `api.py`; the rest is unaffected.
