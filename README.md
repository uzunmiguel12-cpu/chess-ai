# chess-ai

Sistema scacchistico AI per **analisi post-partita e coaching**: non gioca al
posto tuo (lo fa già Stockfish), ma spiega gli errori, riconosce i pattern
ricorrenti del giocatore e insegna seguendo schemi.

## Visione

Trasformare la valutazione numerica di un motore scacchistico in spiegazioni
didattiche comprensibili, identificare gli errori tipici di un giocatore nel
tempo, e proporre temi su cui allenarsi.

## Architettura (quattro strati)

```
1 · Strato dati        →  PGN, parsing, database posizioni
2 · Strato motore      →  Stockfish: verità tattica, centipawn loss
3 · Strato ML          →  classificazione errori in concetti umani
4 · Strato RAG + LLM   →  recupero conoscenza, spiegazione didattica
```

Ogni strato produce l'input del successivo. Il valore del progetto sta negli
strati 3 e 4, dove la valutazione grezza diventa insegnamento.

## Struttura del monorepo

| Cartella    | Responsabilità                                    |
|-------------|---------------------------------------------------|
| `frontend/` | Interfaccia React (scacchiera, analisi, coaching) |
| `engine/`   | Wrapper Stockfish via UCI, centipawn loss         |
| `ml/`       | Classificazione errori e pattern                  |
| `rag/`      | Knowledge base, retrieval, generazione spiegazioni|
| `api/`      | Orchestrazione della pipeline                     |

## Librerie chiave

- [python-chess](https://github.com/niklasf/python-chess) — PGN, mosse legali, protocollo UCI
- [Stockfish](https://github.com/official-stockfish/Stockfish) — motore di analisi
- RAG (Fase 4): LlamaIndex o LangChain + vector store (pgvector / Qdrant / Chroma)

## Stato

In sviluppo — Fase 0 (fondamenta). Vedi la roadmap completa per il dettaglio
delle fasi e delle decisioni ancora aperte (backend hosting, provider LLM).

## Setup

_Da completare nella task 0.9._
