"""Parse the Wikimedia Enterprise HTML dump of it.wikinews into clean JSONL.

Each input line is one page (NDJSON). For every published news article we emit:

    id, title, url, date (YYYY-MM-DD), location, categories, lead, body,
    sources [{title, url, publisher, date}], related [titles],
    image, wikidata, archived, n_chars

Usage:
    python src/parse_dump.py data/raw/itwikinews.json.tar.gz data/processed/articles.jsonl
    (the input can also be the extracted .ndjson file)
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import tarfile
from multiprocessing import Pool
from pathlib import Path
from typing import Iterator

from bs4 import BeautifulSoup, Tag

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

MONTHS = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
    "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10,
    "novembre": 11, "dicembre": 12,
}
DATE_RE = re.compile(
    r"(\d{1,2})\s*(?:º|°)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", re.IGNORECASE
)
DATE_TEMPLATE_RE = re.compile(r"\{\{\s*(?:data|luogodata)\s*\|([^{}]*)\}\}", re.IGNORECASE)
LUOGO_RE = re.compile(r"luogo\s*=\s*([^|}]+)", re.IGNORECASE)

# Templates that are pure boilerplate: their rendered output is removed from the body.
BOILERPLATE_TEMPLATES = {
    "data", "luogodata", "dì la tua", "dìlatua", "dì_la_tua", "pubblicato",
    "archiviato", "wikinotizie", "wikipedia", "fonte", "condividi", "commons",
    "wikiquote", "wikisource", "interprogetto", "sviluppo", "notizia in sviluppo",
    "fonteestera", "fontecarta", "notizia per wikivoyage", "wikivoyage", "clear",
    "articolo da non elencare",
}
# Templates citing a source: parameters url / titolo / agenzia / autore / data / lingua.
SOURCE_TEMPLATES = {"fonte", "fonteestera", "fontecarta", "notizia per wikivoyage"}
# Block (div) templates that carry real article text; every other div-rendered
# template is a banner / navigation box (e.g. {{SismaAbruzzo}}) and is dropped.
KEEP_DIV_TEMPLATES = {"w@h domanda"}

# Sections (h2) that are not part of the article text.
NON_BODY_SECTIONS = {
    "fonti", "articoli correlati", "notizie correlate", "collegamenti esterni",
    "note", "voci correlate", "altri progetti", "approfondimenti", "bibliografia",
}

# Editorial / maintenance categories, not useful as topical facets.
CATEGORY_DROP_PREFIXES = (
    "Pubblicati", "Articoli ", "Pagine ", "Da ", "Bozze", "Notizie da prima pagina",
    "Notizie originali", "Notizie in sviluppo", "Errori ", "Template ", "Voci ", "Categoria da definire",
    "Articolo in ",
)

PUBLISHED_CAT = "Categoria:Pubblicati"
ARCHIVED_CAT = "Categoria:Articoli archiviati"

FLOAT_RE = re.compile(r"float\s*:\s*(left|right)", re.IGNORECASE)
WS_RE = re.compile(r"[ \t ​]+")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def clean_ws(text: str) -> str:
    text = WS_RE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_it_date(text: str) -> str | None:
    m = DATE_RE.search(text or "")
    if not m:
        return None
    day, month, year = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
    if not (1 <= day <= 31 and 1990 <= year <= 2030):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def extract_date_and_place(wikitext: str, abstract: str) -> tuple[str | None, str, str | None]:
    """Publication date from {{data}} / {{luogodata}}, falling back to the abstract."""
    m = DATE_TEMPLATE_RE.search(wikitext or "")
    if m:
        args = m.group(1)
        place = LUOGO_RE.search(args)
        date = parse_it_date(args)
        if date:
            return date, "template", place.group(1).strip() if place else None
    date = parse_it_date((abstract or "")[:80])
    if date:
        return date, "abstract", None
    return None, "none", None


def template_names(el: Tag) -> list[str]:
    raw = el.get("data-mw")
    if not raw:
        return []
    try:
        parts = json.loads(raw).get("parts", [])
    except (ValueError, AttributeError):
        return []
    names = []
    for p in parts:
        if isinstance(p, dict) and "template" in p:
            wt = p["template"].get("target", {}).get("wt", "")
            names.append(wt.strip().lower().replace("_", " "))
    return names


def template_params(el: Tag) -> list[tuple[str, dict]]:
    try:
        parts = json.loads(el.get("data-mw", "{}")).get("parts", [])
    except ValueError:
        return []
    out = []
    for p in parts:
        if isinstance(p, dict) and "template" in p:
            t = p["template"]
            name = t.get("target", {}).get("wt", "").strip().lower()
            params = {k: v.get("wt", "") for k, v in t.get("params", {}).items()}
            out.append((name, params))
    return out


def strip_wikitext(s: str) -> str:
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\S+\s+([^\]]*)\]", r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    return clean_ws(re.sub(r"<[^>]+>", "", s))


def block_text(el: Tag) -> str:
    # Inline elements (links, bold...) must not introduce spaces: "l'<a>Unione</a>"
    return clean_ws(el.get_text(""))


# --------------------------------------------------------------------------- #
# Article parsing
# --------------------------------------------------------------------------- #

def parse_html(html: str) -> tuple[str, list[dict], list[str]]:
    soup = BeautifulSoup(html, "lxml")
    body_el = soup.body or soup

    for br in body_el.find_all("br"):
        br.replace_with("\n")

    # 1. Collect sources ({{fonte}}) and related articles ({{wikinotizie}})
    #    from template parameters, before boilerplate removal.
    sources, seen_urls, related = [], set(), []
    for el in body_el.find_all(attrs={"data-mw": True}):
        for name, params in template_params(el):
            if name in SOURCE_TEMPLATES:
                url = params.get("url", "").strip()
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                sources.append({
                    "title": strip_wikitext(params.get("titolo", "")),
                    "url": url,
                    "publisher": strip_wikitext(params.get("agenzia") or params.get("giornale", "")),
                    "author": strip_wikitext(params.get("autore", "")),
                    "date": strip_wikitext(params.get("data", "")),
                    "lang": params.get("lingua", "").strip() or "it",
                    "printed": name == "fontecarta",
                })
            elif name == "wikinotizie":
                t = strip_wikitext(params.get("titolo") or params.get("1", ""))
                if t:
                    related.append(t)

    # 2. Remove boilerplate transclusions (all nodes sharing the same `about`).
    bad_about = set()
    for el in body_el.find_all(attrs={"typeof": re.compile("mw:Transclusion")}):
        if el.decomposed:  # already removed together with an ancestor
            continue
        names = template_names(el)
        is_banner = el.name == "div" and not any(n in KEEP_DIV_TEMPLATES for n in names)
        if is_banner or any(n in BOILERPLATE_TEMPLATES for n in names):
            if el.get("about"):
                bad_about.add(el["about"])
            el.decompose()
    for about in bad_about:
        for el in body_el.find_all(attrs={"about": about}):
            if not el.decomposed:
                el.decompose()

    # Tables (lotto draws, match results...) are kept aside: used only when
    # the article has no running text at all.
    table_text = "\n".join(
        " | ".join(block_text(c) for c in row.find_all(["td", "th"]) if block_text(c))
        for row in body_el.select("table tr")
    )

    # Floating boxes are navigation sidebars (e.g. {{SismaAbruzzo}} "Speciale" boxes),
    # not article text.
    for el in body_el.find_all(["div", "aside"], style=FLOAT_RE):
        el.decompose()

    # 3. Remove non-textual / noisy elements.
    for sel in ["figure", "table", "style", "script", "sup.reference", "ol.references",
                ".noprint", "#commentrequest", "#condivisione-articolo", "#social_bookmark",
                "link", "meta", ".mw-empty-elt", "span[typeof='mw:File']"]:
        for el in body_el.select(sel):
            el.decompose()

    # 4. Walk sections: keep body sections, harvest related articles.
    paragraphs = []
    sections = body_el.find_all("section", recursive=True)
    for sec in sections:
        if sec.find_parent("section"):
            continue  # nested sections are handled through their top-level parent
        h = sec.find(["h2", "h3"], recursive=False)
        heading = block_text(h).lower() if h else ""
        if heading in ("articoli correlati", "notizie correlate"):
            for a in sec.find_all("a", rel="mw:WikiLink"):
                t = a.get("title")
                if t and not t.startswith(("Categoria:", "File:", "Immagine:")):
                    related.append(t)
            continue
        if heading in NON_BODY_SECTIONS:
            continue
        for el in sec.find_all(["p", "li", "blockquote", "h2", "h3", "h4", "dd"]):
            # avoid double counting nested blocks (e.g. p inside blockquote, li inside li)
            if el.find_parent(["blockquote", "li", "dd"]) and el.name in ("p", "li", "dd"):
                continue
            if el.name in ("h2", "h3", "h4") and el.find_parent("section") is not sec and \
                    block_text(el).lower() in NON_BODY_SECTIONS:
                continue
            txt = block_text(el)
            if txt:
                paragraphs.append(txt)

    body = "\n\n".join(paragraphs)
    if len(body) < 80 and table_text.strip():
        body = clean_ws((body + "\n\n" + table_text).strip())
    return body, sources, list(dict.fromkeys(related))


def topical_categories(cats: list[dict]) -> list[str]:
    out = []
    for c in cats or []:
        name = c.get("name", "").removeprefix("Categoria:")
        if name and not name.startswith(CATEGORY_DROP_PREFIXES) and not DATE_RE.fullmatch(name):
            out.append(name)
    return out


def process(line: str) -> tuple[str, dict | None]:
    """Return (status, article). status is 'ok' or a skip reason."""
    try:
        d = json.loads(line)
    except ValueError:
        return "bad_json", None

    cat_names = {c.get("name") for c in d.get("categories") or []}
    tmpl_names = {t.get("name") for t in d.get("templates") or []}
    if PUBLISHED_CAT not in cat_names and "Template:Pubblicato" not in tmpl_names:
        return "not_published", None

    art_body = d.get("article_body") or {}
    wikitext = art_body.get("wikitext", "")
    if re.match(r"\s*#(RINVIA|REDIRECT)", wikitext, re.IGNORECASE):
        return "redirect", None

    body, sources, related = parse_html(art_body.get("html", ""))
    if len(body) < 80:
        return "too_short", None

    abstract = d.get("abstract") or ""
    date, date_src, place = extract_date_and_place(wikitext, abstract)
    lead = body.split("\n\n", 1)[0]

    return "ok", {
        "id": d["identifier"],
        "title": d["name"],
        "url": d["url"],
        "date": date,
        "date_source": date_src,
        "location": place,
        "categories": topical_categories(d.get("categories")),
        "lead": lead,
        "body": body,
        "sources": sources,
        "related": related,
        "image": (d.get("image") or {}).get("content_url"),
        "wikidata": (d.get("main_entity") or {}).get("identifier"),
        "archived": ARCHIVED_CAT in cat_names,
        "last_modified": d.get("date_modified"),
        "n_chars": len(body),
    }


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def iter_lines(path: Path) -> Iterator[str]:
    if path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(path, "r:gz") as tar:
            for member in tar:
                if member.isfile() and member.name.endswith(".ndjson"):
                    f = tar.extractfile(member)
                    assert f is not None
                    for raw in f:
                        yield raw.decode("utf-8")
    else:
        with path.open(encoding="utf-8") as f:
            yield from f


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    stats = collections.Counter()
    date_src = collections.Counter()
    years = collections.Counter()
    cats = collections.Counter()
    seen_titles = set()

    with Pool(args.workers) as pool, args.output.open("w", encoding="utf-8") as out:
        for i, (status, art) in enumerate(pool.imap(process, iter_lines(args.input), chunksize=32), 1):
            if status == "ok" and art["title"] in seen_titles:
                status = "duplicate"
            stats[status] += 1
            if status == "ok":
                seen_titles.add(art["title"])
                date_src[art["date_source"]] += 1
                years[(art["date"] or "????")[:4]] += 1
                cats.update(art["categories"])
                out.write(json.dumps(art, ensure_ascii=False) + "\n")
            if i % 2000 == 0:
                print(f"  {i} pages processed...", file=sys.stderr)

    report = {
        "pages": sum(stats.values()),
        "status": dict(stats),
        "date_source": dict(date_src),
        "articles_per_year": dict(sorted(years.items())),
        "top_categories": cats.most_common(30),
    }
    stats_path = args.output.with_name(args.output.stem + "_stats.json")
    stats_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
