"""The query model + executor — the heart of text-to-query.

A :class:`Query` is a tiny, structured graph-query AST: start at nodes of a
given type (optionally filtered by a name substring), follow a fixed list of
typed, directed hops, and return the terminal nodes of a result type. This is
the "Cypher-like" plan the translator emits and the executor runs against an
in-memory :class:`~gquery.core.graph.PropertyGraph` — deterministic and
dependency-free, so it is fully testable with no database and no model.

A hop is ``(relation, direction)``:

* ``"out"`` follows edges where ``src == current`` and ``rel`` matches → ``dst``
* ``"in"``  follows edges where ``dst == current`` and ``rel`` matches → ``src``

The schema is not hard-coded here: any relation/direction/type triples work, so
the same executor runs queries over any property graph.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gquery.core.graph import Node, PropertyGraph


@dataclass
class Query:
    """A structured graph-query AST (the plan a question is translated into)."""

    start_type: str
    result_type: str
    start_name: str | None = None
    hops: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-friendly view of the AST (exposed by the API/UI)."""
        return {
            "start_type": self.start_type,
            "start_name": self.start_name,
            "hops": [{"relation": rel, "direction": direction} for rel, direction in self.hops],
            "result_type": self.result_type,
        }


def _contains_word(haystack: str, needle: str) -> bool:
    """True if ``needle`` appears in ``haystack`` on word boundaries (case-insensitive).

    Used so a short node name/id can't match inside an unrelated word.
    """
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle.lower())}(?!\w)", haystack.lower()) is not None


def _matches_name(node: Node, phrase: str) -> bool:
    """Match a node against the captured ``phrase``.

    Resolves by *reverse containment*: the node's name (or id) must appear, on
    word boundaries, inside the captured phrase. This makes qualified/multi-word
    questions robust — e.g. the phrase "hypertension in elderly" still resolves
    to the node "Hypertension", and "metformin and lisinopril" resolves to both
    medication nodes. The phrase-in-name direction is also kept so a partial
    entity typed by the user (e.g. "diabetes") still matches "Type 2 Diabetes".
    """
    name = str(node.attrs.get("name", node.id))
    phrase_l = phrase.lower()
    # Reverse containment (node name/id appears in the phrase, word-bounded).
    if _contains_word(phrase_l, name) or _contains_word(phrase_l, node.id):
        return True
    # Forward containment (phrase is a partial of the node name/id).
    return phrase_l in name.lower() or phrase_l in node.id.lower()


def find_start_nodes(graph: PropertyGraph, query: Query) -> list[Node]:
    """Nodes of ``start_type`` matching ``start_name`` (all of the type if None).

    Multiple nodes of the start type may match (e.g. an "X or Y" question), and
    all are returned; the executor unions their traversals.
    """
    nodes = graph.nodes_of_type(query.start_type)
    if query.start_name:
        nodes = [n for n in nodes if _matches_name(n, query.start_name)]
    return nodes


def _step(graph: PropertyGraph, node_id: str, relation: str, direction: str) -> list[str]:
    """One hop from ``node_id`` along ``relation`` in ``direction`` → neighbor ids."""
    out: list[str] = []
    for edge, edge_dir, other in graph.neighbors(node_id):
        if edge.rel == relation and edge_dir == direction:
            out.append(other)
    return out


def execute(graph: PropertyGraph, query: Query) -> list[Node]:
    """Run ``query`` against ``graph`` → terminal nodes of ``result_type``.

    Deterministic: results are de-duplicated by id while preserving first-seen
    order. Terminal nodes whose type does not equal ``result_type`` are dropped.
    """
    current = [n.id for n in find_start_nodes(graph, query)]

    for relation, direction in query.hops:
        nxt: list[str] = []
        seen: set[str] = set()
        for node_id in current:
            for other in _step(graph, node_id, relation, direction):
                if other not in seen:
                    seen.add(other)
                    nxt.append(other)
        current = nxt

    results: list[Node] = []
    emitted: set[str] = set()
    for node_id in current:
        node = graph.nodes.get(node_id)
        if node is None or node.type != query.result_type or node.id in emitted:
            continue
        emitted.add(node.id)
        results.append(node)
    return results
