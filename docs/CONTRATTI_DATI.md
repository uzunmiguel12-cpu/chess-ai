# Contratti dati

Questo documento definisce il formato unico con cui tutti i moduli (`engine`,
`ml`, `rag`, `api`, `frontend`) si scambiano dati. È un accordo: chiunque
produca o legga dati nel progetto rispetta queste forme.

Principio guida: i contratti sono la versione serializzata (in JSON) degli
oggetti di python-chess. Ogni modulo converte in oggetti python-chess solo
internamente, ai propri bordi. Se un domani cambia la libreria, si toccano
solo i convertitori, non i contratti.

Glossario rapido:
- FEN: stringa che descrive esattamente una posizione sulla scacchiera.
- UCI: notazione di una mossa come la usa Stockfish, es. `e2e4`.
- SAN: notazione leggibile di una mossa, es. `Nf3`. Dipende dalla posizione.
- Centipawn (cp): unità di vantaggio. 100 cp = un pedone.

---

## Contratto 1 — Posizione

Descrive una posizione sulla scacchiera. La chiave è la FEN: da sola contiene
già lato al tratto, diritti di arrocco e numero di mossa, quindi gli altri
campi sono ricavabili e opzionali.

Campi:
- `fen` (stringa, obbligatorio) — prodotta da `board.fen()`.

Origine python-chess: `chess.Board`.

---

## Contratto 2 — Mossa

Descrive una singola mossa giocata, sempre legata alla posizione in cui è
avvenuta (serve per calcolare la notazione leggibile).

Campi:
- `uci` (stringa, obbligatorio) — la mossa in notazione UCI, da `move.uci()`.
- `san` (stringa, obbligatorio) — la stessa mossa leggibile, da `board.san(move)`.
- `fen_before` (stringa, obbligatorio) — la posizione prima della mossa.

Origine python-chess: `chess.Move` + la `Board` di contesto.

---

## Contratto 3 — Analisi

È il contratto più importante: viene riempito progressivamente dai vari moduli.
`engine` riempie i campi del motore; `ml` aggiunge la categoria; `rag` aggiunge
la spiegazione. I campi non ancora prodotti restano `null`.

Campi:
- `fen` (stringa) — posizione a cui si riferisce l'analisi.
- `move_uci` (stringa) — mossa giocata, in UCI.
- `eval_cp` (numero) — valutazione Stockfish in centipawn. [riempito da engine, Fase 2]
- `best_move_uci` (stringa) — mossa migliore secondo il motore. [engine, Fase 2]
- `centipawn_loss` (numero) — perdita rispetto alla mossa migliore. [engine, Fase 2]
- `category` (stringa o null) — tipo di errore. [riempito da ml, Fase 3]
- `explanation` (stringa o null) — spiegazione didattica. [riempito da rag, Fase 4]

Flusso di riempimento:
```
engine  →  eval_cp, best_move_uci, centipawn_loss
ml      →  category
rag     →  explanation
```

---

## Nota sulle categorie di errore

Il campo `category` del contratto Analisi avrà un insieme definito di valori
possibili (es: errore_tattico, errore_posizionale, errore_apertura,
errore_finale, tattica_persa). L'elenco preciso verrà fissato nella Fase 3,
quando si progetta il layer ML. Per ora il campo esiste nel contratto ma
resta `null`.
