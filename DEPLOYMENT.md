# Deployment guide

This service is a **text-to-query knowledge-graph QA API** with a bundled browser
UI. It translates a natural-language question into a structured graph-query AST,
executes that query over an in-memory property graph, and returns the answer plus
the generated query. It runs three ways: local Python, a single Docker container,
or the full `docker compose` stack (API + Ollama).

Translation and execution are **deterministic and model-free**; Ollama is optional
and only phrases results into a sentence. The service degrades to a deterministic
**offline backend** when no model server is present, so it is always runnable.

## Architecture

```
                 ┌──────────────────────────────────────────┐
  browser ──────►│  FastAPI app (gquery.api.main)             │
  (web/ UI)      │   GET  /         static UI                 │
                 │   GET  /health   backend + graph size      │
                 │   POST /ask      NL → query AST → execute  │
                 │   POST /load     rebuild graph             │
                 │        │                                   │
                 │        ▼                                   │
                 │  GraphQueryQA pipeline                     │
                 │   • translate(question) → Query AST        │
                 │   • execute(graph, query) → Nodes          │
                 │   • PropertyGraph (in-memory, pure-Python) │
                 │   • LLM phrasing: Ollama OR offline join   │
                 └───────────────┬────────────────────────────┘
                                 │ HTTP (prose phrasing only)
                                 ▼
                          Ollama model server (optional)
```

Data flows in at startup from `data/clinical.json` (synthetic; no PHI) and can
be replaced at runtime via `POST /load`.

## 1. Local (Python)

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Offline (no Ollama) — instant:
KG_OFFLINE=1 uvicorn gquery.api.main:app --reload

# With Ollama for natural-language prose:
ollama pull llama3.2
uvicorn gquery.api.main:app --reload
```

Open <http://localhost:8000> for the UI, or <http://localhost:8000/docs> for the
API. For uvicorn either `pip install -e .` (recommended) or run with `PYTHONPATH=src`.

## 2. Single Docker container

```bash
docker build -t kg-text2query .
# offline backend, no external Ollama:
docker run -p 8000:8000 -e KG_OFFLINE=1 kg-text2query
# or point at a host Ollama:
docker run -p 8000:8000 -e OLLAMA_HOST=http://host.docker.internal:11434 kg-text2query
```

## 3. Full stack (docker compose) — API + Ollama

```bash
cp .env.example .env            # optional; defaults are fine
docker compose up --build
# `ollama-init` pulls the model on first run; then open http://localhost:8000
```

To run the stack without Ollama (offline backend): `KG_OFFLINE=1 docker compose up --build`.

## 4. Cloud notes

- The container is stateless; the graph is rebuilt from `data/clinical.json` at
  startup, so it scales horizontally behind a load balancer.
- Set `OLLAMA_HOST` to a managed/hosted Ollama (or a sidecar) in production, or
  just set `KG_OFFLINE=1` — the answer prose is the only thing Ollama affects.
- Health check: `GET /health` returns `{"status":"ok", ...}` — wire it to your
  platform's liveness/readiness probe.
- No secrets are required; `.env` only configures the model endpoint/name.

## Configuration

| Var | Default | Meaning |
|-----|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (prose only) |
| `KG_LLM_MODEL` | `llama3.2` | generation model |
| `KG_OFFLINE` | `0` | `1` forces the offline backend |
