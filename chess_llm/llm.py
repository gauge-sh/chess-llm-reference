"""The LLM chess player — endpoint-neutral.

Talks to any chat-completions HTTP endpoint via the widely-implemented JSON wire
format (`POST {base_url}/chat/completions` with `messages` + `tools`). The endpoint is
pure configuration (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`); there is no
endpoint-specific code here, and no third-party client SDK — just an HTTP call.

It runs a tool-calling loop — `get_legal_moves` → reason → `make_move` — with the
engine validating every move. Per-move detail (tokens, latency, the chosen move) is
returned on `MoveChoice` and written to the JSON logs, but nothing is persisted to a
trace store — wire your own LLM-observability platform in here if you want one. To
support an endpoint that doesn't speak this wire format, implement the `Player`
protocol in a new module and return it from `make_player`.
"""

from __future__ import annotations

import json
import time
from typing import Protocol

import httpx

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

log = get_logger("llm")


class Player(Protocol):
    model: str

    def choose_move(self, engine: ChessEngine, game_id: int) -> MoveChoice: ...


def make_player(model: str | None = None) -> Player:
    """Return the configured LLM player. Swap this out (or branch on an env flag) to
    introduce an alternative adapter without touching the rest of the app."""
    return ChatCompletionsPlayer(model=model)


class LLMNotConfigured(RuntimeError):
    pass


class ChatCompletionsPlayer:
    def __init__(self, model: str | None = None):
        if not settings.llm_base_url or not (model or settings.llm_model):
            raise LLMNotConfigured(
                "Set LLM_BASE_URL and LLM_MODEL (and usually LLM_API_KEY) — see .env.example."
            )
        self.model = model or settings.llm_model  # type: ignore[assignment]
        self.base_url = settings.llm_base_url.rstrip("/")
        self.api_key = settings.llm_api_key
        self.http = httpx.Client(timeout=120.0)  # reasoning models can be slow

    def _complete(self, messages: list[dict], tools: list[dict]) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "max_tokens": settings.max_tokens,
            "temperature": settings.temperature,
        }
        resp = self.http.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def choose_move(self, engine: ChessEngine, game_id: int) -> MoveChoice:
        prompt = position_prompt(engine)
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        turn = TurnTrace()
        chosen: str | None = None
        comment: str | None = None

        t0 = time.monotonic()
        status = "ok"
        try:
            chosen, comment = self._run_loop(engine, messages, turn)
        except Exception as exc:
            status = "error"
            log.warning(
                "llm turn failed", extra={"context": {"game_id": game_id, "error": repr(exc)}}
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        fallback = False
        if chosen is None:
            chosen = engine.legal_moves()[0].uci
            fallback = True
            log.warning(
                "falling back to first legal move",
                extra={"context": {"game_id": game_id, "uci": chosen}},
            )

        # Per-move detail is logged and returned on MoveChoice, not persisted. Hook
        # your own observability platform in here if you want spans exported.
        log.info(
            "llm move chosen",
            extra={
                "context": {
                    "game_id": game_id,
                    "model": self.model,
                    "uci": chosen,
                    "fallback": fallback,
                    "status": status,
                    "input_tokens": turn.input_tokens,
                    "output_tokens": turn.output_tokens,
                    "latency_ms": latency_ms,
                }
            },
        )
        return MoveChoice(
            uci=chosen,
            thinking="\n".join(turn.thinking),
            comment=comment,
            fallback=fallback,
            input_tokens=turn.input_tokens,
            output_tokens=turn.output_tokens,
            latency_ms=latency_ms,
        )

    def _run_loop(self, engine, messages, turn) -> tuple[str | None, str | None]:
        chosen = comment = None
        tools = tool_specs()
        for _ in range(settings.max_tool_iterations):
            data = self._complete(messages, tools)
            usage = data.get("usage") or {}
            turn.input_tokens += usage.get("prompt_tokens") or 0
            turn.output_tokens += usage.get("completion_tokens") or 0

            msg = data["choices"][0]["message"]
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                if msg.get("content"):
                    turn.thinking.append(msg["content"])
                messages.append({"role": "assistant", "content": msg.get("content") or ""})
                messages.append(
                    {
                        "role": "user",
                        "content": "Use the make_move tool to play exactly one legal move.",
                    }
                )
                continue

            # Echo the assistant turn (with its tool_calls) back verbatim, then answer each call.
            messages.append(
                {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
            )
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                outcome = execute_tool(engine, fn.get("name", ""), args)
                if outcome.picked_uci is not None:
                    chosen, comment = outcome.picked_uci, outcome.comment
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": json.dumps(outcome.output),
                    }
                )

            if chosen is not None:
                break
        return chosen, comment
