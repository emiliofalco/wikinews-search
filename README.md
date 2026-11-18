# Wikinotizie Search

Motore di ricerca con interfaccia web sulle notizie in italiano di [it.wikinews.org](https://it.wikinews.org),
costruito sul dump Wikimedia Enterprise HTML del 20 marzo 2025.

*Ingegneria dei Dati 2026/2027 — Homework 4*

- **11.030 articoli** pubblicati (2005–2025), indicizzati con Elasticsearch 8 e un analyzer italiano personalizzato
- ricerca full-text con evidenziazione dei termini, filtri per anno, categoria e testata, ordinamento per data
- sintassi avanzata (`"frase esatta"`, `+obbligatorio`, `-escluso`, `a | b`, `prefisso*`)
- autocompletamento dei titoli, pagina dell'articolo con fonti, articoli correlati e notizie simili
- tre profili di ranking (`baseline`, `italian`, `full`) selezionabili dall'interfaccia, usati per la valutazione

## Architettura

```
dump .json.tar.gz ──► src/parse_dump.py ──► data/processed/articles.jsonl
   (NDJSON, HTML Parsoid)   pulizia HTML, metadati          │
                                                            ▼
                                     src/index_articles.py ──► Elasticsearch (index "wikinews")
                                                                     ▲
              browser ◄──► src/web/app.py (FastAPI + Jinja) ──► src/search.py
```

| Componente | File | Ruolo |
|---|---|---|
| Parsing | `src/parse_dump.py` | Legge il dump (anche direttamente dal `.tar.gz`), tiene solo gli articoli *pubblicati*, estrae testo pulito dall'HTML, data, luogo, categorie tematiche, fonti, articoli correlati, immagine |
| Mapping | `es/index_settings.json` | Analyzer italiano, sotto-campi per gli esperimenti (`.std`, `.exact`, `.shingles`), autocompletamento |
| Indicizzazione | `src/index_articles.py` | Crea l'indice e carica i documenti in bulk |
| Query | `src/search.py` | Costruzione delle query, profili di ranking, filtri, faccette, highlight, suggerimenti; usabile anche da CLI |
| Web | `src/web/` | Applicazione FastAPI con template Jinja |

## Requisiti

- Python ≥ 3.11
- Docker (per Elasticsearch 8.15)
- circa 1,5 GB di spazio disco (dump estratto + indice)

## Installazione

Setup completo in un comando (virtualenv, download del dump, parsing, avvio di Elasticsearch, indicizzazione):

```bash
./scripts/setup.sh
```

Oppure passo per passo:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. download del dump (~73 MB)
mkdir -p data/raw
curl -L -o data/raw/itwikinews.json.tar.gz \
  https://dumps.wikimedia.org/other/enterprise_html/runs/20250320/itwikinews-NS0-20250320-ENTERPRISE-HTML.json.tar.gz

# 2. parsing -> data/processed/articles.jsonl (+ articles_stats.json)
.venv/bin/python src/parse_dump.py data/raw/itwikinews.json.tar.gz data/processed/articles.jsonl

# 3. Elasticsearch
docker compose up -d

# 4. indicizzazione
.venv/bin/python src/index_articles.py data/processed/articles.jsonl --recreate
```

## Utilizzo

### Interfaccia web

```bash
.venv/bin/uvicorn src.web.app:app --port 8000
```

Poi apri <http://localhost:8000>.

### Riga di comando

```bash
.venv/bin/python src/search.py "terremoto in abruzzo" --profile full -k 10
```

### API JSON

| Endpoint | Descrizione |
|---|---|
| `GET /api/search?q=...&profile=full&k=10` | primi `k` risultati (id, titolo, data, punteggio) |
| `GET /api/suggest?q=...` | suggerimenti di titoli per l'autocompletamento |

### Sintassi di ricerca

| Query | Significato |
|---|---|
| `papa francesco` | testo libero (con due termini sono richiesti entrambi; con più termini almeno il 75%) |
| `"governo Prodi"` | frase esatta |
| `+roma -lazio` | `roma` obbligatorio, `lazio` escluso |
| `milano \| torino` | almeno uno dei due |
| `olimp*` | ricerca per prefisso |

## Scelte progettuali

**Parsing.** Si usa l'HTML (Parsoid) del dump invece del wikitext, perché ha già i template espansi.
Il parser toglie il boilerplate (riga della data, "Dì la tua", box di condivisione, riquadri di
navigazione, figure, tabelle) e legge fonti e articoli correlati dai parametri dei template
`{{fonte}}`/`{{fonteestera}}`/`{{wikinotizie}}`. La data di pubblicazione viene da `{{data}}`/`{{luogodata}}`
(99,3% degli articoli). Le categorie redazionali e di servizio vengono scartate. Gli articoli senza
testo, fatti solo di tabelle (es. estrazioni del Lotto), conservano il testo delle tabelle.

**Analyzer italiano** (`it_text`): tokenizer standard → elisione (`l'`, `dell'`, `nell'`…) → minuscole
→ stopword italiane → rimozione degli accenti → stemming *light_italian*.
Esempio: *"L'Unione Europea dell'Italia"* → `union`, `europe`, `ital`.

**Profili di ranking** (BM25):

| Profilo | Descrizione |
|---|---|
| `baseline` | analyzer standard, campi `title` + `body`, OR fra i termini |
| `italian` | analyzer italiano; `title^3`, `lead^1.5`, `body`, `categories^2`, `location`; `minimum_should_match: 2<75%` |
| `full` | `italian` + bonus per frase esatta nel titolo/testo e per coppie di parole adiacenti (shingle) |

## Struttura del repository

```
├── docker-compose.yml        Elasticsearch 8.15 su un solo nodo
├── es/index_settings.json    analyzer + mapping
├── requirements.txt
├── scripts/setup.sh          setup completo
└── src/
    ├── parse_dump.py
    ├── index_articles.py
    ├── search.py
    └── web/                  app FastAPI, template, CSS/JS
```

I dati (`data/`) non sono versionati: si rigenerano con gli script.

## Licenza dei contenuti

I testi delle notizie sono di Wikinotizie, rilasciati con licenza
[CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/).
