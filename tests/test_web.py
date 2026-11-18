"""End-to-end tests of the web application (FastAPI TestClient + live index)."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import needs_es

pytestmark = needs_es

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="module")
def client():
    from src.web.app import app
    return TestClient(app)


def test_home(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Wiki" in r.text and 'name="q"' in r.text


def test_search_page_shows_results_and_highlights(client):
    r = client.get("/search", params={"q": "terremoto abruzzo"})
    assert r.status_code == 200
    assert "risultati" in r.text and "<mark>" in r.text


def test_search_with_filters_and_bad_params(client):
    r = client.get("/search", params={"q": "roma", "cat": "Sport", "year_from": 2006, "year_to": 2008,
                                      "profile": "nonexistent", "page": 9999, "sort": "date_desc"})
    assert r.status_code == 200


def test_no_results(client):
    r = client.get("/search", params={"q": "xyzqwertyzzz"})
    assert r.status_code == 200 and "Nessun" in r.text


def test_query_is_html_escaped(client):
    r = client.get("/search", params={"q": "<script>alert(1)</script>"})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_article_page_and_404(client):
    hit = client.get("/api/search", params={"q": "Giuseppe Allamano", "k": 1}).json()["hits"][0]
    r = client.get(f"/article/{hit['id']}")
    assert r.status_code == 200 and hit["title"] in r.text and "Fonti" in r.text
    assert client.get("/article/999999999").status_code == 404


def test_api_search_shape(client):
    data = client.get("/api/search", params={"q": "papa", "k": 5}).json()
    assert data["total"] > 0 and len(data["hits"]) == 5
    assert {"id", "title", "date", "score"} <= data["hits"][0].keys()


def test_api_suggest(client):
    data = client.get("/api/suggest", params={"q": "papa fra"}).json()
    assert isinstance(data, list) and data
