// Thin client for the FastAPI backend. Base URL is configurable so the frontend
// is not tied to any particular host.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface LegalMove {
  uci: string;
  san: string;
  capture: boolean;
  check: boolean;
}

export interface MoveRow {
  ply: number;
  move_number: number;
  color: string;
  san: string;
  uci: string;
  player: string;
}

export interface LastLLMMove {
  san: string;
  uci: string;
  comment: string | null;
  fallback: boolean;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  trace_id: number;
}

export interface GameState {
  id: number;
  white_player: string;
  black_player: string;
  human_color: "white" | "black" | null;
  llm_configured: boolean;
  fen: string;
  turn: "white" | "black";
  fullmove_number: number;
  ply: number;
  in_check: boolean;
  is_over: boolean;
  status: string;
  result: string | null;
  termination: string | null;
  legal_moves: LegalMove[];
  moves: MoveRow[];
  last_llm_move?: LastLLMMove;
}

export interface GameSummary {
  id: number;
  white_player: string;
  black_player: string;
  status: string;
  result: string | null;
  created_at: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ ok: boolean; llm_configured: boolean; model: string | null }>("/api/health"),
  listGames: () => req<GameSummary[]>("/api/games"),
  createGame: (human_color: "white" | "black" | "none") =>
    req<GameState>("/api/games", { method: "POST", body: JSON.stringify({ human_color }) }),
  getGame: (id: number) => req<GameState>(`/api/games/${id}`),
  playMove: (id: number, move: string) =>
    req<GameState>(`/api/games/${id}/moves`, { method: "POST", body: JSON.stringify({ move }) }),
  llmMove: (id: number) => req<GameState>(`/api/games/${id}/llm-move`, { method: "POST", body: "{}" }),
  analysis: (id: number) => req<any>(`/api/games/${id}/analysis`),
  traces: (id: number) => req<any[]>(`/api/games/${id}/traces`),
};
