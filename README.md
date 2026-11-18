# Wikinotizie Search

Motore di ricerca con interfaccia web sulle notizie in italiano di [it.wikinews.org](https://it.wikinews.org),
costruito sul dump Wikimedia Enterprise HTML del 20 marzo 2025.

*Ingegneria dei Dati 2026/2027 — Homework 4*

- **11.030 articoli** pubblicati (2005–2025), indicizzati con Elasticsearch 8 e un analyzer italiano personalizzato
- ricerca full-text con evidenziazione dei termini, filtri per anno, categoria e testata, ordinamento per data
- sintassi avanzata (`"frase esatta"`, `+obbligatorio`, `-escluso`, `a | b`, `prefisso*`)
- autocompletamento dei titoli, pagina dell'articolo con fonti, articoli correlati e notizie simili
- tre profili di ranking (`baseline`, `v1`, `full`) selezionabili dall'interfaccia; quello di produzione è scelto in base alla valutazione sperimentale
- strategia di test: test automatici (pytest) e valutazione offline con due collezioni di test, ablation e test di significatività

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
| `v1` | primo design: analyzer italiano, `best_fields` su `title^3`, `lead^1.5`, `body`, `categories^2`, `location`; `minimum_should_match: 2<75%`; bonus per frase esatta e shingle |
| `full` | **produzione**: analyzer italiano, `cross_fields` su `title^1.5`, `lead`, `body`; `minimum_should_match: 50%`; niente bonus per le frasi |

`full` è il risultato della valutazione: il primo design (`v1`) era **peggiore della baseline**
(MAP 0.480 contro 0.572), soprattutto perché il minimum match al 75% tagliava la recall.
Le categorie restano disponibili come filtri ma non entrano nel punteggio, così il profilo in
produzione è esattamente quello misurato. Le frasi tra virgolette sono sempre cercate sul testo
non stemmato (`.exact`).

## Strategia di test

**1. Test automatici** (`tests/`, 40 test, `pytest`):

| File | Cosa verifica |
|---|---|
| `test_parser.py` | parsing delle date, filtro delle categorie, pulizia dell'HTML (boilerplate, box, figure, tabelle), estrazione di fonti e articoli correlati, scarto di bozze e redirect |
| `test_search.py` | analyzer (elisione, stopword, accenti, stemming), ricerca di articoli noti per ogni profilo, sintassi avanzata (frasi, esclusione), filtri, faccette, ordinamento, paginazione, autocompletamento |
| `test_web.py` | pagine e API (status, contenuti, highlight, 404, parametri non validi, escaping HTML della query) |

```bash
.venv/bin/python -m pytest -q
```

I test di integrazione vengono saltati se Elasticsearch non è attivo.

**2. Valutazione offline della qualità del ranking** (`eval/`), con due collezioni di test indipendenti:

- **Topic ad-hoc** (`eval/topics.json`): 50 query scritte come le scriverebbe un utente
  (es. *"delitto di Garlasco"*). I giudizi di rilevanza vengono dalle **categorie editoriali** di
  Wikinotizie (es. *Omicidio Chiara Poggi*), assegnate dai redattori e quindi indipendenti dal
  sistema; ci sono da 12 a 93 documenti rilevanti per topic. Per evitare che la risposta entri nel
  ranking, nessun sistema valutato cerca nel campo categorie.
  Metriche: P@10, R-Precision, MAP, nDCG@10, Recall@100.
- **Known-item** (`eval/known_items.json`, generato da `eval/make_known_items.py`): 300 articoli
  casuali; per ognuno la query è formata dalle 4 parole più distintive del testo (tf-idf)
  **assenti dal titolo**, come per un utente che ricorda di cosa parlava la notizia ma non il titolo.
  Metriche: MRR, Success@1, Success@10.

Le **ablation** variano un solo aspetto di `full` alla volta (stemming, analyzer, tipo di
multi_match, minimum match, boost del titolo, bonus per le frasi, categorie). Le differenze sono
verificate con un **test di randomizzazione appaiato** (10.000 permutazioni). Per limitare
l'overfitting, `full` è stato scelto solo sui topic *dev* (posizioni pari); i topic *test*
(posizioni dispari) servono da verifica.

**3. Latenza**: 500 ricerche con il profilo di produzione, comprese faccette ed evidenziazione.

```bash
.venv/bin/python eval/evaluate.py data/processed/articles.jsonl   # -> eval/results/RESULTS.md
```

### Risultati principali

| Sistema | MAP | nDCG@10 | P@10 | MAP (topic test) | MRR known-item |
|---|---|---|---|---|---|
| baseline | 0.572 | 0.736 | 0.714 | 0.504 | 0.937 |
| v1 (primo design) | 0.480 | 0.678 | 0.654 | 0.436 | 0.922 |
| **full (produzione)** | **0.624** | **0.774** | **0.760** | **0.550** | 0.933 |

- `full` è significativamente migliore della baseline su MAP e nDCG@10, e sul known-item è allo stesso livello (differenza non significativa).
- Il fattore più importante è il **minimum_should_match**: al 75% costa 0.11 di MAP (R@100 da 0.84 a 0.65).
- I **bonus per frase/shingle peggiorano** il ranking (MAP −0.05, MRR −0.02, entrambi significativi), quindi sono stati tolti.
- **Boost del titolo**: a 3 non cambia la MAP sui topic ma fa crollare il known-item (MRR 0.84); 1.5 è il compromesso.
- **Stemming e analyzer italiano** danno un vantaggio piccolo e **non significativo** (MAP 0.624 contro 0.614 senza stemming e 0.605 con l'analyzer standard).
- **Latenza**: p50 ≈ 3 ms, p95 ≈ 5 ms.

Le tabelle complete, compresa la MAP per ogni topic, sono in [`eval/results/RESULTS.md`](eval/results/RESULTS.md).

**Limiti.** I giudizi derivati dalle categorie sono incompleti: un articolo pertinente ma non
categorizzato conta come non rilevante, il che sottostima la precisione di tutti i sistemi allo
stesso modo. Le query known-item sono sintetiche. Mancano i sinonimi: per esempio *"pandemia
coronavirus"* non trova gli articoli che dicono solo *"COVID-19"*.

## Struttura del repository

```
├── docker-compose.yml        Elasticsearch 8.15 su un solo nodo
├── es/index_settings.json    analyzer + mapping
├── requirements.txt
├── scripts/setup.sh          setup completo
├── tests/                    test automatici (pytest)
├── eval/                     topic, known-item, script di valutazione, risultati
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
