"""Text-to-query QA pipeline: translate → execute → phrase.

1. :func:`~gquery.core.translate.translate` turns the question into a structured
   :class:`~gquery.core.query.Query` AST (deterministic).
2. :func:`~gquery.core.query.execute` runs that AST over the in-memory property
   graph and returns the matching nodes (deterministic).
3. the LLM backend phrases those results into a sentence (Ollama, or a
   deterministic offline join).

Exposing the generated query AST is the selling point: the ``ask`` result
carries the exact structured query that was executed.
"""

from __future__ import annotations

from gquery.core.backends import get_llm
from gquery.core.graph import PropertyGraph
from gquery.core.loader import build_graph
from gquery.core.query import execute
from gquery.core.translate import translate


def _name(node) -> str:
    return str(node.attrs.get("name", node.id))


class GraphQueryQA:
    def __init__(self, graph: PropertyGraph | None = None):
        self.llm = get_llm()
        self.graph = graph if graph is not None else PropertyGraph()

    def load(self, data: dict) -> int:
        """(Re)build the graph from structured records. Returns node count."""
        self.graph = build_graph(data)
        return len(self.graph)

    def ask(self, question: str) -> dict:
        """Translate the question to a query, execute it, and phrase the results."""
        if len(self.graph) == 0:
            return {"answer": "The knowledge graph is empty.", "query": None,
                    "results": [], "matched": None}

        query = translate(question)
        if query is None:
            return {
                "answer": "No structured query could be formed from that question. "
                "Try e.g. 'Which medications treat hypertension?' or "
                "'Which patients are on metformin?'.",
                "query": None,
                "results": [],
                "matched": None,
            }

        nodes = execute(self.graph, query)
        results = [{"type": n.type, "name": _name(n)} for n in nodes]
        answer = self.llm.phrase(question, [r["name"] for r in results])
        return {
            "answer": answer,
            "query": query.to_dict(),
            "results": results,
            "matched": query.start_name,
        }
