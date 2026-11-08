"""LLM backend (Ollama-first, deterministic offline fallback).

Text-to-query is fully deterministic: the translator builds the query AST and
the executor runs it. The LLM here is *optional* and only turns the executed
results into a natural-language sentence. Offline (or when no Ollama is up) a
deterministic sentence join is used instead, so the whole pipeline — and the
tests — run with no model server.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from gquery.config import settings


class LLM(Protocol):
    def phrase(self, question: str, result_names: list[str]) -> str: ...


def _join(names: list[str]) -> str:
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


class OfflineLLM:
    """Deterministic phrasing — no model. Joins the executed results into prose."""

    def phrase(self, question: str, result_names: list[str]) -> str:
        if not result_names:
            return "The query matched no results in the graph."
        return f"{_join(result_names)}."


class OllamaLLM:
    def __init__(self, host: str, model: str):
        self.host, self.model = host.rstrip("/"), model

    def phrase(self, question: str, result_names: list[str]) -> str:
        if not result_names:
            return "The query matched no results in the graph."
        prompt = (
            "Answer the question in one short sentence using ONLY these results "
            "from a knowledge-graph query. Do not add facts.\n"
            f"QUESTION: {question}\n"
            f"RESULTS: {_join(result_names)}\n"
        )
        with httpx.Client(timeout=120) as c:
            r = c.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            r.raise_for_status()
            return r.json()["response"].strip()


def _ollama_up(host: str) -> bool:
    try:
        with httpx.Client(timeout=2) as c:
            return c.get(f"{host.rstrip('/')}/api/tags").status_code == 200
    except Exception:
        return False


def get_llm() -> LLM:
    if not settings.offline and _ollama_up(settings.ollama_host):
        return OllamaLLM(settings.ollama_host, settings.llm_model)
    return OfflineLLM()
