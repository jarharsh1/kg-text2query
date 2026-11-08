"""Unit tests: the translator emits the right Query AST, and the executor runs it."""

import json
from pathlib import Path

from gquery.core.loader import build_graph
from gquery.core.query import Query, execute
from gquery.core.translate import translate

DATA = json.loads(Path("data/clinical.json").read_text(encoding="utf-8"))
GRAPH = build_graph(DATA)


def _names(nodes):
    return {n.attrs.get("name", n.id) for n in nodes}


# ---- translate() shapes --------------------------------------------------- #

def test_translate_medications_that_treat():
    q = translate("Which medications treat hypertension?")
    assert q == Query(start_type="Condition", result_type="Medication",
                      start_name="hypertension", hops=[("TREATS", "in")])


def test_translate_drugs_for():
    q = translate("drugs for hypertension")
    assert q.start_type == "Condition"
    assert q.result_type == "Medication"
    assert q.hops == [("TREATS", "in")]
    assert "hypertension" in q.start_name.lower()


def test_translate_conditions_patient_has():
    q = translate("What conditions does Patient 001 have?")
    assert q.start_type == "Patient"
    assert q.result_type == "Condition"
    assert q.hops == [("HAS_CONDITION", "out")]
    assert "001" in q.start_name


def test_translate_conditions_patient_has_trailing_verb_form():
    # Trailing-verb form (entity before the verb) must translate, matching the
    # shape advertised in the module docstring: "conditions <patient> has".
    for question in ("conditions Patient 001 has", "conditions that Patient 001 has"):
        q = translate(question)
        assert q is not None, question
        assert q.start_type == "Patient"
        assert q.result_type == "Condition"
        assert q.hops == [("HAS_CONDITION", "out")]
        assert "001" in q.start_name


def test_execute_conditions_patient_001_trailing_form():
    nodes = execute(GRAPH, translate("conditions Patient 001 has"))
    assert _names(nodes) == {"Hypertension", "Chronic Kidney Disease"}


def test_translate_patients_on_med():
    q = translate("Which patients are on metformin?")
    assert q == Query(start_type="Medication", result_type="Patient",
                      start_name="metformin",
                      hops=[("PRESCRIBED", "in"), ("HAS_ENCOUNTER", "in")])


def test_translate_who_takes():
    q = translate("who takes metformin")
    assert q.start_type == "Medication"
    assert q.result_type == "Patient"
    assert q.hops == [("PRESCRIBED", "in"), ("HAS_ENCOUNTER", "in")]


def test_translate_what_did_provider_prescribe():
    q = translate("What did Dr. Rao prescribe?")
    assert q.start_type == "Provider"
    assert q.result_type == "Medication"
    assert q.hops == [("SEEN_BY", "in"), ("PRESCRIBED", "out")]
    assert "Rao" in q.start_name


def test_translate_returns_none_when_no_match():
    assert translate("hello there, how are you?") is None


# ---- execute() over the clinical graph ------------------------------------ #

def test_execute_treat_hypertension_gives_lisinopril_and_amlodipine():
    q = translate("Which medications treat hypertension?")
    nodes = execute(GRAPH, q)
    assert _names(nodes) == {"Lisinopril", "Amlodipine"}


def test_execute_patients_on_metformin():
    q = translate("Which patients are on metformin?")
    nodes = execute(GRAPH, q)
    # Only Patient 002 was prescribed metformin (enc:1002).
    assert _names(nodes) == {"Patient 002"}


def test_execute_conditions_patient_001_has_htn_and_ckd():
    q = translate("What conditions does Patient 001 have?")
    nodes = execute(GRAPH, q)
    assert _names(nodes) == {"Hypertension", "Chronic Kidney Disease"}


def test_execute_what_did_dr_rao_prescribe():
    q = translate("What did Dr. Rao prescribe?")
    nodes = execute(GRAPH, q)
    # Dr. Rao's encounter (enc:1002) prescribed metformin and amlodipine.
    assert _names(nodes) == {"Metformin", "Amlodipine"}


def test_execute_no_match_entity_returns_empty():
    q = Query(start_type="Condition", result_type="Medication",
              start_name="nonexistent-condition", hops=[("TREATS", "in")])
    assert execute(GRAPH, q) == []
