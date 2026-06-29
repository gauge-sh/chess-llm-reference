"""Runtime configuration — every vendor choice is an env var, nothing is hardcoded.

The two pluggable seams:

* **LLM** — any chat-completions HTTP endpoint. Set ``LLM_BASE_URL``, ``LLM_API_KEY``
  and ``LLM_MODEL``. Works with any endpoint that speaks the standard chat-completions
  JSON protocol; nothing about a specific host is baked in.
* **Database** — any SQLAlchemy URL via ``DATABASE_URL``. Defaults to local SQLite;
  point it at a hosted Postgres to use a managed provider. No driver lock-in beyond
  "it's a SQLAlchemy URL".
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass


@dataclass(frozen=True)
class Settings:
    # --- LLM (any chat-completions endpoint / model) -------------------------
    llm_base_url: str | None = os.getenv("LLM_BASE_URL")  # e.g. https://<host>/v1
    llm_api_key: str | None = os.getenv("LLM_API_KEY")
    llm_model: str | None = os.getenv("LLM_MODEL")
    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "2048"))
    max_tool_iterations: int = int(os.getenv("LLM_MAX_TOOL_ITERS", "8"))

    # --- Database (any SQLAlchemy URL) ---------------------------------------
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./chess.db")

    # --- App -----------------------------------------------------------------
    log_dir: str = os.getenv("LOG_DIR", "logs")
    # Comma-separated list of allowed browser origins for the API.
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000")

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model)


settings = Settings()
