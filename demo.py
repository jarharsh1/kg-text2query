"""CLI demo: load the clinical graph, translate questions to query ASTs, execute.

    python demo.py            # Ollama if up, else offline
    KG_OFFLINE=1 python demo.py

For each question it prints the generated structured query AST and the results.
"""

import json
from pathlib import Path

from gquery.core.pipeline import GraphQueryQA

QUESTIONS = [
    "Which medications treat hypertension?",
    "Which patients are on metformin?",
    "What conditions does Patient 001 have?",
    "What did Dr. Rao prescribe?",
]


def main() -> None:
    data = json.loads(Path("data/clinical.json").read_text(encoding="utf-8"))
    qa = GraphQueryQA()
    n = qa.load(data)
    print(f"Loaded graph with {n} nodes (backend: {type(qa.llm).__name__})\n")

    for q in QUESTIONS:
        result = qa.ask(q)
        print(f"Q: {q}")
        print(f"   generated query: {json.dumps(result['query'])}")
        names = [r["name"] for r in result["results"]]
        print(f"   results: {names}")
        print(f"A: {result['answer']}")
        print()


if __name__ == "__main__":
    main()
