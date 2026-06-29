# chess-llm-reference

Play chess against an LLM (or watch it play itself), with every game, move, and LLM
turn stored so you can rewind and inspect them. Python core + FastAPI + a small Next.js
board UI.

**WIP.** The core loop works end to end; lots of edges are still rough (see
[Status](#status)). Pick it up and keep going.

## Run it

Backend:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
./.venv/bin/uvicorn chess_llm.api:app --reload --port 8000
```

Frontend:

```bash
cd web
npm install
cp .env.local.example .env.local
npm run dev                   # http://localhost:3000
```

Or skip the UI and use the CLI:

```bash
./.venv/bin/python -m chess_llm.cli play          # play in the terminal
./.venv/bin/python -m chess_llm.cli llm-vs-llm    # watch it play itself
./.venv/bin/python -m chess_llm.cli games         # list games
./.venv/bin/python -m chess_llm.cli show 1
./.venv/bin/python -m chess_llm.cli rewind 1 --ply 6
./.venv/bin/python -m chess_llm.cli analyze 1
./.venv/bin/python -m chess_llm.cli traces 1
```

## Config

Two things, both env:

- **LLM** — `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`. Any endpoint that speaks the
  standard chat-completions JSON protocol. The API boots without it; LLM moves just
  return 503 until it's set.
- **Database** — `DATABASE_URL` (any SQLAlchemy URL). Defaults to local SQLite. For
  Postgres, uncomment `psycopg[binary]` in `requirements.txt` and use a
  `postgresql+psycopg://…` URL.

## Layout

```
chess_llm/
  engine.py       chess rules (python-chess): legal moves, apply, end detection
  llm.py          the LLM player — chat-completions tool-call loop over raw HTTP
  tools.py        the two tools (get_legal_moves / make_move) + prompts, vendor-neutral
  game.py         orchestration: load/apply a move, persist, detect game over
  repository.py   all DB reads/writes
  db.py           SQLAlchemy models + engine/session
  analysis.py     rewind to any ply + per-game/player metrics
  api.py          FastAPI HTTP layer
  cli.py          terminal client
web/              Next.js board UI (hand-rolled board, click-to-move)
tests/            engine + persistence tests
```

Data model: `games → moves` (each move stores FEN before/after, so rewind is just a
lookup) and `games → traces → spans` (one trace per LLM turn, one span per tool call,
linked to the move it produced).

## Status

Works:

- Human vs LLM and LLM vs LLM, both CLI and web.
- Moves + LLM traces persisted; rewind and `analyze`/`traces` read back fine.
- LLM drives the game through tool calls; engine validates every move; illegal moves
  bounce back and it retries.

Rough / not done yet:

- **`/llm-move` is synchronous** — blocks for the whole turn (20s+ on reasoning
  models). Needs streaming or a job/poll model before it's pleasant in the UI.
- **No API/adapter tests** — only the engine and persistence are covered.
- **Frontend gaps**: pawn promotion auto-queens (no picker); no board-flip; traces and
  analysis aren't surfaced in the UI yet (endpoints exist, CLI shows them).
- **No auth / multi-user** — games are global; `repository` would need per-user scoping.
- **Schema is `create_all` on startup** — no migrations.
- **Fallback is crude** — on an LLM/API error it just plays the first legal move and
  flags the turn; fine for not crashing, not for quality.
- `analyze` is material-only (piece counts), not a real position evaluation.

## Notes for whoever continues this

- The LLM is a swappable adapter: implement the `Player` protocol (`choose_move →
  MoveChoice`) in a new module, reuse `tools.execute_tool` so the engine still
  validates, and return it from `make_player`. Nothing else should need to change.
- Tests run without any API key: `./.venv/bin/python -m pytest -q`.
