"use client";

import { useCallback, useEffect, useState } from "react";
import Board from "@/components/Board";
import { api, GameState } from "@/lib/api";

export default function GamePage({ params }: { params: { id: string } }) {
  const id = Number(params.id);
  const [state, setState] = useState<GameState | null>(null);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If it's the LLM's turn, ask it to move and store the result.
  const triggerLlm = useCallback(async (s: GameState) => {
    if (s.is_over || s.human_color === null || !s.llm_configured) return;
    if (s.turn === s.human_color) return;
    setThinking(true);
    setError(null);
    try {
      setState(await api.llmMove(s.id));
    } catch (e) {
      setError(String(e));
    } finally {
      setThinking(false);
    }
  }, []);

  useEffect(() => {
    api.getGame(id).then((s) => { setState(s); triggerLlm(s); }).catch((e) => setError(String(e)));
  }, [id, triggerLlm]);

  async function onMove(uci: string) {
    if (!state) return;
    setError(null);
    try {
      const next = await api.playMove(id, uci);
      setState(next);
      triggerLlm(next);
    } catch (e) {
      setError(String(e));
    }
  }

  if (!state) return <p className="muted">{error ?? "Loading…"}</p>;

  const orientation = state.human_color ?? "white";
  const interactive = !thinking && !state.is_over && state.human_color !== null && state.turn === state.human_color;
  const last = state.last_llm_move;

  return (
    <main>
      <h1>Game #{state.id}</h1>
      <p className="muted">
        {state.white_player} (W) vs {state.black_player} (B)
        {state.in_check && !state.is_over ? " · check" : ""}
      </p>

      <div className="row">
        <div>
          <Board
            fen={state.fen}
            legalMoves={state.legal_moves}
            interactive={interactive}
            orientation={orientation}
            onMove={onMove}
          />
          <p style={{ marginTop: 10 }}>
            {state.is_over ? (
              <span className="badge">Game over · {state.status}{state.result ? ` (${state.result})` : ""} · {state.termination}</span>
            ) : thinking ? (
              <span className="badge">Opponent is thinking…</span>
            ) : interactive ? (
              <span className="badge">Your move ({state.turn})</span>
            ) : (
              <span className="badge">Waiting…</span>
            )}
          </p>
          {error && <p style={{ color: "#ff8080" }}>{error}</p>}
        </div>

        <div style={{ flex: 1, minWidth: 260 }}>
          {last && (
            <div className="panel" style={{ marginBottom: 16 }}>
              <strong>Last LLM move: {last.san}</strong> <code>{last.uci}</code>
              {last.fallback && <span className="badge" style={{ marginLeft: 8 }}>fallback</span>}
              {last.comment && <p className="muted" style={{ margin: "6px 0 0" }}>{last.comment}</p>}
              <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>
                {last.input_tokens}+{last.output_tokens} tokens · {last.latency_ms} ms · trace #{last.trace_id}
              </p>
            </div>
          )}

          <div className="panel">
            <strong>Moves</strong>
            <div className="movelist" style={{ marginTop: 8 }}>
              {state.moves.length === 0 && <span className="muted">No moves yet.</span>}
              {state.moves.map((m) => (
                <span key={m.ply} className="mv">
                  {m.color === "white" ? `${m.move_number}. ` : ""}
                  {m.san}{" "}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
