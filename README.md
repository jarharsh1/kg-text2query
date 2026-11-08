# Text-to-Query Knowledge-Graph QA Engine

Ask a question in plain English; the engine translates it into a small,
**structured graph-query AST**, **executes** that query against an in-memory
property graph, and returns the results — plus the exact query it ran. Think
**text-to-Cypher**, but against a pure-Python property graph with **no external
database and no model required** for the query itself.

**Why text-to-query.** Flat text RAG retrieves passages and hopes the answer is
in them. A *relational* question — "which drugs treat X", "which patients are on
Y", "what did provider Z prescribe" — is really a **traversal**. Translating the
question into an explicit query makes the retrieval **precise, inspectable, and
deterministic**: you can see the structured query that produced the answer.

**Ships with a worked example: a clinical knowledge graph** — patients,
encounters, conditions, medications, and providers — so the engine runs end to
end out of the box. The query model, translator, and executor are
**domain-agnostic**: to target another domain you feed the loader different
records and add a few translation rules ([see use cases](#use-cases)); the
engine does not change.

> The shipped sample data is **synthetic** — no real patient data / PHI.

## How it works

```
question ──translate──► Query AST ──execute──► result nodes ──phrase──► answer
   (plain English)      (structured)   (graph traversal)        (sentence)
```

1. **translate** (`core/translate.py`) — deterministic keyword/regex rules
   recognize a question *shape* and emit a `Query` AST. No LLM needed.
2. **execute** (`core/query.py`) — runs the AST over the `PropertyGraph`: start
   at typed nodes, follow typed/directed hops, return terminal nodes. Pure
   Python, fully testable.
3. **phrase** (`core/backends.py`) — the *only* optional LLM step turns the
   executed results into a sentence (Ollama, or a deterministic offline join).

### Example generated query

The question **"Which medications treat hypertension?"** translates to this AST:

```json
{
  "start_type": "Condition",
  "start_name": "hypertension",
  "hops": [{ "relation": "TREATS", "direction": "in" }],
  "result_type": "Medication"
}
```

Read it as: *find `Condition` nodes named "hypertension", follow `TREATS` edges
**inward** (medication → condition), return the `Medication` nodes* →
**Lisinopril, Amlodipine**. The `/ask` response and the UI show this AST next to
the answer — surfacing the structured query is the whole point.

### Recognized question shapes (clinical example)

| Question | Generated query (start → hops → result) |
|----------|------------------------------------------|
| "Which medications treat hypertension?" | `Condition["hypertension"]` → `TREATS(in)` → `Medication` |
| "What conditions does Patient 001 have?" | `Patient["001"]` → `HAS_CONDITION(out)` → `Condition` |
| "Which patients are on metformin?" | `Medication["metformin"]` → `PRESCRIBED(in)` → `HAS_ENCOUNTER(in)` → `Patient` |
| "What did Dr. Rao prescribe?" | `Provider["Rao"]` → `SEEN_BY(in)` → `PRESCRIBED(out)` → `Medication` |

## Use cases

The engine is the same; only the records you feed the loader (and a few
translation rules) change. The `Query` model, the `execute()` traversal, and the
`PropertyGraph` are domain-agnostic — swap in your own nodes and relations and
the same text-to-query pipeline answers over them.

| Domain | Graph (nodes — relations) | Example question → query |
|--------|---------------------------|--------------------------|
| **Healthcare** *(shipped example)* | patients — conditions — medications — providers | "Which drugs treat hypertension?" → `Condition → TREATS(in) → Medication` |
| **Enterprise / HR** | employees — teams — projects | "Who works on project X?" → `Project → ASSIGNED(in) → Employee` |
| **E-commerce** | customers — orders — products | "Who bought product Y?" → `Product → CONTAINS(in) → PLACED(in) → Customer` |
| **Supply chain** | suppliers — parts — plants | "Which suppliers provide part Y?" → `Part → SUPPLIES(in) → Supplier` |
| **Research** | papers — authors — topics | "Who published on topic Z?" → `Topic → ABOUT(in) → WROTE(in) → Author` |
| **Fraud / finance** | accounts — transactions — entities | "Which accounts fund entity W?" → `Entity → TO(in) → FROM(out) → Account` |

Only the loader's **input records** and the **translation rules** change — the
query AST, the executor's traversal, and the graph are identical across all of
these.

## Stack

- **Backend:** FastAPI (serves the HTTP API and auto-generates interactive docs
  at `/docs`).
- **Frontend:** a lightweight browser UI (`web/`, plain HTML + JS) served by
  FastAPI at `/` — it posts to `/ask` and **prominently renders the generated
  query AST** alongside the answer and results.
- **Query engine:** a dependency-free `PropertyGraph` + a tiny `Query` AST and
  `execute()` traversal — deterministic, no database, no model.
- **Model:** Ollama (local LLM) for optional prose phrasing, with a deterministic
  offline fallback (so the pipeline and tests run with no model server — CI-safe).
- **Deploy:** single Docker image, or `docker compose` (API + Ollama). See
  [DEPLOYMENT.md](DEPLOYMENT.md).

Open **<http://localhost:8000>** for the UI once running.

## Graph schema (shipped clinical example)

This is the schema of the bundled clinical example (`data/clinical.json`). Any
graph with its own node/relation types works the same way — the engine does not
hard-code these.

| Relation | Meaning |
|----------|---------|
| `Patient -HAS_ENCOUNTER-> Encounter` | a visit |
| `Encounter -SEEN_BY-> Provider` | attending provider |
| `Encounter -DIAGNOSED-> Condition` | diagnosis at the visit |
| `Encounter -PRESCRIBED-> Medication` | prescription at the visit |
| `Medication -TREATS-> Condition` | drug knowledge |
| `Patient -HAS_CONDITION-> Condition` | rolled up for convenience |

## Quickstart

```bash
pip install -r requirements.txt

ollama pull llama3.2                     # optional, for natural-language prose
python demo.py                           # or KG_OFFLINE=1 python demo.py

uvicorn gquery.api.main:app --reload     # API at /docs (loads data/clinical.json)
```

### Example

```bash
curl -X POST localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Which medications treat hypertension?"}'
```

```json
{
  "answer": "Lisinopril and Amlodipine.",
  "query": {
    "start_type": "Condition",
    "start_name": "hypertension",
    "hops": [{ "relation": "TREATS", "direction": "in" }],
    "result_type": "Medication"
  },
  "results": [
    { "type": "Medication", "name": "Lisinopril" },
    { "type": "Medication", "name": "Amlodipine" }
  ],
  "matched": "hypertension"
}
```

## Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (prose only) |
| `KG_LLM_MODEL` | `llama3.2` | generation model |
| `KG_OFFLINE` | `0` | `1` forces the offline backend |

## Tests

```bash
pytest -q          # offline; no Ollama needed
```

CI lints, runs the tests + the demo offline, and builds the Docker image.
