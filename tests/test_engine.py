import pytest

from chess_llm.engine import ChessEngine


def test_starting_position_has_twenty_legal_moves():
    eng = ChessEngine()
    assert len(eng.legal_moves()) == 20
    assert eng.turn == "white"
    assert eng.ply == 0


def test_apply_updates_state():
    eng = ChessEngine()
    applied = eng.apply("e2e4")
    assert applied.san == "e4"
    assert applied.uci == "e2e4"
    assert applied.color == "white"
    assert eng.turn == "black"
    assert eng.ply == 1
    assert applied.fen_before != applied.fen_after


def test_accepts_san_and_uci():
    eng = ChessEngine()
    assert eng.parse_move("Nf3") is not None  # SAN
    assert eng.parse_move("g1f3") is not None  # UCI


def test_illegal_move_raises():
    eng = ChessEngine()
    with pytest.raises(ValueError):
        eng.apply("e2e5")  # not a legal pawn move


def test_scholars_mate_is_checkmate():
    eng = ChessEngine()
    for mv in ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6", "h5f7"]:
        eng.apply(mv)
    outcome = eng.outcome()
    assert outcome.over is True
    assert outcome.status == "white_win"
    assert outcome.result == "1-0"
    assert outcome.termination == "checkmate"


def test_capture_and_check_flags():
    eng = ChessEngine()
    for mv in ["e2e4", "e7e5", "f1c4", "b8c6", "d1h5", "g8f6"]:
        eng.apply(mv)
    applied = eng.apply("h5f7")  # Qxf7#
    assert applied.is_capture is True
    assert applied.is_check is True
