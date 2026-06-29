"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, GameSummary } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [games, setGames] = useState<GameSummary[]>([]);
  const [llm, setLlm] = useState<{ configured: boolean; model: string | null }>({ configured: false, model: null });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listGames().then(setGames).catch((e) => setError(String(e)));
    api.health().then((h) => setLlm({ configured: h.llm_configured, model: h.model })).catch(() => {});
  }, []);

  async function start(color: "white" | "black") {
    setBusy(true);
    setError(null);
    try {
      const g = await api.createGame(color);
      router.push(`/games/${g.id}`);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>New game</h1>
      <p className="muted">
        Opponent:{" "}
        {llm.configured ? <code>{llm.model}</code> : <span>not configured — set <code>LLM_*</code> in the backend</span>}
      </p>
      <div style={{ display: "flex", gap: 12, marginBottom: 28 }}>
        <button disabled={busy} onClick={() => start("white")}>Play as White</button>
        <button className="secondary" disabled={busy} onClick={() => start("black")}>Play as Black</button>
      </div>
      {error && <p style={{ color: "#ff8080" }}>{error}</p>}

      <h1>Games</h1>
      {games.length === 0 && <p className="muted">No games yet.</p>}
      <div className="panel" style={{ padding: 0 }}>
        {games.map((g) => (
          <Link key={g.id} href={`/games/${g.id}`}
            style={{ display: "flex", justifyContent: "space-between", padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--text)" }}>
            <span>#{g.id} &nbsp; {g.white_player} <span className="muted">vs</span> {g.black_player}</span>
            <span className="badge">{g.status}{g.result ? ` · ${g.result}` : ""}</span>
          </Link>
        ))}
      </div>
    </main>
  );
}
