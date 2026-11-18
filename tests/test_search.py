"""Integration tests against the live Elasticsearch index."""

import pytest

from conftest import needs_es
from search import PROFILES, Filters, RankConfig, text_query

pytestmark = needs_es


# ------------------------------------------------------------- analyzer ---

def analyze(searcher, text, analyzer="it_text"):
    res = searcher.es.indices.analyze(index=searcher.index, analyzer=analyzer, text=text)
    return [t["token"] for t in res["tokens"]]


def test_italian_analyzer_elision_stopwords_folding(searcher):
    assert analyze(searcher, "L'Unione dell'Italia è la città") == ["union", "ital", "citta"]


def test_italian_analyzer_conflates_inflections(searcher):
    # singular/plural and gender variants share the same stem
    assert len(set(analyze(searcher, "terremoto terremoti"))) == 1
    assert len(set(analyze(searcher, "elezione elezioni"))) == 1


# ------------------------------------------------------- index sanity ---

def test_index_contains_all_articles(searcher):
    assert searcher.es.count(index=searcher.index)["count"] > 10_000


def test_empty_query_returns_everything(searcher):
    res = searcher.search("", size=1)
    assert res["hits"]["total"]["value"] == searcher.es.count(index=searcher.index)["count"]


# ----------------------------------------------------- ranking (smoke) ---

@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("query,expected", [
    ("nuova fortissima scossa terremoto abruzzo", "Nuova fortissima scossa di terremoto in Abruzzo"),
    ("Giuseppe Allamano santo", "Papa Francesco: Giuseppe Allamano sarà proclamato santo"),
])
def test_known_article_in_top3(searcher, profile, query, expected):
    titles = [h["_source"]["title"] for h in searcher.search(query, profile=profile, size=3)["hits"]["hits"]]
    assert expected in titles


def test_stemming_matches_inflected_forms(searcher):
    # "terremoti" (plural) must find documents whose title says "terremoto"
    res = searcher.search("terremoti", profile="full", size=50, facets=False, highlight=False)
    assert any("terremoto" in h["_source"]["title"].lower() for h in res["hits"]["hits"])


def test_accent_insensitive(searcher):
    a = searcher.search("citta", profile="full", size=0)["hits"]["total"]["value"]
    b = searcher.search("città", profile="full", size=0)["hits"]["total"]["value"]
    assert a == b > 0


# -------------------------------------------------------- query syntax ---

def test_advanced_syntax_detection():
    assert "simple_query_string" in text_query('"governo Prodi"')
    assert "simple_query_string" in text_query("roma -lazio")
    assert "simple_query_string" not in text_query("roma-lazio 2-1")


def test_exclusion_operator(searcher):
    res = searcher.search('"governo Prodi" -Berlusconi', size=50, highlight=False, facets=False)
    assert res["hits"]["total"]["value"] > 0
    for h in res["hits"]["hits"]:
        doc = searcher.get(h["_source"]["id"])
        assert "berlusconi" not in (doc["title"] + " " + doc["body"]).lower()


def test_phrase_query_requires_adjacency(searcher):
    res = searcher.search('"Romano Prodi"', size=20, highlight=False, facets=False)
    for h in res["hits"]["hits"]:
        doc = searcher.get(h["_source"]["id"])
        text = (doc["title"] + " " + doc["body"] + " " + doc["lead"]).lower()
        assert "romano prodi" in text


def test_rank_config_fields():
    assert RankConfig(suffix=".exact").fields()[:2] == ["title.exact^3", "body.exact"]
    assert "categories.text^2" not in RankConfig(use_categories=False).fields()


# ------------------------------------------------------------- filters ---

def test_year_filter(searcher):
    res = searcher.search("calcio", filters=Filters(year_from=2010, year_to=2012), size=50, highlight=False)
    years = {int(h["_source"]["date"][:4]) for h in res["hits"]["hits"]}
    assert years and years <= {2010, 2011, 2012}


def test_category_filter_and_facets(searcher):
    res = searcher.search("", filters=Filters(categories=["Sport"]), size=30, highlight=False)
    assert all("Sport" in h["_source"]["categories"] for h in res["hits"]["hits"])
    facet = {b["key"]: b["doc_count"] for b in res["aggregations"]["categories"]["buckets"]}
    assert facet["Sport"] == res["hits"]["total"]["value"]


def test_sort_by_date(searcher):
    res = searcher.search("elezioni", sort="date_desc", size=30, highlight=False, facets=False)
    dates = [h["_source"]["date"] for h in res["hits"]["hits"] if h["_source"].get("date")]
    assert dates == sorted(dates, reverse=True)


def test_pagination_is_disjoint(searcher):
    p1 = searcher.ids("roma", "full", k=10)
    p2 = [h["_source"]["id"] for h in searcher.search("roma", page=2, size=10, facets=False,
                                                       highlight=False)["hits"]["hits"]]
    assert len(p2) == 10 and not set(p1) & set(p2)


# ------------------------------------------------------- autocomplete ---

def test_suggest_requires_all_words(searcher):
    sugg = searcher.suggest("olimpiadi tor")
    assert sugg
    assert all("olimpiadi" in s.lower() and "tor" in s.lower() for s in sugg)
