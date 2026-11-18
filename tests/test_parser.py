"""Unit tests for the dump parser (no Elasticsearch needed)."""

import html
import json

import parse_dump as p


# ----------------------------------------------------------------- dates ---

def test_parse_it_date_basic():
    assert p.parse_it_date("9 giugno 2020") == "2020-06-09"
    assert p.parse_it_date("martedì 1º Gennaio 2008") == "2008-01-01"


def test_parse_it_date_rejects_garbage():
    assert p.parse_it_date("nessuna data qui") is None
    assert p.parse_it_date("40 marzo 2008") is None
    assert p.parse_it_date("3 marzo 1850") is None


def test_date_from_data_template():
    assert p.extract_date_and_place("{{data|31 marzo 2008|lunedì}}\ntesto", "") == \
        ("2008-03-31", "template", None)


def test_date_and_place_from_luogodata():
    wt = "{{luogodata|mercoledì|luogo=Roma|data=4 novembre 2020}}"
    assert p.extract_date_and_place(wt, "") == ("2020-11-04", "template", "Roma")


def test_date_falls_back_to_abstract():
    assert p.extract_date_and_place("nessun template", "martedì 9 giugno 2020 Dopo...") == \
        ("2020-06-09", "abstract", None)


# ------------------------------------------------------------ categories ---

def test_topical_categories_drop_editorial_and_dates():
    cats = [{"name": f"Categoria:{n}"} for n in
            ["Pubblicati", "Articoli archiviati", "Europa", "9 giugno 2020",
             "Articolo in CC BY-SA", "Notizie da prima pagina", "Belgio"]]
    assert p.topical_categories(cats) == ["Europa", "Belgio"]


# ------------------------------------------------------------------ HTML ---

def _tpl(name, params=None, about="#mwt1"):
    data = {"parts": [{"template": {"target": {"wt": name},
                                    "params": {k: {"wt": v} for k, v in (params or {}).items()}}}]}
    return f'about="{about}" typeof="mw:Transclusion" data-mw="{html.escape(json.dumps(data))}"'


HTML = f"""<html><body>
<section data-mw-section-id="0">
  <p><span {_tpl('data', {'1': '9 giugno 2020'}, '#mwt0')}>martedì 9 giugno 2020</span></p>
  <div style="display:block" {_tpl('SismaAbruzzo', about='#mwt5')}>Speciale sul sisma</div>
  <div about="#mwt5" style="float:left">Tutti gli articoli dello Speciale</div>
  <figure><figcaption>Didascalia da ignorare</figcaption></figure>
  <p>Dopo l'<a rel="mw:WikiLink" href="./X">abbattimento</a> della statua di Colston a Bristol, anche a Bruxelles<br>si protesta contro Leopoldo II.</p>
  <table><tr><td>tabella</td></tr></table>
  <div class="center" {_tpl('dì la tua', about='#mwt3')}><p>Hai un'opinione su questo evento?</p></div>
</section>
<section data-mw-section-id="1"><h2>Articoli correlati</h2>
  <ul><li {_tpl('Wikinotizie', {'1': 'Statua abbattuta a Bristol'}, '#mwt6')}>Statua abbattuta a Bristol</li></ul>
</section>
<section data-mw-section-id="2"><h2>Fonti</h2>
  <ul {_tpl('fonte', {'url': 'https://www.ilpost.it/x', 'titolo': "''Statue''", 'agenzia': 'il Post',
                      'data': '8 giugno 2020'}, '#mwt7')}><li>il Post</li></ul>
</section>
</body></html>"""


def test_parse_html_body_is_clean():
    body, _, _ = p.parse_html(HTML)
    assert body == ("Dopo l'abbattimento della statua di Colston a Bristol, anche a Bruxelles\n"
                    "si protesta contro Leopoldo II.")
    for noise in ("Speciale", "Didascalia", "tabella", "opinione", "giugno 2020", "Statua abbattuta"):
        assert noise not in body


def test_parse_html_extracts_sources_and_related():
    _, sources, related = p.parse_html(HTML)
    assert sources == [{"title": "Statue", "url": "https://www.ilpost.it/x", "publisher": "il Post",
                        "author": "", "date": "8 giugno 2020", "lang": "it", "printed": False}]
    assert related == ["Statua abbattuta a Bristol"]


def test_table_only_article_keeps_table_text():
    html = "<html><body><section><table><tr><th>Bari</th><td>36</td><td>21</td></tr></table></section></body></html>"
    body, _, _ = p.parse_html(html)
    assert body == "Bari | 36 | 21"


# ---------------------------------------------------------- full record ---

def _record(cats=("Categoria:Pubblicati", "Categoria:Europa"), wikitext="{{data|9 giugno 2020}}"):
    return json.dumps({
        "name": "Titolo di prova", "identifier": 42, "url": "https://it.wikinews.org/wiki/T",
        "date_modified": "2024-01-01T00:00:00Z",
        "categories": [{"name": c} for c in cats], "templates": [],
        "article_body": {"html": HTML, "wikitext": wikitext},
    })


def test_process_published_article():
    status, art = p.process(_record())
    assert status == "ok"
    assert art["id"] == 42 and art["date"] == "2020-06-09"
    assert art["categories"] == ["Europa"]
    assert art["lead"] == art["body"].split("\n\n")[0]
    assert art["n_chars"] == len(art["body"])


def test_process_skips_drafts_and_redirects():
    assert p.process(_record(cats=("Categoria:Bozze",)))[0] == "not_published"
    assert p.process(_record(wikitext="#RINVIA [[Altro]]"))[0] == "redirect"
    assert p.process("{not json")[0] == "bad_json"
