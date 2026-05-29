# Roadmap — Sistema scacchistico AI (analisi, coaching, knowledge)

> Obiettivo del sistema: **non** giocare forte (lo fa già Stockfish), ma
> spiegare gli errori del giocatore, riconoscere pattern ricorrenti, e
> insegnare seguendo schemi. Architettura: Stockfish come oracolo tattico +
> layer ML per classificare + RAG/LLM per spiegare.

---

## Decisioni da prendere subito (bloccano le fasi successive)

| Decisione | Quando diventa bloccante | Implicazione |
|---|---|---|
| Dove gira Stockfish | Fase 2 | Browser = profondità bassa, debole. Server/cloud = profondità seria. |
| Sorgente delle partite | Fase 1 | Lichess open DB (gratis, enorme) vs. solo partite dell'utente. |
| Provider LLM | Fase 4 | API esterna (più semplice) vs. modello locale (privacy, costo GPU). |
| Storage embedding | Fase 4 | Vector DB dedicato (pgvector, Qdrant) vs. in-memory. |

Regola pratica: per un sistema didattico serio serve un **backend**. Il browser
da solo non regge Stockfish a profondità + embedding RAG. Conviene decidere
"backend con GPU/cloud" prima di iniziare la Fase 2.

---

## Fase 0 — Fondamenta (1–2 settimane)

Prerequisito di tutto. Mette in piedi il monorepo e le interfacce tra i moduli.

- [ ] Struttura monorepo: `frontend/`, `engine/`, `ml/`, `rag/`, `api/`
- [ ] Definire i contratti dati tra i moduli (schema JSON per posizione, mossa, analisi)
- [ ] Scegliere il linguaggio del backend (Python consigliato: ecosistema ML/RAG maturo)
- [ ] Setup ambiente: gestione dipendenze, env vars, logging
- [ ] CI minima: lint + test su ogni commit

Output: scheletro che compila, moduli vuoti con interfacce definite.

> Stato Fase 0: completate 0.1–0.6 e 0.9. Le task 0.7 (framework di test) e
> 0.8 (CI minima) sono rimandate consapevolmente all'inizio della Fase 1,
> quando ci sara' codice vero da testare e sorvegliare. Farle prima
> significherebbe testare e controllare il vuoto.

### Task 0.4 (dettaglio) — Contratti dati basati su python-chess

Non reinventare la rappresentazione di posizioni e mosse: usare gli oggetti
`Board`, `Move`, `Game` di python-chess come vocabolario condiviso. I contratti
JSON sono la versione serializzata di quegli oggetti. Ogni modulo converte
verso/da python-chess solo internamente, ai bordi.

Contratto **Posizione**:
- `fen` (chiave primaria) — prodotta da `board.fen()`, riassorbita da `chess.Board(fen)`
- metadati (numero mossa, lato al tratto, diritti arrocco) opzionali, ricavabili dalla FEN

Contratto **Mossa**:
- `uci` — notazione UCI da `move.uci()` (es. `e2e4`), stesso formato di Stockfish
- `san` — notazione leggibile da `board.san(move)` (richiede una posizione di riferimento)
- `fen_before` — posizione in cui la mossa è stata giocata (necessaria per calcolare la SAN)

Contratto **Analisi** (riempito progressivamente engine → ml → rag):
- `fen`, `move_uci` — a quale mossa si riferisce
- `eval_cp` — valutazione Stockfish in centipawn (Fase 2)
- `best_move_uci` — mossa migliore secondo il motore (Fase 2)
- `centipawn_loss` — perdita rispetto alla mossa migliore (Fase 2)
- `category` — categoria errore, `null` finché non arriva la Fase 3 (ML)
- `explanation` — spiegazione didattica, `null` finché non arriva la Fase 4 (RAG)

Principio: i moduli si scambiano JSON conforme a questi contratti. Se in futuro
cambia la libreria, si toccano solo i convertitori ai bordi, non i contratti.

---

## Fase 1 — Strato dati (1–2 settimane)

Dipende da: Fase 0.

- [ ] Parser PGN robusto (gestire commenti, varianti, NAG, header malformati)
- [ ] Importazione da Lichess open database (o upload PGN utente)
- [ ] Schema database: partite, posizioni (FEN), mosse, metadati giocatore
- [ ] Deduplicazione posizioni (la stessa posizione ricorre in molte partite)
- [ ] Indici per query veloci (per giocatore, per apertura, per fase di gioco)

Output: database popolato e interrogabile di partite e posizioni.

---

## Fase 2 — Strato motore Stockfish (2–3 settimane)

Dipende da: Fase 1. **Punto di decisione "dove gira il sistema".**

- [ ] Integrare Stockfish via UCI (binario nativo lato server, NON wasm in browser per l'analisi seria)
- [ ] Wrapper che data una FEN restituisce: valutazione, mossa migliore, PV (linea principale)
- [ ] Calcolo del **centipawn loss** per ogni mossa giocata (differenza tra mossa migliore e mossa giocata)
- [ ] Classificazione grezza per soglia: inaccuracy / mistake / blunder (basata su cp loss)
- [ ] Pipeline batch: analizzare un'intera partita e salvare i risultati
- [ ] Caching: non rianalizzare posizioni già viste (collega alla dedup di Fase 1)
- [ ] Gestione profondità/tempo configurabile (trade-off velocità vs. accuratezza)

Output: ogni mossa di ogni partita ha valutazione e centipawn loss salvati.
Questo è il **dataset etichettato** che alimenta la Fase 3.

---

## Fase 3 — Strato ML, classificazione concettuale (3–5 settimane)

Dipende da: Fase 2 (servono i dati etichettati). È il cuore del valore aggiunto.

Stockfish ti dice *quanto* una mossa è cattiva (centipawn). L'ML deve dire
*perché* e *che tipo* di errore è, in termini umani.

- [ ] Feature engineering dalla posizione: materiale, struttura pedonale, sicurezza del re, attività dei pezzi, controllo del centro, fase di gioco
- [ ] Etichettatura dei temi: definire le categorie (errore tattico, errore posizionale, errore di apertura, errore in finale, occasione tattica persa, ecc.)
- [ ] Dataset di training: usare i tag PGN/Lichess esistenti come label deboli + euristiche da Stockfish (es. se cp loss alto E c'era una forchetta disponibile → "tattica persa")
- [ ] Modello classificatore (partire semplice: gradient boosting sulle feature; poi eventualmente rete neurale sulla rappresentazione della scacchiera)
- [ ] Rilevamento pattern ricorrenti per giocatore: clustering degli errori (es. "sbaglia spesso nei finali di torre", "perde pezzi per pin non visti")
- [ ] Validazione: confronto con annotazioni umane su un set di test
- [ ] Metriche: accuratezza classificazione, copertura dei temi

Output: data una mossa cattiva, il sistema produce una **categoria** e
identifica i **pattern ricorrenti** del giocatore.

---

## Fase 4 — Strato RAG + LLM, generazione spiegazioni (3–4 settimane)

Dipende da: Fase 3 (servono le categorie da cui partire). **Decisioni: provider LLM, vector DB.**

- [ ] Costruire la knowledge base scacchistica: principi, motivi tattici, piani tipici per struttura, finali teorici. Fonti: libri liberi da diritti, articoli, glossari, le proprie note
- [ ] Chunking e embedding della knowledge base in un vector DB
- [ ] Retrieval: data la categoria di errore + posizione, recuperare i concetti pertinenti
- [ ] Prompt engineering: dare all'LLM la posizione, la valutazione Stockfish, la categoria ML, e i chunk recuperati → generare spiegazione didattica
- [ ] Guardrail: l'LLM NON deve inventare valutazioni; la verità tattica viene sempre da Stockfish, l'LLM solo spiega
- [ ] Generazione di esercizi correlati ("ecco 3 posizioni simili dove allenare questo tema")
- [ ] Valutazione qualità spiegazioni (review umana, fedeltà ai dati del motore)

Output: spiegazione in linguaggio naturale di ogni errore, con principi e
suggerimenti, ancorata ai dati reali di Stockfish.

---

## Fase 5 — Integrazione e UX coaching (2–3 settimane)

Dipende da: Fasi 3 e 4.

- [ ] Endpoint API che collega tutta la pipeline (partita → analisi completa)
- [ ] Vista analisi post-partita nel frontend (collegata alla scacchiera già costruita)
- [ ] Report del giocatore: pattern ricorrenti, progressi nel tempo, temi da allenare
- [ ] Coda asincrona per l'analisi (l'analisi profonda richiede tempo)
- [ ] Caching dei risultati per partita

Output: il giocatore carica/gioca una partita e riceve coaching completo.

---

## Riepilogo dipendenze

```
Fase 0  →  Fase 1  →  Fase 2  →  Fase 3  →  Fase 4  →  Fase 5
(setup)   (dati)    (motore)   (ML)       (RAG/LLM)  (UX)
                       ↑                      ↑
              decisione "dove gira"   decisione "LLM + vector DB"
```

L'ordine è quasi obbligato: ogni fase produce l'input della successiva.
L'unica parallelizzazione utile è iniziare a raccogliere/costruire la
knowledge base (parte di Fase 4) durante le Fasi 2–3.

---

## Stima totale

Indicativamente 12–19 settimane per una persona a tempo pieno, esclusi
imprevisti e raccolta dati. Le fasi più rischiose e lunghe sono la 3 (ML)
e la 4 (RAG), dove sta il vero valore del sistema.
