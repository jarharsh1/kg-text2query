"""End-to-end: the API serves the UI and runs text-to-query over the graph."""

from fastapi.testclient import TestClient

from gquery.api import main as api_main
from gquery.api.main import app

client = TestClient(app)


def test_sample_path_is_cwd_independent():
    # The bundled dataset path must resolve from the package location, not the
    # current working directory, so startup load works regardless of CWD.
    assert api_main._SAMPLE.is_absolute()
    assert api_main._SAMPLE.exists()


def test_health_offline():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "offline"
    assert body["graph_nodes"] > 0  # sample loaded at startup


def test_ask_returns_query_ast_and_results():
    r = client.post("/ask", json={"question": "Which medications treat hypertension?"})
    assert r.status_code == 200
    body = r.json()
    # The generated query AST must be exposed and non-null.
    assert body["query"] is not None
    assert body["query"]["start_type"] == "Condition"
    assert body["query"]["result_type"] == "Medication"
    names = {r["name"] for r in body["results"]}
    assert names == {"Lisinopril", "Amlodipine"}
    assert "lisinopril" in body["answer"].lower()


def test_ask_unmatched_question_has_null_query():
    r = client.post("/ask", json={"question": "tell me a joke"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] is None
    assert body["results"] == []


def test_index_served_with_title():
    r = client.get("/")
    assert r.status_code == 200
    assert "Text-to-Query Knowledge-Graph QA" in r.text


def test_static_js_served():
    r = client.get("/static/app.js")
    assert r.status_code == 200
    assert "/ask" in r.text
