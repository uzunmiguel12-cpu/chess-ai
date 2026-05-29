# Stack tecnologico e decisioni

Questo documento registra le scelte tecnologiche del progetto: quelle già
prese e quelle rimandate di proposito. Scrivere le decisioni aperte è
importante quanto scrivere quelle chiuse — segnala che sono scelte
consapevoli, non dimenticanze.

Ultimo aggiornamento: Fase 0.

---

## Decisioni prese

### Backend — linguaggio: Python
Motivo: l'intero ecosistema ML e RAG che servirà nelle Fasi 3 e 4 è maturo in
Python. La libreria scacchistica di riferimento (python-chess) è Python.

### Frontend: React
Motivo: già avviato. Il componente principale della scacchiera esiste già.

### Libreria scacchistica: python-chess
Motivo: copre parsing PGN, generazione e validazione mosse, e comunicazione
con il motore via protocollo UCI. È lo standard de facto dell'ecosistema.
Repo: https://github.com/niklasf/python-chess

### Motore di analisi: Stockfish
Motivo: motore open source più forte e diffuso. python-chess ci comunica
nativamente via UCI.
Repo: https://github.com/official-stockfish/Stockfish

---

## Decisioni rimandate (da prendere)

### Dove gira il backend — DA DECIDERE
Opzioni: locale / server con GPU / cloud.
Diventa bloccante in: Fase 2 (Stockfish a profondità seria non gira bene nel
browser; serve quasi certamente un backend).
Stato: rimandata consapevolmente.

### Database — DA DECIDERE
Opzioni: PostgreSQL (con estensione pgvector per il RAG) / SQLite per iniziare.
Diventa rilevante in: Fase 1 (storage delle partite e posizioni).
Stato: rimandata.

### Provider LLM — DA DECIDERE
Opzioni: API esterna (più semplice) / modello locale (privacy, costo GPU).
Diventa rilevante in: Fase 4 (generazione delle spiegazioni).
Stato: rimandata.

### Framework RAG — DA DECIDERE
Opzioni: LlamaIndex (orientato a indicizzazione/retrieval, più semplice) /
LangChain (orientato ad agenti e flussi complessi).
Diventa rilevante in: Fase 4.
Stato: rimandata.

### Vector store — DA DECIDERE
Opzioni: pgvector (se si usa PostgreSQL) / Qdrant / Chroma.
Diventa rilevante in: Fase 4.
Stato: rimandata.

---

## Note

Le decisioni rimandate non bloccano la Fase 0. Vanno prese nell'ordine in cui
diventano bloccanti, seguendo la roadmap. Aggiornare questo file ogni volta
che una decisione passa da "rimandata" a "presa".
