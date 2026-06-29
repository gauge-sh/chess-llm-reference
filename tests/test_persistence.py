from chess_llm import analysis, repository
from chess_llm.engine import ChessEngine


def _play_game() -> int:
    eng = ChessEngine()
    game_id = repository.create_game("human", "claude-test", eng.fen)
    for mv in ["e2e4", "e7e5", "g1f3", "b8c6"]:
        applied = eng.apply(mv)
        repository.record_move(game_id, applied, player="human")
    return game_id


def test_moves_round_trip():
    game_id = _play_game()
    moves = repository.get_moves(game_id)
    assert [m.san for m in moves] == ["e4", "e5", "Nf3", "Nc6"]
    assert moves[0].color == "white"
    assert moves[1].color == "black"
    assert all(m.ply == i + 1 for i, m in enumerate(moves))


def test_rewind_to_ply():
    game_id = _play_game()
    start = analysis.position_at_ply(game_id, 0)
    assert start is not None and start.last_move_san is None

    after_two = analysis.position_at_ply(game_id, 2)
    assert after_two is not None
    assert after_two.last_move_san == "e5"
    # Black just moved, so it is White to move in the reconstructed FEN.
    assert " w " in after_two.fen


def test_trace_with_spans_round_trip():
    game_id = _play_game()
    trace_id = repository.record_trace(
        game_id=game_id,
        model="claude-test",
        input_tokens=120,
        output_tokens=30,
        latency_ms=900,
        spans=[
            {"tool_name": "get_legal_moves", "tool_use_id": "t1", "tool_input": {}, "tool_output": {"n": 20}},
            {"tool_name": "make_move", "tool_use_id": "t2", "tool_input": {"uci": "e2e4"}, "tool_output": {"ok": True}},
        ],
    )
    traces = repository.get_traces(game_id)
    assert any(t.id == trace_id for t in traces)
    t = next(t for t in traces if t.id == trace_id)
    assert [sp.tool_name for sp in t.spans] == ["get_legal_moves", "make_move"]


def test_game_summary_metrics():
    game_id = _play_game()
    repository.record_trace(
        game_id=game_id, model="claude-test", input_tokens=100, output_tokens=20, latency_ms=500,
        spans=[{"tool_name": "make_move", "tool_input": {"uci": "zz"}, "tool_output": {"ok": False}, "is_error": True},
               {"tool_name": "make_move", "tool_input": {"uci": "e7e5"}, "tool_output": {"ok": True}}],
    )
    summary = analysis.game_summary(game_id)
    assert summary is not None
    assert summary["total_plies"] == 4
    assert summary["white"]["moves"] == 2
    assert summary["black"]["moves"] == 2
    assert summary["llm"]["illegal_move_attempts"] == 1
    assert summary["llm"]["input_tokens"] == 100
