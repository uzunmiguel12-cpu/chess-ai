# chess-ai — Cose da fare e da implementare

> Stato del progetto: **Fase 4 completata** (sistema personale completo e funzionante).
> Questo documento elenca ciò che manca ancora, diviso per priorità.
> Aggiornato al termine della sessione in cui è stata aggiunta la persistenza tra sessioni.

---

## Dove siamo arrivati (per contesto)

Il sistema **personale** è completo e funzionante end-to-end:
- Analisi delle partite (tutte le cadenze) con Stockfish a profondità 15.
- Profilo di debolezze (fase + motivi tattici), con misure oneste (tasso, non conteggio).
- Piano di allenamento automatico dalle debolezze, ordinato per frequenza.
- Database puzzle Lichess (6.014.381 puzzle) interrogabile per tema ed Elo.
- Scacchiera giocabile nel browser (Vite + chess.js + chessground).
- Difficoltà adattiva (regola dell'85%, fascia Elo che cresce/cala ogni 10 puzzle).
- Statistiche di sessione (successo al primo colpo).
- Nessuna ripetizione di puzzle (tracciamento dei visti + pesca casuale su sottoinsieme).
- 8 pulsanti-tema per allenamento focalizzato (con adattività attiva).
- Avanzamento automatico dopo un successo (800ms), pausa sugli errori.
- Query ottimizzata (sottoinsieme 5000 candidati → veloce + vario).
- Persistenza tra sessioni (fascia, visti, statistiche salvati su `data/stato_sessione.json`).

---

## PRIORITÀ ALTA — robustezza e completezza del sistema personale

### 1. Test automatici per i moduli `rag` e `api` ✅ FATTO
- ~~`costruisci_db.py`, `decomprimi_puzzle.py`, `raccomanda.py` e `api/server.py` **non hanno ancora test**.~~
- Aggiunti `rag/test_raccomanda.py` (10), `rag/test_costruisci_db.py` (5),
  `rag/test_decomprimi_puzzle.py` (3) e `api/test_server.py` (12) — 30 nuovi test, tutti verdi.
- I test usano database/CSV/file-zst finti temporanei (come già fatto per piano); il backend
  è testato chiamando direttamente le funzioni degli endpoint (niente httpx) con `_sessione`
  azzerata e percorsi reindirizzati via monkeypatch.
- Restano fuori dai test (di proposito): `_prepara_sessione` end-to-end (richiede un profilo
  reale nella cartella categorie di default) e il vero `puzzle.db`.

### 2. Gestione dell'esaurimento dei puzzle ✅ FATTO
- ~~Limite noto: se si gioca tantissimo nella stessa combinazione tema+fascia, il bacino può esaurirsi (mai ripetizioni, ma meno puzzle disponibili).~~
- Quando un blocco/tema ha meno di 5 puzzle nuovi nella fascia Elo corrente (esclusi i visti),
  il backend alza **solo temporaneamente** il tetto della fascia di +100 alla volta e ripesca,
  fino a +400 sopra il tetto di base o al tetto assoluto 2800.
- Regola di non-interferenza con l'adattività: l'allargamento è una fascia **"effettiva"**
  locale per la singola pesca (`_pesca_allargando` in `api/server.py`); la fascia di base
  (`elo_min`/`elo_max`) in sessione **non viene mai toccata**. L'adattività resta l'unica
  padrona della fascia di base e, ricalibrando ogni 10 puzzle, riparte sempre da quella vera.
- Se anche col tetto massimo i puzzle nuovi restano insufficienti, il sistema **non si blocca**:
  segnala `esaurito` con un `suggerimento` di cambiare tema nelle risposte di
  `/scegli-tema` e `/prossimo-puzzle`.
- Testato in `api/test_server.py` con DB temporanei a pochi puzzle (8 nuovi test).

### 3. Verifica server-side finale delle soluzioni (sicurezza)
- Attualmente la verifica delle mosse è solo nel browser (scelta giusta per reattività).
- In ottica multi-utente servirà una verifica finale lato server (per evitare imbrogli), da fare solo a puzzle completato per non rallentare ogni mossa.

---

## PRIORITÀ MEDIA — esperienza e rifinitura

### 4. Pulizia residui e dettagli — favicon ✅ FATTO
- ~~Far sparire il **404 della favicon** (aggiungere un'iconcina).~~ Aggiunta una
  favicon a tema scacchi (`frontend/public/favicon.svg`, un cavallo su sfondo a
  scacchiera) e referenziata in `frontend/index.html` con `<link rel="icon">`.
- (Resta, minore) Rimuovere gli eventuali `.svg` di esempio in `frontend/src/assets`
  (residui Vite, innocui).

### 5. Cronologia e progressi nel tempo ✅ FATTO
- ~~Mostrare un **grafico dei progressi** (fascia Elo nel tempo, % di successo per tema).~~
- Aggiunta una sezione "I miei progressi" nel frontend (pulsante 📊), con due grafici
  **Chart.js**: (a) fascia Elo nel tempo, ricostruita da `storico_fasce`; (b) percentuale
  di successo al primo colpo per tema, dalle statistiche-per-tema (punto 7).
- Backend: nuovo endpoint `/storico-fasce` (storico + fascia attuale) per il grafico (a).
- I grafici si aggiornano all'apertura della sezione e dopo ogni esito (se aperta).

### 6. Tassonomia temi più ricca ✅ FATTO
- ~~Ora ci sono 8 temi nei pulsanti.~~ Ampliati a **24 temi**, raggruppati in 3 categorie
  (**Tattiche** 11, **Matti** 6, **Finali** 7) in `TEMI_CATEGORIE` (`api/server.py`).
- L'endpoint `/temi` ora restituisce sia la lista piatta (compatibilità) sia il
  raggruppamento per categoria; il frontend mostra i pulsanti divisi per categoria.
- I 4 temi del profilo automatico restano: pezzo_in_presa, forchetta, inchiodatura, infilata.

### 7. Statistiche per tema ✅ FATTO
- ~~Sapere in quali temi si va meglio/peggio (non solo la % globale).~~
- Il backend traccia per ogni tema affrontato i puzzle **tentati** e quelli **risolti al
  primo colpo**, con percentuale. Dati **persistiti** in `data/stato_sessione.json`
  (sopravvivono ai riavvii) ed esposti dall'endpoint `/statistiche-temi`.
- Il tema di ogni esito è dedotto dal `motivo_allenamento` del puzzle in coda.
- Non-interferenza con l'adattività: sono **solo conteggi**, non toccano fascia/blocco.
- Testato in `api/test_server.py` (tracciamento, percentuale, persistenza, non-interferenza).

---

## PRIORITÀ FUTURA — Fase 5: il servizio multi-utente

Questo è il **grande salto** verso la visione originale. Richiede competenze e
infrastruttura nuove. Da affrontare solo quando la versione personale soddisfa pienamente.

### Componenti necessari
- **Sistema di account**: registrazione, login, password (con sicurezza adeguata).
- **Database utenti**: ogni utente con i propri dati isolati (partite, profilo, stato, visti).
- **Server sempre acceso**: hosting (non il portatile), con costi mensili e manutenzione.
- **Caricamento partite per utente**: ognuno carica le proprie e vanno analizzate (Stockfish è lento: ~3,5h per ~3000 partite — chi/come fa il calcolo?).
- **Migrazione da file JSON a database** per lo stato (ora `stato_sessione.json` è single-user).
- **Interfaccia web pubblica** rifinita.

### Nodi aperti da decidere per la Fase 5
- Dove gira l'analisi Stockfish (server? coda di lavori? limiti per utente?).
- Licenza **chessground è GPL-3.0**: usarla in un servizio pubblico obbligherebbe a rendere pubblico il codice. Da valutare consapevolmente (o cercare alternative).
- Costi di hosting e modello (gratuito? freemium? il vecchio interesse per startup/MindDesk potrebbe ispirare il modello di business).

---

## Note tecniche utili (promemoria)

- Progetto: `C:\Users\migue\Desktop\chess-ai` (Desktop, NON OneDrive).
- Avvio sviluppo: servono **due server** — backend (`uvicorn server:app --reload` in `api/`, porta 8000) e frontend (`npm run dev` in `frontend/`, porta 5173).
- Cartelle: `engine/` (Stockfish/parser), `ml/` (categorizzazione/profilo/tattica), `rag/` (DB puzzle/raccomandazione/piano), `api/` (server), `frontend/` (scacchiera).
- `data/` è ignorata da Git (contiene `puzzle.db`, le partite, le analisi, lo stato) — non finisce su GitHub.
- Per azzerare tutto e ripartire da capo: cancellare `data\stato_sessione.json`.
- Stockfish (`engine/bin/stockfish.exe`) e `node_modules` sono esclusi da Git.
- Elo di riferimento attuale: rapid ~1043; fascia puzzle di partenza 1050-1250 (poi adattiva).
