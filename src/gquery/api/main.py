"""FastAPI serving layer for the text-to-query knowledge-graph QA engine.

Endpoints:
  GET  /         - the browser UI (static)
  GET  /health   - liveness + active backend + graph size
  POST /load      - (re)build the graph from structured records
  POST /ask       - translate NL -> structured query AST, execute it, phrase it

The ``/ask`` response exposes the *generated query AST* alongside the answer and
results — "here is the structured query we ran" is the differentiator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from gquery.core.backends import OllamaLLM
from gquery.core.pipeline import GraphQueryQA

# Locate bundled files (repo-root/web, repo-root/data), resilient to the CWD.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_WEB_DIR = _REPO_ROOT / "web"

app = FastAPI(
    title="Text-to-Query Knowledge-Graph QA",
    version="0.1.0",
    description="Translate a natural-language question into a small, structured "
    "graph-query AST, then execute that query against an in-memory property "
    "graph and return the results. Domain-agnostic (think 'text-to-Cypher' with "
    "no database); ships with a clinical knowledge-graph as the worked example.",
)

_pipeline = GraphQueryQA()

# Load the bundled synthetic dataset at startup if present.
_SAMPLE = _REPO_ROOT / "data" / "clinical.json"
if _SAMPLE.exists():
    try:
        _pipeline.load(json.loads(_SAMPLE.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - startup best-effort
        print(f"[startup] could not load {_SAMPLE}: {exc}", file=sys.stderr)


class LoadRequest(BaseModel):
    data: dict = Field(..., description="Structured records: patients, providers, "
                       "conditions, medications, encounters.")


class LoadResponse(BaseModel):
    nodes: int


class AskRequest(BaseModel):
    question: str = Field(..., examples=["Which medications treat hypertension?"])


class ResultItem(BaseModel):
    type: str
    name: str


class AskResponse(BaseModel):
    answer: str
    query: dict | None
    results: list[ResultItem]
    matched: str | None


@app.get("/health")
def health() -> dict:
    backend = "ollama" if isinstance(_pipeline.llm, OllamaLLM) else "offline"
    return {"status": "ok", "backend": backend, "graph_nodes": len(_pipeline.graph)}


@app.post("/load", response_model=LoadResponse)
def load(req: LoadRequest) -> LoadResponse:
    return LoadResponse(nodes=_pipeline.load(req.data))


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    return AskResponse(**_pipeline.ask(req.question))


# --- Browser UI ------------------------------------------------------------ #
# Serve the static UI. Mounted last so it never shadows the API routes.
if _WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(_WEB_DIR / "index.html"))
