"use client";

import { useMemo, useState } from "react";
import { LegalMove } from "@/lib/api";

const GLYPH: Record<string, string> = {
  K: "♚", Q: "♛", R: "♜", B: "♝", N: "♞", P: "♟",
  k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
};

// Parse the placement field of a FEN into an 8x8 array (rank 8 first), each cell a
// piece letter or null.
function parseFen(fen: string): (string | null)[][] {
  const placement = fen.split(" ")[0];
  return placement.split("/").map((rank) => {
    const row: (string | null)[] = [];
    for (const ch of rank) {
      if (/\d/.test(ch)) for (let i = 0; i < Number(ch); i++) row.push(null);
      else row.push(ch);
    }
    return row;
  });
}

const FILES = ["a", "b", "c", "d", "e", "f", "g", "h"];

export default function Board({
  fen,
  legalMoves,
  interactive,
  orientation,
  onMove,
}: {
  fen: string;
  legalMoves: LegalMove[];
  interactive: boolean;
  orientation: "white" | "black";
  onMove: (uci: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const board = useMemo(() => parseFen(fen), [fen]);

  // squares reachable from the selected square
  const targets = useMemo(() => {
    if (!selected) return new Map<string, boolean>();
    const m = new Map<string, boolean>();
    for (const mv of legalMoves) {
      if (mv.uci.slice(0, 2) === selected) m.set(mv.uci.slice(2, 4), mv.capture);
    }
    return m;
  }, [selected, legalMoves]);

  const fromSquares = useMemo(() => new Set(legalMoves.map((m) => m.uci.slice(0, 2))), [legalMoves]);

  // rows/cols in display order (flip for black)
  const rows = orientation === "white" ? [0, 1, 2, 3, 4, 5, 6, 7] : [7, 6, 5, 4, 3, 2, 1, 0];
  const cols = orientation === "white" ? [0, 1, 2, 3, 4, 5, 6, 7] : [7, 6, 5, 4, 3, 2, 1, 0];

  function squareName(r: number, c: number): string {
    return FILES[c] + (8 - r);
  }

  function handleClick(sq: string, piece: string | null) {
    if (!interactive) return;
    if (selected) {
      if (sq === selected) { setSelected(null); return; }
      // try to complete a move; prefer queen promotion when applicable
      const candidates = legalMoves.filter((m) => m.uci.slice(0, 2) === selected && m.uci.slice(2, 4) === sq);
      if (candidates.length) {
        const promo = candidates.find((m) => m.uci.endsWith("q")) ?? candidates[0];
        onMove(promo.uci);
        setSelected(null);
        return;
      }
      // clicked elsewhere: reselect if it's a movable piece, else clear
      setSelected(fromSquares.has(sq) ? sq : null);
      return;
    }
    if (fromSquares.has(sq)) setSelected(sq);
  }

  return (
    <div className="board">
      {rows.map((r) =>
        cols.map((c) => {
          const sq = squareName(r, c);
          const piece = board[r][c];
          const isLight = (r + c) % 2 === 0;
          const target = targets.has(sq);
          return (
            <div
              key={sq}
              className={`sq ${isLight ? "light" : "dark"} ${selected === sq ? "selected" : ""}`}
              onClick={() => handleClick(sq, piece)}
              title={sq}
            >
              {piece && (
                <span className={`piece ${piece === piece.toUpperCase() ? "white" : "black"}`}>
                  {GLYPH[piece]}
                </span>
              )}
              {target && !piece && <span className="dot" />}
              {target && piece && <span className="ring" />}
            </div>
          );
        })
      )}
    </div>
  );
}
