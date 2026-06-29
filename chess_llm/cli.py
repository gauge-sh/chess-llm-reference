"""Command-line interface: play against the LLM, then rewind and analyze games.

    python -m chess_llm.cli play              # play White vs the LLM
    python -m chess_llm.cli play --color black
    python -m chess_llm.cli llm-vs-llm        # watch the LLM play itself
    python -m chess_llm.cli games             # list stored games
    python -m chess_llm.cli show 1            # move list for game 1
    python -m chess_llm.cli rewind 1 --ply 6  # board after 6 half-moves
    python -m chess_llm.cli analyze 1         # per-game / per-player metrics
"""

from __future__ import annotations

import json

import click

from .llm import make_player
from .config import settings
from .db import init_db
from .game import GameSession
from . import analysis, repository


def _print_board(session: GameSession) -> None:
    click.echo()
    click.echo(session.engine.ascii_board())
    click.echo(f"\nFEN: {session.engine.fen}")
    click.echo(f"Turn: {session.engine.turn}  (move {session.engine.fullmove_number})\n")


def _announce_result(session: GameSession) -> None:
    outcome = session.engine.outcome()
    click.secho(
        f"\nGame over — {outcome.status} ({outcome.result}) by {outcome.termination}.",
        fg="green",
        bold=True,
    )
    click.echo(f"Game id {session.game_id}. Analyze with: python -m chess_llm.cli analyze {session.game_id}")


@click.group()
def cli() -> None:
    """Chess vs. an LLM, with games and moves stored locally."""
    init_db()


@cli.command()
@click.option("--color", type=click.Choice(["white", "black"]), default="white",
              help="The colour YOU play. The LLM takes the other side.")
@click.option("--model", default=None, help="Override LLM_MODEL for this game.")
def play(color: str, model: str | None) -> None:
    """Play a game against the configured LLM in the terminal."""
    llm = make_player(model=model)
    human_label, llm_label = "human", llm.model
    if color == "white":
        session = GameSession.new(human_label, llm_label, llm=llm)
    else:
        session = GameSession.new(llm_label, human_label, llm=llm)

    click.secho(f"You are {color.upper()} vs {llm.model}. Enter moves as UCI (e2e4) or SAN (Nf3).", fg="cyan")  # noqa: E501
    click.echo("Commands: 'moves' to list legal moves, 'resign' to quit.")

    while True:
        _print_board(session)
        if session.maybe_finish():
            _announce_result(session)
            return

        if session.engine.turn == color:
            move_str = click.prompt(f"Your move ({color})", type=str).strip()
            if move_str.lower() in {"resign", "quit", "q"}:
                session.abandon()
                click.secho("You resigned.", fg="yellow")
                return
            if move_str.lower() == "moves":
                legal = ", ".join(m.san for m in session.engine.legal_moves())
                click.echo(f"Legal: {legal}")
                continue
            try:
                session.play_human_move(move_str)
            except ValueError as exc:
                click.secho(str(exc), fg="red")
                continue
        else:
            click.echo(f"{llm.model} is thinking…")
            applied, choice = session.play_llm_move()
            note = f"  ({choice.comment})" if choice.comment else ""
            flag = "  [fallback]" if choice.fallback else ""
            click.secho(f"LLM plays {applied.san} ({applied.uci}){note}{flag}", fg="magenta")
            click.echo(
                f"  {choice.input_tokens}+{choice.output_tokens} tok, {choice.latency_ms} ms"
            )


@cli.command(name="llm-vs-llm")
@click.option("--max-moves", default=60, help="Stop after this many half-moves (safety cap).")
@click.option("--model", default=None, help="Override LLM_MODEL for this game.")
def llm_vs_llm(max_moves: int, model: str | None) -> None:
    """Watch the LLM play against itself (both sides driven by the same player)."""
    llm = make_player(model=model)
    session = GameSession.new(f"{llm.model} (W)", f"{llm.model} (B)", llm=llm)
    for _ in range(max_moves):
        _print_board(session)
        if session.maybe_finish():
            _announce_result(session)
            return
        applied, choice = session.play_llm_move()
        flag = "  [fallback]" if choice.fallback else ""
        click.secho(f"{applied.color} plays {applied.san} ({applied.uci}){flag}", fg="magenta")
    click.secho(f"\nReached move cap ({max_moves}). Game id {session.game_id}.", fg="yellow")


@cli.command()
def games() -> None:
    """List stored games."""
    rows = repository.list_games()
    if not rows:
        click.echo("No games yet. Start one with: python -m chess_llm.cli play")
        return
    for g in rows:
        click.echo(
            f"#{g.id:<4} {g.white_player:>22} vs {g.black_player:<22} "
            f"{g.status:<12} {g.result or '-':<8} {g.created_at:%Y-%m-%d %H:%M}"
        )


@cli.command()
@click.argument("game_id", type=int)
def show(game_id: int) -> None:
    """Show the move list for a game."""
    moves = repository.get_moves(game_id)
    if not moves:
        click.echo("No such game or no moves recorded.")
        return
    for m in moves:
        prefix = f"{m.move_number}." if m.color == "white" else f"{m.move_number}..."
        click.echo(f"  ply {m.ply:>3}  {prefix:<6} {m.san:<8} ({m.uci})  by {m.player}")


@cli.command()
@click.argument("game_id", type=int)
@click.option("--ply", type=int, required=True, help="Half-move to rewind to (0 = start).")
def rewind(game_id: int, ply: int) -> None:
    """Reconstruct the board after a given number of half-moves."""
    pos = analysis.position_at_ply(game_id, ply)
    if pos is None:
        click.echo("No such game.")
        return
    click.echo(f"Position after ply {pos.ply}" + (f" ({pos.last_move_san})" if pos.last_move_san else " (start)"))
    click.echo()
    click.echo(pos.ascii_board)
    click.echo(f"\nFEN: {pos.fen}")


@cli.command()
@click.argument("game_id", type=int)
@click.option("--timeline", is_flag=True, help="Also print the material balance per ply.")
def analyze(game_id: int, timeline: bool) -> None:
    """Show performance metrics for a game."""
    summary = analysis.game_summary(game_id)
    if summary is None:
        click.echo("No such game.")
        return
    click.echo(json.dumps(summary, indent=2))
    if timeline:
        click.echo("\nMaterial balance (>0 favours White):")
        for row in analysis.material_timeline(game_id):
            bar = ("+" if row["balance"] >= 0 else "") + str(row["balance"])
            click.echo(f"  ply {row['ply']:>3} {row['san']:<8} balance {bar}")


if __name__ == "__main__":
    cli()
