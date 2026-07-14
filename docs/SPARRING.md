# Sparring — bot a livelli + coach posizionale realtime

Sezione `/sparring` (nav: tra Aperture e Principi). Giochi contro Stockfish a
livelli; dopo ogni tua mossa il coach dice se la mossa è ok / teoria / errore
tattico / errore posizionale, e per gli errori posizionali spiega *quali*
elementi sono peggiorati. Decisioni prese da Miguel (sessione luglio 2026):
nome "Sparring", livelli via Skill Level, analisi dopo ogni mossa, training
su `data/analisi/`.

## Componenti

| File | Ruolo |
|---|---|
| `ml/caratteristiche_posizionali.py` | ~20 feature posizionali da una Board (solo lettura, niente engine) |
| `ml/dataset_posizionale.py` | dataset da `data/analisi/` (riusa i cp_loss a prof. 15; NO engine). Riprendibile a blocchi |
| `ml/allena_posizionale.py` | allena regressore (perdita cp) + classificatore di rischio → `data/modello_posizionale.joblib` |
| `api/sparring.py` | router FastAPI: `/sparring/livelli`, `/sparring/mossa`, `/sparring/mossa-bot` (incluso da `server.py`) |
| `frontend/src/pages/Sparring.jsx` + `.css` | scacchiera + pannello coach; route e voce nav aggiunte |

## Numeri onesti [DATO] (dataset: 101.173 mosse non tattiche, 3.337 partite, split per partita)

- Regressore cp_loss: MAE 45.4 vs baseline 47.7 → il posizionale resta poco
  predicibile dalle sole feature, coerente con l'esito T3 di `ml/analizza_posizionale.py`.
- Classificatore rischio (errore ≥100cp): AUC 0.667; il decile più a rischio
  sbaglia il doppio della media (35% vs 18%).

**Conseguenza di design**: nel pannello la diagnosi primaria è deterministica
(cp_loss engine + feature peggiorate = [DATO]); il modello ML compare solo come
"rischio stimato … [stima]". Se in futuro il segnale non basta, il pannello
funziona anche senza modello (il backend lo carica in modo opzionale).

## Classificazione della mossa (in `api/sparring.py`)

1. prime 5 mosse → `teoria` (nessuna diagnosi, come SALTA_APERTURA del training),
   MA un blunder ≥300cp viene comunque segnalato;
2. cp_loss ≥300, o ≥50 con confutazione forzante (catture/scacchi nella PV,
   swing materiale) → `tattico` (la spiega già Stockfish / allenamento puzzle);
3. cp_loss ≥50 altrimenti → `posizionale`, con le 3 feature più peggiorate;
4. sotto 50 → `ok`.

## Avvio e retraining

```cmd
:: backend (da api/, ambiente attivo) — stockfish.exe già in engine/bin
uvicorn server:app --reload

:: retraining del modello (da ml/)
python dataset_posizionale.py --reset   & :: ricostruisce il CSV da data/analisi
python allena_posizionale.py            & :: MAE/AUC aggiornati + joblib
```

Nuove dipendenze in requirements.txt: scikit-learn, joblib, pandas.
Env `STOCKFISH_PATH` per usare un binario diverso da `engine/bin/stockfish.exe`.

## Roadmap del modello (decisa da Miguel — dettagli in docs/DA_FARE.md, sezione
## "Roadmap modello posizionale"): S1 arricchire le feature → S2 dataset Lichess
## per volume (PGN con [%eval]) → S3 rete neurale 8x8x12 con spiegazioni
## deterministiche. Ordine vincolante.

## Aperto / prossimi passi possibili

- Profondità analisi realtime: 12 (compromesso latenza ~1s). Alzabile.
- Le spiegazioni possono uscire vuote (peggioramento non catturato dalle 20
  feature): il frontend mostra un testo generico. Candidate nuove feature:
  case deboli, pedoni sospesi, blocco dei passati.
- Collegare gli errori posizionali dello Sparring alla coda errori (`data/coda_errori.json`).
- Report di fine partita (riepilogo errori già mostrato nel pannello, non persistito).
