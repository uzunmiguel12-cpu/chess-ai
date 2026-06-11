# chess-ai — Cose da fare e da implementare

> Stato del progetto: **Fase 4 completata + punti 1, 6 e 2 della visione estesa** (sistema
> personale completo; flussi separati; flusso `errori` popolato; report carenze + piano di
> studio + confronto progressi anti-diluizione).
> Questo documento elenca ciò che manca ancora, diviso per priorità.
> Aggiornato al termine della sessione in cui è stato implementato il punto 2 della visione
> (report carenze, piano di studio a pesi relativi, snapshot nel tempo anti-diluizione).

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
- 3 tentativi per puzzle (margine didattico); il "successo" resta SOLO il primo colpo.
- Snapshot periodici dei progressi (ogni 10 puzzle) con grafico % al primo colpo nel
  tempo, indicatore di tendenza "stai migliorando?" e tabella riassuntiva.
- **Flussi separati** (punto 1 della visione estesa): `piano` / `temi` / `errori`, ciascuno
  con coda, fascia Elo adattiva e statistiche proprie; visti globali; persistenza a tre
  stati con migrazione dal vecchio file; selettore di flusso nel frontend.
- **Flusso `errori` implementato** (punto 6 della visione estesa): puzzle dai propri errori
  veri, validati con Stockfish (gap ≥200, prof. 18), in sequenze forzate multi-mossa, con
  rinforzo Lichess marcato a esaurimento. 1027 puzzle in `data/coda_errori_estesa.json`.
  Vedi 5d più sotto.

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

#### 5b. Metriche e grafici di progresso nel tempo ✅ FATTO
- **Snapshot periodici**: ogni 10 puzzle tentati il backend salva uno snapshot
  `{timestamp, tentati, percentuale_primo_colpo, fascia_elo: [min, max]}` nella lista
  `snapshot_progresso`, **persistita** in `data/stato_sessione.json` e ricaricata all'avvio.
  Lo snapshot è preso **dopo** l'eventuale ricalibro adattivo, così fotografa la fascia
  aggiornata. È **solo lettura/conteggio**: non influenza mai la fascia adattiva.
- **Grafico 1 — "% di successo al primo colpo nel tempo"**: linea costruita dagli snapshot
  (asse X = puzzle tentati). In interfaccia una nota spiega che la percentuale tende
  all'**85%** per via della difficoltà adattiva.
- **Indicatore 2 — "stai migliorando?"**: `_calcola_tendenza` confronta il punto medio della
  fascia Elo tra il primo e l'ultimo degli ultimi 5 snapshot e mostra ↑ "In crescita",
  → "Stabile" o ↓ "In calo". È l'indicatore onesto di miglioramento.
- **Tabella riassuntiva** (`_riepilogo_progressi`): puzzle totali tentati, % al primo colpo
  storica, fascia Elo iniziale (la prima registrata) vs attuale con il guadagno (+N punti),
  tema migliore e peggiore dalle statistiche-per-tema.
- Backend: nuovo endpoint `/progressi` (snapshot + tendenza + riepilogo). Testato in
  `api/test_server.py` (snapshot, persistenza, non-interferenza, tendenza, riepilogo, endpoint).
- **Tentativi 2 → 3**: il frontend ora concede 3 tentativi prima di mostrare la soluzione,
  ma il "successo" per adattività e statistiche resta **solo il primo colpo** (l'esito è
  `primo` unicamente se `tentativi == 0`; 2°/3° tentativo = `secondo`, margine didattico).

#### 5c. Separazione dei flussi (punto 1 della visione estesa) ✅ FATTO
- Le due modalità (piano automatico / temi liberi) non condividono più coda, fascia e
  statistiche: ora ci sono **tre flussi indipendenti** — `piano`, `temi`, `errori` —
  predisposti fin da subito (il flusso `errori` è solo predisposto: verrà col **punto 6**).
- Ogni flusso ha la PROPRIA coda, la PROPRIA fascia Elo adattiva (regola dell'85%
  indipendente) e le PROPRIE statistiche (tentati, % al primo, snapshot storici,
  statistiche-per-tema, storico fasce). I **visti** sono invece **globali** tra i flussi
  (scelta progettuale: non rivedere lo stesso puzzle cambiando flusso).
- Persistenza **v2**: `data/stato_sessione.json` salva i tre flussi separatamente +
  `flusso_attivo` + `visti` globali. **Retrocompatibile**: il vecchio file a stato singolo
  viene migrato nel flusso `piano` senza crashare. Aggiunto un **riepilogo complessivo**
  (totale puzzle sommando i flussi); le statistiche principali restano per-flusso.
- Endpoint: `GET /flussi`, `POST /flusso/{nome}` (con `errori` → 501); gli endpoint di
  lettura si riferiscono al flusso attivo. Frontend: selettore di flusso, con statistiche e
  grafici riferiti al flusso attivo. Dettagli in `docs/VISIONE_ESTESA.md` (punto 1).
- Testato in `api/test_server.py`: indipendenza fasce tra flussi, persistenza dei tre
  stati, retrocompatibilità col vecchio file, visti globali, riepilogo complessivo.

#### 5d. Punto 6 della visione — Puzzle dai propri errori ✅ FATTO
> (Questo è il **punto 6 della visione estesa**, da non confondere con il "punto 6" interno
> di questo documento qui sotto, che è la tassonomia temi.)
- Il flusso `errori` (prima solo predisposto → 501) è ora **implementato e popolato**.
- **Pipeline** (nessuna rianalisi delle partite: si parte dalle analisi già in
  `data/analisi/`):
  1. `ml/estrai_errori.py` — estrae le mie mosse sbagliate (colore + turno dal FEN), filtro
     di sanità (±700cp), conta per soglia; **bullet escluso**. → 4604 candidati non-bullet ≥200.
  2. `ml/valida_errori.py` — valida l'unicità con Stockfish MultiPV (gap ≥200, prof. 18),
     `--campione`/`--batch`. → **1027 puzzle** tenuti (70% con soluzione corretta rispetto al
     vecchio dato a prof. 15).
  3. `ml/coda_errori.py` — formato-coda con **setup davanti** (`moves` = setup + soluzione),
     verifica di coerenza (1027/1027 ok), `rating` ibrido dichiarato stima [1000–1300].
  4. `ml/estendi_sequenze.py` — sequenze forzate multi-mossa (gap asimmetrico: mie ≥200,
     difese ≥100; tetto 3 mosse). → 903×1mossa, 94×2, 30×3 (`data/coda_errori_estesa.json`).
  5. `api/server.py` — tolto il 501; `_riempi_coda_errori` pesca prima i miei errori, poi
     **rinforzo Lichess marcato** (`origine`); caricamento a cascata esteso→base→vuoto;
     persistenza `errori_attivo`. Frontend: badge "📍 Tuo errore" / "♟ Rinforzo Lichess" /
     "🧩 Combinazione (N mosse)".
- **Test**: 61 in `api/test_server.py` + i test dei 4 moduli ml. Verificato dal vivo nel browser.
- Dettagli completi in `docs/VISIONE_ESTESA.md` (punto 6).
- **Nota onesta**: i miei errori sono per lo più tattiche secche → poche combinazioni lunghe
  (è un dato vero, non un limite del codice; per le combinazioni profonde c'è il flusso `temi`).

#### 5e. Punto 2 della visione — Report carenze + piano di studio ✅ FATTO
- Sezione **"🩺 Le mie carenze"** (endpoint `GET /profilo`), in 4 tappe:
  - **A** — report onesto: `tasso_su_mosse_per_tipo` (denominatore = mosse totali, dichiarato),
    soglia di rilevanza ≥5% (esclude inchiodatura/infilata come non-problema), `sintesi` generata
    dai numeri, nota fasi-vicine.
  - **C** — piano di studio (C2+C3): **pesi relativi, NON minuti** (peso = tasso/tasso_dominante),
    priorità alta/media/bassa, `progressione` (consiglio di metodo), `nota_posizionale` (il 38.5%
    non-tattico non è coperto), pulsante "allenati su questo tema" → flusso `temi`.
  - **D** — confronto progressi **anti-diluizione** (anticipo punto 4): profilo delle SOLE partite
    nuove vs storico (mai cumulativo vs cumulativo), `data/storico_profili.json`, rilevazione pigra,
    `solo_file` in `ml/profilo.py`, guardrail rumore <50 partite. Blocco "📈 Stai migliorando?".
- **Test**: 89 verdi (incl. test anti-diluizione). Tutto di sola lettura rispetto all'allenamento.
- Dettagli in `docs/VISIONE_ESTESA.md` (punto 2).
- Raffinamenti futuri NON fatti: tasso-su-occasioni (denom. vero, vicino al punto 5); piano dinamico
  pieno (ricalibro pesi sulle partite recenti) col punto 4 completo.

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

## PRIORITÀ MEDIA — Miglioramenti del sistema personale (da uso reale)

> Raccolti dopo aver usato il sistema. Dettaglio completo, con difficoltà e **decisioni
> aperte**, in `docs/VISIONE_ESTESA.md` → "Miglioramenti del sistema personale" (gruppi
> R / C / T). Diversi si sovrappongono col **punto 2** della visione (report carenze):
> conviene affrontarli insieme.

**Rifinitura (R) — bassa difficoltà:**
- R1. Flusso `temi`: quando un tema si esaurisce, **proseguire** (salire di difficoltà o
  continuare con l'adattività) invece di fermarsi. Riusa `_pesca_allargando` / rinforzo come
  nel flusso errori.
- R2. % "tema migliore/peggiore" = **primo colpo / tentati** (coerenza con la def. di successo).
- R3. Rendere chiari i grafici "fascia Elo nel tempo" e "% primo colpo nel tempo" (assi,
  legenda, spiegazione dell'85%).
- R4. **Schermate distinte per flusso**: nel Piano non si vedono i temi liberi; ogni flusso
  mostra solo i suoi dati.

**Coaching (C) — media, lega col punto 2:**
- C1. Flusso `piano`: tema **più definito e a rotazione** (etichetta visibile + cambio ogni
  tot in base ai risolti al primo colpo). DECISIONE APERTA: ogni quanti puzzle e con quale
  regola d'avanzamento.
- C2. Consigliare su quali **temi liberi** concentrarsi in base alle carenze.
- C3. **Piano di studio personalizzato** a punti prima dell'allenamento (quali temi, quanto
  tempo, come variare). DECISIONE APERTA: il "tempo consigliato" deve derivare da un dato
  reale (frequenza errore / tasso fallimento), non inventato.

**Trasparenza e motore (T):**
- T1. **Disclaimer alla prima partita** (cosa misura, che la difficoltà si adatta; tono
  divulgativo). NOTA onesta: la segretezza lato client è debole — il disclaimer informa
  l'utente, non protegge davvero l'algoritmo. Flag `disclaimer_visto`.
- T2. **Nuovi tipi tattici** riconosciuti (estende `ml/tattica.py`): deviazione, attrazione,
  scoperta, zwischenzug, sovraccarico… Beneficio anche sui puzzle-errore (rinforzi più
  "simili"). Ogni tema aggiunto con test, uno per volta.
- T3. **Capire cosa c'è nel "non tattico" (38.5%)**: scomporre la categoria-residuo per
  capirne la composizione (LIVELLO 1, solo conteggio). Probabile divisione in: tattiche non
  ancora riconosciute (→ T2), posizionale con soluzione netta (allenabile come i tattici,
  LIVELLO 2), posizionale puro senza mossa netta (muro del punto 5, LIVELLO 3). I livelli 2/3
  si decidono DOPO aver visto la composizione, non al buio. Onesto: non tutto è allenabile
  coi puzzle.

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
