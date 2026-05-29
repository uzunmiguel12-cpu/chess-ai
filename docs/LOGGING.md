# Convenzione di logging ed errori

Questo documento fissa come tutti i moduli Python del progetto (`engine`,
`ml`, `rag`, `api`) scrivono i loro messaggi. L'obiettivo è che il programma
racconti cosa fa mentre lo fa, così quando qualcosa va storto si capisce dove
e perché.

Non serve installare niente: Python ha il modulo `logging` integrato.

## Livelli da usare

- `INFO` — flusso normale: inizio/fine di un'operazione, conteggi, progressi.
  Esempi: "Avvio analisi partita", "Analizzate 50 posizioni".
- `WARNING` — situazione insolita ma gestibile, il programma prosegue.
  Esempi: "Partita senza tag Date, proseguo", "FEN sospetta ma valida".
- `ERROR` — qualcosa è andato male e va gestito.
  Esempi: "Impossibile contattare Stockfish", "File PGN illeggibile".

Regola pratica: se il programma può andare avanti è al massimo WARNING; se
un'operazione fallisce è ERROR.

## Come configurare (una volta per modulo)

Ogni modulo, all'avvio, configura il logging con lo stesso formato condiviso.
Vedere il file di esempio `logging_example.py` in questa cartella: contiene la
configurazione standard da copiare.

Formato dei messaggi (uguale per tutti):
```
2025-05-30 14:23:01 | INFO | engine | Avvio analisi partita
```
cioè: data e ora | livello | nome del modulo | messaggio.

## Gestione errori — convenzione minima

- Non far fallire un intero batch per un singolo elemento problematico:
  loggare l'errore a livello ERROR e proseguire con l'elemento successivo,
  quando ha senso (es. una partita malformata su mille).
- Quando un errore impedisce di proseguire del tutto, loggarlo e interrompere
  con un messaggio chiaro, non con un crash silenzioso.

Questa è la versione minima della convenzione. Verrà ampliata quando i moduli
avranno codice vero (gestione delle eccezioni specifiche, log su file, ecc.).
