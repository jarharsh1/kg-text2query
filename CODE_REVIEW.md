# Code review — text-to-query engine

A high-effort correctness review of the text-to-query engine, with the findings,
the root-cause analysis, the fixes, and the regression tests that lock them in.
Every bug below was **confirmed by running code against the shipped sample graph**,
not inferred from reading.

The commits that implement these fixes are on `main`
(`09c46df`, `0d3a0fc`, `f181e3b`, `c762bc8`); this document is the reviewer-facing
write-up of what they do and why.

---

## Finding 1 (High) — qualified / multi-word questions returned empty results

**Where:** `src/gquery/core/translate.py` (greedy entity capture) +
`src/gquery/core/query.py::_matches_name` (containment direction).

**Symptom (confirmed by running):**

| Question | Before | After |
|----------|--------|-------|
| `medications that treat hypertension in elderly` | `[]` | `Lisinopril, Amlodipine` |
| `who takes metformin or lisinopril` | `[]` | `Patient 001, Patient 002` |
| `who takes metformin` | `Patient 002` | `Patient 002` (unchanged) |

**Root cause.** The translator captures the entity with a greedy `(?P<ent>.+)`,
so `"...treat hypertension in elderly"` captured the whole tail
`"hypertension in elderly"`. The matcher then did **forward** containment:

```python
# before
def _matches_name(node, needle):
    name = str(node.attrs.get("name", node.id))
    return needle.lower() in name.lower() or needle.lower() in node.id.lower()
```

i.e. it required the *captured phrase* to be a substring of the *node name*.
`"hypertension in elderly" in "hypertension"` is `False`, so nothing resolved —
the query executed over an empty start set and returned `[]`. A conjunction
(`"metformin and lisinopril"`) failed the same way: it is never a substring of a
single node name.

**Why the obvious fix is wrong.** Loosening the capture regex (`.+?` instead of
`.+`) just moves the failure — it still assumes the captured span is exactly one
clean entity name, which natural phrasing violates. The real issue is that the
**matcher trusts the regex capture to be a clean entity**. It shouldn't.

**Fix — resolve the entity against the graph (reverse containment).** A node now
matches when its *name* appears, on word boundaries, *inside* the captured
phrase; the forward direction is kept so a user's partial (`"diabetes"` →
`"Type 2 Diabetes"`) still works. Word boundaries stop a short name from matching
inside an unrelated word.

```python
# after
def _contains_word(haystack, needle):
    return re.search(rf"(?<!\w){re.escape(needle.lower())}(?!\w)", haystack.lower()) is not None

def _matches_name(node, phrase):
    name = str(node.attrs.get("name", node.id))
    phrase_l = phrase.lower()
    if _contains_word(phrase_l, name) or _contains_word(phrase_l, node.id):  # reverse
        return True
    return phrase_l in name.lower() or phrase_l in node.id.lower()           # forward
```

`find_start_nodes` now returns **all** matching start-type nodes and the executor
unions their traversals, which is what makes `"X or Y"` work.

**Altitude note.** This fixes the root cause (entity resolution) at the right
layer rather than patching each regex rule. The regex rules stayed simple; the
intelligence moved to resolution, where it belongs.

**Regression tests:** the three table rows above are asserted in
`tests/test_query.py` (qualified phrase, conjunction union, unchanged simple case).

---

## Finding 2 (Medium) — `translate()` returned a rule whose entity resolved to nothing

**Where:** `src/gquery/core/translate.py::translate` (first-rule-wins).

**Root cause.** `translate()` returned the first rule whose *regex* matched and
whose *cleaned entity string* was non-empty — without checking the entity
actually resolves to a node. A broad early rule could win with a junk entity
while a more specific later rule would have produced a resolvable one, so the
pipeline reported an empty answer.

**Fix.** `translate(question, graph=None)` now, when a graph is supplied, prefers
the first rule whose entity **resolves to at least one start node**, falling back
to the first structural match otherwise. The pipeline passes the graph in. This
is backward-compatible: `translate(question)` with no graph keeps the old
first-structural-match behavior, so the translator stays usable standalone.

---

## Finding 3 (Medium) — bundled dataset path was resolved against the CWD

**Where:** `src/gquery/api/main.py` (`_SAMPLE = Path("data/clinical.json")`).

**Root cause.** The startup graph load used a **CWD-relative** path while the web
UI directory two lines above resolved from `__file__`. Launch the server from any
directory other than the repo root and `clinical.json` is not found, the graph
stays empty, and `/ask` answers "the knowledge graph is empty" for every
question — with the failure visible only on stderr.

**Fix.** Resolve the sample from the package root, consistent with `_WEB_DIR`:

```python
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE = _REPO_ROOT / "data" / "clinical.json"
```

**Regression test:** asserts `_SAMPLE.is_absolute()` and `_SAMPLE.exists()`, so a
reintroduced CWD-relative path fails CI regardless of where pytest runs.

---

## What was checked and found correct (not changed)

- **Executor hop directions** (`core/query.py::_step`): `"out"` follows
  `src == current`, `"in"` follows `dst == current`. Verified against the clinical
  schema — a reversed hop would return plausible-but-wrong nodes, so this was
  traced explicitly for every shipped rule.
- **De-duplication** in `execute()` preserves first-seen order and filters to
  `result_type`.
- **`Query.to_dict()`** (the AST the UI surfaces) round-trips the hops faithfully.

## Test evidence

`pytest -q` → **28 passed** (was 21 before the review; +7 regression tests).
`ruff check src tests demo.py` → clean.
