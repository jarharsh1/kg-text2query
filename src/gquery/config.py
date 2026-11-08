"""Runtime configuration (env with local defaults). Ollama-first, offline fallback.

The translator and executor are fully deterministic and need no model; the LLM
is optional and only phrases the executed results into a sentence. Set
``KG_OFFLINE=1`` to force the deterministic offline backend (no Ollama).
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    llm_model: str = os.getenv("KG_LLM_MODEL", "llama3.2")
    offline: bool = os.getenv("KG_OFFLINE", "0") == "1"


settings = Settings()
