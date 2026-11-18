# Risultati sperimentali

## Topic ad-hoc (50 query, giudizi = categorie editoriali, profondità 100)

| Sistema | Descrizione | P@10 | R-Prec | MAP | nDCG@10 | R@100 | MAP dev | MAP test |
|---|---|---|---|---|---|---|---|---|
| baseline | analyzer standard, title+body, OR | 0.714 | 0.582 | 0.572 * | 0.736 * | 0.800 | 0.639 | 0.504 |
| v1 | primo design: best_fields, title^3, mm 2<75%, frasi | 0.654 | 0.533 | 0.480 * | 0.678 * | 0.627 | 0.524 | 0.436 |
| full | produzione: italiano, cross_fields, title^1.5, mm 50% | 0.760 | 0.628 | 0.624 | 0.774 | 0.835 | 0.698 | 0.550 |
| -stemming | full senza stemming/stopword (campi .exact) | 0.752 | 0.611 | 0.614 | 0.770 | 0.832 | 0.686 | 0.541 |
| analyzer std | full con analyzer standard | 0.756 | 0.602 | 0.605 | 0.771 | 0.811 | 0.673 | 0.536 |
| best_fields | full con best_fields invece di cross_fields | 0.758 | 0.611 | 0.610 * | 0.773 | 0.826 | 0.678 | 0.543 |
| mm 2<75% | full con minimum_should_match 2<75% | 0.720 | 0.544 | 0.517 * | 0.746 * | 0.653 | 0.581 | 0.454 |
| OR | full senza minimum_should_match | 0.760 | 0.628 | 0.624 | 0.774 | 0.835 | 0.698 | 0.550 |
| title^3 | full con boost titolo 3 | 0.758 | 0.627 | 0.618 | 0.776 | 0.833 | 0.677 | 0.558 |
| +frasi | full + bonus frase esatta/shingle | 0.672 | 0.597 | 0.573 * | 0.687 * | 0.822 | 0.643 | 0.503 |

## Known-item (300 query)

| Sistema | MRR | Success@1 | Success@10 | non trovati in top-100 |
|---|---|---|---|---|
| baseline | 0.937 | 0.910 | 0.977 | 2 |
| v1 | 0.922 | 0.887 | 0.980 | 4 |
| full | 0.933 | 0.907 | 0.980 | 3 |
| -stemming | 0.938 | 0.913 | 0.977 | 2 |
| analyzer std | 0.929 | 0.897 | 0.977 | 2 |
| best_fields | 0.930 | 0.903 | 0.980 | 3 |
| mm 2<75% | 0.932 | 0.907 | 0.977 | 4 |
| OR | 0.933 | 0.907 | 0.980 | 3 |
| title^3 | 0.838 * | 0.757 | 0.963 | 3 |
| +frasi | 0.915 * | 0.873 | 0.980 | 3 |
| +categorie | 0.925 | 0.897 | 0.980 | 3 |

\* differenza rispetto a `full` statisticamente significativa (test di randomizzazione appaiato, 10.000 permutazioni, p < 0.05).

`full` è stato scelto con una grid search sui soli topic *dev* (posizioni pari) e sul known-item; i topic *test* (posizioni dispari) non sono stati usati per nessuna scelta.

## Latenza (profilo di produzione, con faccette ed evidenziazione)

500 ricerche: media 2.9 ms, p50 2.6 ms, p95 4.5 ms, max 14.2 ms (tempo interno di Elasticsearch: media 1.4 ms).

## MAP per topic

| Topic | Query | #rel | baseline | v1 | full | -stemming | analyzer std | best_fields | mm 2<75% | OR | title^3 | +frasi |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | influenza aviaria | 12 | 0.918 | 0.902 | 0.987 | 0.987 | 0.934 | 0.981 | 0.910 | 0.987 | 0.976 | 0.974 |
| T02 | pandemia coronavirus | 78 | 0.330 | 0.021 | 0.354 | 0.352 | 0.351 | 0.346 | 0.049 | 0.354 | 0.371 | 0.346 |
| T03 | proteste dopo la morte di George Floyd | 17 | 0.709 | 0.587 | 0.709 | 0.747 | 0.704 | 0.740 | 0.635 | 0.705 | 0.669 | 0.677 |
| T04 | terremoto dell'Aquila 2009 | 15 | 0.103 | 0.212 | 0.183 | 0.107 | 0.112 | 0.166 | 0.222 | 0.183 | 0.072 | 0.183 |
| T05 | delitto di Garlasco | 14 | 0.667 | 0.500 | 0.676 | 0.663 | 0.676 | 0.638 | 0.500 | 0.676 | 0.548 | 0.709 |
| T06 | rapimento del piccolo Tommaso | 17 | 0.911 | 0.765 | 0.932 | 0.957 | 0.957 | 0.923 | 0.748 | 0.932 | 0.963 | 0.872 |
| T07 | emergenza rifiuti a Napoli | 20 | 0.695 | 0.778 | 0.759 | 0.759 | 0.666 | 0.693 | 0.784 | 0.759 | 0.649 | 0.669 |
| T08 | olimpiadi di Pechino | 70 | 0.600 | 0.457 | 0.711 | 0.766 | 0.707 | 0.692 | 0.642 | 0.711 | 0.862 | 0.675 |
| T09 | giochi olimpici invernali di Torino | 43 | 0.740 | 0.860 | 0.850 | 0.853 | 0.854 | 0.844 | 0.880 | 0.850 | 0.887 | 0.860 |
| T10 | mondiali di calcio in Sudafrica | 44 | 0.175 | 0.569 | 0.389 | 0.494 | 0.385 | 0.425 | 0.453 | 0.389 | 0.568 | 0.125 |
| T11 | mondiali di calcio Germania 2006 | 42 | 0.650 | 0.471 | 0.736 | 0.800 | 0.791 | 0.703 | 0.726 | 0.736 | 0.756 | 0.451 |
| T12 | europei di calcio 2008 | 14 | 0.031 | 0.434 | 0.459 | 0.106 | 0.150 | 0.429 | 0.459 | 0.459 | 0.459 | 0.454 |
| T13 | Jannik Sinner | 14 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| T14 | Roger Federer | 18 | 0.911 | 0.881 | 0.961 | 0.949 | 0.955 | 0.946 | 0.964 | 0.961 | 0.980 | 0.857 |
| T15 | rally Parigi Dakar | 16 | 0.905 | 0.844 | 0.912 | 0.952 | 0.935 | 0.959 | 0.912 | 0.912 | 0.989 | 0.844 |
| T16 | Tour de France | 33 | 0.912 | 0.942 | 0.894 | 0.910 | 0.930 | 0.942 | 0.894 | 0.894 | 0.924 | 0.941 |
| T17 | festival di Sanremo | 17 | 0.613 | 0.618 | 0.698 | 0.704 | 0.723 | 0.689 | 0.680 | 0.698 | 0.746 | 0.624 |
| T18 | Eurovision Song Contest | 33 | 0.777 | 0.811 | 0.764 | 0.777 | 0.810 | 0.783 | 0.764 | 0.764 | 0.790 | 0.808 |
| T19 | festival del film di Locarno | 13 | 0.497 | 0.367 | 0.491 | 0.506 | 0.467 | 0.440 | 0.512 | 0.491 | 0.252 | 0.297 |
| T20 | vincitori del premio Nobel | 15 | 0.300 | 0.347 | 0.343 | 0.312 | 0.333 | 0.350 | 0.343 | 0.343 | 0.356 | 0.343 |
| T21 | missioni spaziali NASA | 71 | 0.487 | 0.617 | 0.805 | 0.510 | 0.492 | 0.799 | 0.648 | 0.805 | 0.803 | 0.805 |
| T22 | crisi dei mutui subprime | 37 | 0.321 | 0.242 | 0.330 | 0.339 | 0.348 | 0.327 | 0.231 | 0.330 | 0.314 | 0.309 |
| T23 | crisi Alitalia | 18 | 0.775 | 0.151 | 0.786 | 0.763 | 0.815 | 0.759 | 0.151 | 0.786 | 0.778 | 0.786 |
| T24 | Apple iPhone | 18 | 0.689 | 0.246 | 0.671 | 0.667 | 0.685 | 0.709 | 0.243 | 0.671 | 0.707 | 0.671 |
| T25 | Microsoft Windows | 24 | 0.826 | 0.360 | 0.851 | 0.831 | 0.848 | 0.862 | 0.458 | 0.851 | 0.989 | 0.697 |
| T26 | software libero e Linux | 18 | 0.780 | 0.657 | 0.788 | 0.771 | 0.785 | 0.768 | 0.661 | 0.788 | 0.702 | 0.786 |
| T27 | processo a Saddam Hussein | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| T28 | guerra in Iraq | 21 | 0.248 | 0.189 | 0.326 | 0.309 | 0.297 | 0.310 | 0.172 | 0.326 | 0.329 | 0.308 |
| T29 | invasione russa dell'Ucraina | 36 | 0.133 | 0.223 | 0.306 | 0.294 | 0.135 | 0.298 | 0.228 | 0.306 | 0.271 | 0.299 |
| T30 | guerra tra Israele e Hamas a Gaza | 48 | 0.438 | 0.236 | 0.469 | 0.464 | 0.471 | 0.443 | 0.366 | 0.469 | 0.422 | 0.344 |
| T31 | guerra in Libano 2006 | 47 | 0.665 | 0.198 | 0.704 | 0.672 | 0.675 | 0.584 | 0.316 | 0.704 | 0.587 | 0.571 |
| T32 | Obama elezioni presidenziali americane 2008 | 27 | 0.300 | 0.199 | 0.411 | 0.322 | 0.310 | 0.270 | 0.349 | 0.410 | 0.361 | 0.208 |
| T33 | Donald Trump | 17 | 0.689 | 0.685 | 0.758 | 0.729 | 0.757 | 0.774 | 0.727 | 0.758 | 0.771 | 0.717 |
| T34 | elezioni politiche 2006 Prodi Berlusconi | 44 | 0.188 | 0.180 | 0.189 | 0.200 | 0.206 | 0.179 | 0.176 | 0.189 | 0.214 | 0.190 |
| T35 | caduta del governo Prodi | 14 | 0.139 | 0.162 | 0.146 | 0.143 | 0.149 | 0.157 | 0.149 | 0.146 | 0.146 | 0.062 |
| T36 | governo Renzi | 21 | 0.306 | 0.283 | 0.304 | 0.312 | 0.302 | 0.280 | 0.268 | 0.304 | 0.276 | 0.324 |
| T37 | Umberto Bossi Lega Nord | 27 | 0.607 | 0.398 | 0.642 | 0.613 | 0.632 | 0.646 | 0.459 | 0.639 | 0.674 | 0.609 |
| T38 | ndrangheta in Calabria | 33 | 0.572 | 0.333 | 0.593 | 0.584 | 0.585 | 0.567 | 0.351 | 0.593 | 0.554 | 0.479 |
| T39 | papa Giovanni Paolo II | 12 | 0.701 | 0.610 | 0.762 | 0.769 | 0.752 | 0.653 | 0.762 | 0.762 | 0.716 | 0.588 |
| T40 | papa Benedetto XVI Ratzinger | 90 | 0.735 | 0.764 | 0.758 | 0.747 | 0.751 | 0.754 | 0.767 | 0.758 | 0.763 | 0.764 |
| T41 | papa Francesco Bergoglio | 14 | 0.763 | 0.815 | 0.786 | 0.713 | 0.785 | 0.780 | 0.802 | 0.786 | 0.701 | 0.795 |
| T42 | incisioni rupestri della Val Camonica | 21 | 0.582 | 0.371 | 0.536 | 0.549 | 0.485 | 0.514 | 0.441 | 0.536 | 0.461 | 0.391 |
| T43 | metropolitana di Roma | 17 | 0.461 | 0.469 | 0.453 | 0.464 | 0.518 | 0.396 | 0.479 | 0.453 | 0.399 | 0.468 |
| T44 | gran premio di Formula 1 | 60 | 0.577 | 0.439 | 0.574 | 0.566 | 0.559 | 0.600 | 0.439 | 0.565 | 0.596 | 0.554 |
| T45 | MotoGP motomondiale | 17 | 0.560 | 0.118 | 0.617 | 0.642 | 0.631 | 0.599 | 0.294 | 0.617 | 0.621 | 0.617 |
| T46 | tappa del Giro d'Italia | 93 | 0.989 | 0.998 | 0.985 | 0.975 | 0.993 | 0.971 | 0.985 | 0.985 | 0.992 | 0.950 |
| T47 | disastro aereo | 69 | 0.388 | 0.180 | 0.529 | 0.539 | 0.449 | 0.522 | 0.200 | 0.529 | 0.546 | 0.525 |
| T48 | violenza contro le donne | 24 | 0.146 | 0.125 | 0.137 | 0.153 | 0.144 | 0.148 | 0.125 | 0.137 | 0.154 | 0.106 |
| T49 | diritti gay e omofobia | 39 | 0.398 | 0.196 | 0.492 | 0.503 | 0.446 | 0.427 | 0.312 | 0.492 | 0.460 | 0.428 |
| T50 | proteste in Tibet | 12 | 0.681 | 0.201 | 0.695 | 0.833 | 0.785 | 0.732 | 0.229 | 0.695 | 0.770 | 0.598 |
