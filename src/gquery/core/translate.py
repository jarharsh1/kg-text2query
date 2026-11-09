"""Text-to-query translator: natural language → a structured :class:`Query` AST.

This is the deterministic "text-to-Cypher" step — no LLM required. A handful of
keyword/regex rules recognize a few question *shapes*, extract the entity the
question is about, and emit the matching :class:`Query` plan that the executor
then runs. Returns ``None`` when no rule matches (the caller explains that no
query could be formed).

Recognized shapes (clinical worked example)::

    "medications that treat <X>" / "drugs for <X>"
        -> Condition[<X>] --TREATS(in)--> Medication
    "conditions <patient> has" / "diagnoses for <patient>"
        -> Patient[<X>] --HAS_CONDITION(out)--> Condition
    "patients on <med>" / "who takes <med>"
        -> Medication[<X>] --PRESCRIBED(in)--HAS_ENCOUNTER(in)--> Patient
    "what did <provider> prescribe"
        -> Provider[<X>] --SEEN_BY(in)--PRESCRIBED(out)--> Medication

The *rules* are the only domain-specific piece; the :class:`Query` model and the
executor are generic. Add rules here (or swap this module out) to retarget the
engine to another graph schema.
"""

from __future__ import annotations

import re

from gquery.core.graph import PropertyGraph
from gquery.core.query import Query, find_start_nodes

# A rule is (compiled-pattern, entity-group-name, Query-builder taking the entity).
# Patterns are tried in order; the first match wins. Each pattern captures the
# entity under the named group ``ent``.
_RULES: list[tuple[re.Pattern[str], object]] = []


def _rule(pattern: str, builder) -> None:
    _RULES.append((re.compile(pattern, re.IGNORECASE), builder))


# "medications that treat <X>", "drugs for <X>", "what treats <X>"
_rule(
    r"\b(?:medications?|drugs?|meds?)\b.*?\b(?:treat|treats|treating|for)\b\s+(?P<ent>.+)",
    lambda ent: Query(
        start_type="Condition", start_name=ent, hops=[("TREATS", "in")],
        result_type="Medication",
    ),
)
_rule(
    r"\bwhat\b.*?\btreats?\b\s+(?P<ent>.+)",
    lambda ent: Query(
        start_type="Condition", start_name=ent, hops=[("TREATS", "in")],
        result_type="Medication",
    ),
)

# Trailing-verb form: "conditions <patient> has", "conditions that <patient> have".
# The entity sits BEFORE the verb here, so it needs its own rule (the rule below
# only handles the trigger-before-entity form, e.g. "does <patient> have").
_rule(
    r"\b(?:conditions?|diagnoses|diagnosis)\b\s+(?:that\s+)?(?P<ent>.+?)\s+(?:has|have)\b\s*$",
    lambda ent: Query(
        start_type="Patient", start_name=ent, hops=[("HAS_CONDITION", "out")],
        result_type="Condition",
    ),
)

# "diagnoses for <patient>", "what conditions does <patient> have"
_rule(
    r"\b(?:conditions?|diagnoses|diagnosis)\b.*?\b(?:does|for|of|has|have)\b\s+(?P<ent>.+?)\s*(?:have|has)?\s*$",
    lambda ent: Query(
        start_type="Patient", start_name=ent, hops=[("HAS_CONDITION", "out")],
        result_type="Condition",
    ),
)

# "patients on <med>", "who takes <med>", "who is on <med>"
_rule(
    r"\bpatients?\b.*?\bon\b\s+(?P<ent>.+)",
    lambda ent: Query(
        start_type="Medication", start_name=ent,
        hops=[("PRESCRIBED", "in"), ("HAS_ENCOUNTER", "in")], result_type="Patient",
    ),
)
_rule(
    r"\bwho\b.*?\b(?:takes|take|taking|is on|on)\b\s+(?P<ent>.+)",
    lambda ent: Query(
        start_type="Medication", start_name=ent,
        hops=[("PRESCRIBED", "in"), ("HAS_ENCOUNTER", "in")], result_type="Patient",
    ),
)

# "what did <provider> prescribe", "medications prescribed by <provider>"
_rule(
    r"\bwhat\b.*?\bdid\b\s+(?P<ent>.+?)\s+prescribe",
    lambda ent: Query(
        start_type="Provider", start_name=ent,
        hops=[("SEEN_BY", "in"), ("PRESCRIBED", "out")], result_type="Medication",
    ),
)
_rule(
    r"\b(?:medications?|drugs?|meds?)\b.*?\bprescribed by\b\s+(?P<ent>.+)",
    lambda ent: Query(
        start_type="Provider", start_name=ent,
        hops=[("SEEN_BY", "in"), ("PRESCRIBED", "out")], result_type="Medication",
    ),
)

# Trailing noise to strip off an extracted entity.
_TRAILERS = re.compile(r"\b(have|has|take|takes|taking)\b\s*$", re.IGNORECASE)


def _clean(entity: str) -> str:
    """Normalize a captured entity: strip punctuation, articles and trailing verbs."""
    ent = entity.strip().strip("?.!,;:\"'")
    ent = re.sub(r"^(?:a|an|the)\s+", "", ent, flags=re.IGNORECASE)
    ent = _TRAILERS.sub("", ent).strip()
    return ent


def translate(question: str, graph: PropertyGraph | None = None) -> Query | None:
    """Translate ``question`` into a :class:`Query`, or ``None`` if nothing matches.

    When ``graph`` is given, prefer the first rule whose cleaned entity actually
    resolves to at least one start node in the graph. This avoids returning a
    query that is structurally valid but whose entity matches nothing (e.g. a
    broad "on" phrasing capturing a non-medication). Without a graph, the first
    rule whose entity is non-empty wins (the original behavior).
    """
    text = question.strip()
    first: Query | None = None
    for pattern, builder in _RULES:
        m = pattern.search(text)
        if not m:
            continue
        entity = _clean(m.group("ent"))
        if not entity:
            continue
        query: Query = builder(entity)  # type: ignore[operator]
        if graph is None:
            return query
        if find_start_nodes(graph, query):
            return query
        if first is None:
            first = query  # remember the first structural match as a fallback
    return first
