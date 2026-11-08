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


def _matches_name(node: Node, needle: str) -> bool:
    """Case-insensitive substring match against the node's name or id."""
    name = str(node.attrs.get("name", node.id))
    return needle.lower() in name.lower() or needle.lower() in node.id.lower()


def find_start_nodes(graph: PropertyGraph, query: Query) -> list[Node]:
    """Nodes of ``start_type`` matching ``start_name`` (all of the type if None)."""
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
