"""The LLM chess player — vendor-neutral.

Talks to any **OpenAI-compatible** chat-completions endpoint (OpenAI, Anthropic's
compat API, and the many gateways/inference hosts that implement the same protocol).
The vendor is pure configuration (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`); there
is no provider-specific code path here.

It runs a tool-calling loop — `get_legal_moves` → reason → `make_move` — with the
engine validating every move, and records each turn as a trace (request/response,
tokens, latency) with one span per tool call. To support a non-OpenAI-shaped vendor,
implement the `Player` protocol in a new module and return it from `make_player`.
"""

from __future__ import annotations

import json
import time
from typing import Optional, Protocol

from .config import settings
from .engine import ChessEngine
from .logging_setup import get_logger
from .tools import (
    SYSTEM_PROMPT,
    MoveChoice,
    TurnTrace,
    execute_tool,
    position_prompt,
    tool_specs,
)
from . import repository

log = get_logger("llm")


class Player(Protocol):
    model: str

    def choose_move(self, engine: ChessEngine, game_id: int) -> MoveChoice: ...


def make_player(model: str | None = None) -> Player:
    """Return the configured LLM player. Swap this out (or branch on an env flag) to
    introduce an alternative adapter without touching the rest of the app."""
    return OpenAICompatiblePlayer(model=model)


class LLMNotConfigured(RuntimeError):
    pass


class OpenAICompatiblePlayer:
    def __init__(self, model: str | None = None):
        if not settings.llm_base_url or not (model or settings.llm_model):
            raise LLMNotConfigured(
                "Set LLM_BASE_URL and LLM_MODEL (and usually LLM_API_KEY) — see .env.example."
            )
        from openai import OpenAI

        self.model = model or settings.llm_model  # type: ignore[assignment]
        self.client = OpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "EMPTY",  # some local gateways need no key
        )

    def choose_move(self, engine: ChessEngine, game_id: int) -> MoveChoice:
        prompt = position_prompt(engine)
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        turn = TurnTrace()
        chosen: Optional[str] = None
        comment: Optional[str] = None

        t0 = time.monotonic()
        status, error = "ok", None
        try:
            chosen, comment = self._run_loop(engine, messages, turn)
        except Exception as exc:
            status, error = "error", repr(exc)
            log.warning("llm turn failed", extra={"context": {"game_id": game_id, "error": repr(exc)}})

        latency_ms = int((time.monotonic() - t0) * 1000)
        fallback = False
        if chosen is None:
            chosen = engine.legal_moves()[0].uci
            fallback = True
            log.warning("falling back to first legal move", extra={"context": {"game_id": game_id, "uci": chosen}})

        trace_id = repository.record_trace(
            game_id=game_id,
            model=self.model,
            status=status,
            request={"base_url": settings.llm_base_url, "system": SYSTEM_PROMPT, "prompt": prompt},
            response={"chosen": chosen, "comment": comment, "thinking": "\n".join(turn.thinking)},
            error=error,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            latency_ms=latency_ms,
            spans=turn.spans,
        )
        log.info(
            "llm move chosen",
            extra={"context": {
                "game_id": game_id, "model": self.model, "uci": chosen, "fallback": fallback,
                "input_tokens": turn.input_tokens, "output_tokens": turn.output_tokens,
                "latency_ms": latency_ms, "tool_calls": len(turn.spans),
            }},
        )
        return MoveChoice(
            uci=chosen, thinking="\n".join(turn.thinking), comment=comment, trace_id=trace_id,
            fallback=fallback, input_tokens=turn.input_tokens, output_tokens=turn.output_tokens,
            latency_ms=latency_ms,
        )

    def _run_loop(self, engine, messages, turn) -> tuple[Optional[str], Optional[str]]:
        chosen = comment = None
        tools = tool_specs()
        for _ in range(settings.max_tool_iterations):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=settings.max_tokens,
                temperature=settings.temperature,
            )
            if resp.usage:
                turn.input_tokens += resp.usage.prompt_tokens or 0
                turn.output_tokens += resp.usage.completion_tokens or 0

            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                if msg.content:
                    turn.thinking.append(msg.content)
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({"role": "user", "content": "Use the make_move tool to play exactly one legal move."})
                continue

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                started = time.monotonic()
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                outcome = execute_tool(engine, tc.function.name, args)
                turn.add_span(tc.function.name, tc.id, args, outcome, started)
                if outcome.picked_uci is not None:
                    chosen, comment = outcome.picked_uci, outcome.comment
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(outcome.output)})

            if chosen is not None:
                break
        return chosen, comment
