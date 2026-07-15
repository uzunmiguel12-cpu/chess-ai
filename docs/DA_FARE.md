# chess-ai — Cose da fare e da implementare

> **PER LA PROSSIMA SESSIONE (Cowork) — leggere prima.**
> Ruoli: **Miguel** è l'ARCHITETTO/decisore; **Claude** è l'ESECUTORE tecnico.
> Regole operative: rispondere in **italiano**; ambiente **Windows 11 / cmd.exe** (NON PowerShell);
> passi piccoli e verificabili; **diagnosi prima della soluzione** ("guarda, non assumere");
> riusare il codice esistente; le decisioni di **onestà statistica NON si prendono da soli** — fermarsi
> e chiedere a Miguel; **committare solo quando esplicitamente richiesto**; gli script di misura sono
> READ-ONLY e **`data/` è sacra (gitignorata)**; principio guida **"sostanza non apparenza"**
> (marcare [STIMA] vs [DATO]).
> Nota ambiente: il sandbox Cowork può servire versioni **TRONCATE** dei file appena editati alle
> letture da bash (quindi esbuild/pytest/git via bash sono inaffidabili sui file grandi appena
> modificati) — verificare via tool Read + python-chess + esbuild su copie in /tmp; **non committare da
> bash quando il mount è troncato** (committare dal terminale reale).
> Stato attuale e prossimi passi: vedi "Dove siamo arrivati" (sotto) e le priorità. Visione completa
> in `docs/VISIONE_ESTESA.md`; cosa manca ancora, in forma sincronizzabile, in `docs/BACKLOG.md`.

> Stato del progetto: **Fase 4 + tutti e sei i pezzi del coach + gruppo R completo + C1 + T3 + fix
> classificazione + T2 avviato-e-fermato.** Sistema personale completo, coerente e onesto.
> Questo documento elenca ciò che manca ancora, diviso per priorità.
> Aggiornato al termine della sessione dei miglioramenti R/C/T: gruppo R completo (R1-R4), C1
> (interlacciamento blocchi), T3 (scomposizione non_tattico), fix classificazione tattica (best move),
> T2 fermato dopo la scoperta (ritorno ~0). Lezione: il margine di crescita è POSIZIONALE, non tattico.

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

### Aggiornamento — sito React + moduli Aperture / Principi / Impostazioni (luglio 2026)

Il frontend è stato **rifatto in React (Vite)** come sito multi-pagina con design system
(`frontend/src/styles/theme.css`, token CSS). Pagine: Home, Allenamento, Aperture, Principi,
Carenze, Progressi, I miei dati, Impostazioni. Nav in alto con avatar + nome utente. Le
preferenze sono in `frontend/src/ImpostazioniContext.jsx` (React Context + localStorage).

- **Aperture** (`/aperture`): galleria "Tutte le aperture" (card con mini-scacchiera) +
  "Aperture guidate" (calibrazione a 7 fasce Elo). Lo studio di un'apertura parte SEMPRE dalla
  mossa 1 (fase guidata) e poi esplora le varianti ECO; toggle Linee/Puzzle, menu "Vedi le linee",
  box Coach in alto a destra. Puzzle d'apertura = solo linea principale, verifica lato server.
  Rosa curata di ~31 aperture + copertura ECO. File: `frontend/src/components/StudioApertura.jsx`,
  `rag/aperture.py`, `rag/consiglio_aperture.py`, endpoint in `api/server.py`.
- **Coach aperture**: pipeline precompute-once → cache. `rag/genera_coach.py` (Ollama, modello
  `qwen3:8b`, in locale) genera i testi in `rag/coach_aperture.json` (~8439 nodi, gitignorato);
  a runtime solo lookup (`rag/coach.py`, endpoint `/aperture/coach`). NB: 16GB RAM sono al limite
  per qwen3:8b — se cade per memoria, valutare `qwen3:4b`. Lo script ha retry + salvataggio a ogni nodo.
- **Principi** (`/principi`): studio posizionale statico in `frontend/src/data/principi.js` (tutte
  le posizioni verificate con python-chess). **12 temi**: centro, sviluppo, sicurezza del re,
  struttura di pedoni, attività dei pezzi, spazio, case deboli, formulare un piano, Attacco al re,
  Motivi tattici, Cambi e semplificazione, Finali. Ogni principio: descrizione,
  riconoscere/sfruttare/difendersi, esempi giocabili (avanti/indietro + commenti del coach) e quiz
  interattivo (teoria + puzzle, uno alla volta). Collegato dalle Carenze (MAPPA_FASE → temi).
- **Carenze**: sezione "Principi da ripassare" (dai tuoi errori posizionali non-tattici) + card
  "Evoluzione nel tempo" con 2 grafici (tassi d'errore per fase e per tipo, periodo-per-periodo,
  dall'endpoint `/storico-profili`; onesti: punti da poche partite marcati piccoli, stato vuoto se
  storico insufficiente).
- **Impostazioni** (9 sezioni): Profilo (nome + avatar), Scacchiera e pezzi (6 temi colore + 3 set di
  pezzi SVG originali), Preferenze allenamento (velocità animazioni, mosse possibili, tentativi —
  CABLATE nella scacchiera di Allenamento), Accessibilità (dimensione testo, contrasto, riduci
  animazioni, suoni reali via Web Audio in `frontend/src/suoni.js`), Dati e privacy
  (esporta/importa/azzera/cancella impostazioni), Sistema e connessione (URL backend configurabile,
  ping + latenza, diagnostica), Abbonamenti e Account (segnaposto onesti Fase 5), Info e note legali
  (licenze open-source: chessground e Stockfish **GPL-3.0**). Versione app in `frontend/src/config.js`
  (`APP_VERSION = 0.5.0`).
- **Estetica**: bottoni/tab/toggle uniformati e centrati, hover morbidi, focus accessibile.
- **Git**: checkpoint `eb71cf1` (54 file, +7447 righe). Corretto il `.gitignore`: la regola `data/`
  (non ancorata) ignorava per errore **`frontend/src/data/`** (cioè `principi.js`); ora `/data/`
  (solo la radice, che resta sacra); ignorati `.claude/`, la cache `rag/coach_aperture.json` e il
  binario `engine/bin/` (Stockfish, ~109MB).

**Prossimi passi naturali**: estrazione dati Chess.com (backend reale dietro la pagina "I miei dati");
Fase 5 multi-utente (account, DB, hosting); rifinitura funzionale di Abbonamenti/Account quando ci sarà
il backend utenti.

### Aggiornamento — sezione SPARRING + modello posizionale (luglio 2026) ✅ FATTO

Nuova sezione `/sparring` (nav: tra Aperture e Principi): partita contro bot a livelli
(Skill Level Stockfish) con coach posizionale realtime dopo ogni mossa dell'utente
(teoria/ok/tattico/posizionale + feature peggiorate [DATO] + rischio ML [STIMA]).
Componenti: `ml/caratteristiche_posizionali.py`, `ml/dataset_posizionale.py`,
`ml/allena_posizionale.py`, `api/sparring.py`, `frontend/src/pages/Sparring.jsx`.
Modello allenato su 101.173 mosse non tattiche da `data/analisi` (split per partita):
MAE 45.4 vs baseline 47.7, AUC rischio 0.667 [DATO] — segnale debole ma reale,
coerente con l'esito T3. Dettagli, avvio e retraining: `docs/SPARRING.md`.
NON committato: da fare dal terminale reale (regola del mount troncato).

## PRIORITÀ ALTA — Roadmap modello posizionale (decisa da Miguel, luglio 2026)

Ordine vincolante: **prima le feature, poi il volume, poi la rete**. Razionale: con le
20 feature attuali l'AUC 0.667 e' limitato dall'input, non dalla capacita' del modello —
un modello piu' grosso sulle stesse feature non migliora nulla [DATO, misurato].

### S1. Arricchire le feature posizionali ✅ FATTO (luglio 2026)
- Provate 6 feature; misura di accettazione applicata (permutation importance
  sul test split per partita). TENUTE (decisione di Miguel): case_deboli,
  attivita_re, intrappolati, sospesi. BUTTATE: grandi_diagonali e
  passati_bloccati (importanza negativa = rumore).
- Esito [DATO]: MAE 45.4→45.34, AUC 0.667→0.669 con 26 feature. Guadagno
  minimo: il tetto e' il RUMORE DEL TARGET (cp_loss delle mosse tranquille a
  prof. 15), non l'input ne' la capacita' del modello. Conferma che la
  prossima leva e' S2 (volume).
- Artefatti aggiornati: `ml/caratteristiche_posizionali.py` (26 feature),
  `data/dataset_posizionale.csv` (59 colonne), `data/modello_posizionale.joblib`.
  Coerenza modulo↔modello verificata. NON committato (mount troncato: commit
  dal terminale reale).
- Nota operativa sandbox: scrivere il CSV in append sul mount PERDE righe —
  generare su /tmp e copiare con un singolo `cp` alla fine.

### S2. Dataset Lichess per volume ✅ FATTO (luglio 2026) — ACCETTATA

- `ml/dataset_lichess.py`: legge un dump mensile (.pgn.zst locale o --url in
  streaming senza salvarlo), tiene solo partite standard con [%eval], no bullet
  (base <180s), Elo in fascia (default 1400-2200); cp_loss dagli eval consecutivi
  (POV di chi muove); stessi filtri e STESSE COLONNE del dataset personale.
- DIVERGENZA DICHIARATA [STIMA]: nel dump manca la best move → "tattica" =
  cp_loss>=300 O mossa cattura/scacco/promozione (criterio piu' largo, documentato
  nel docstring). Test verdi in `ml/test_dataset_lichess.py`.
- Run di volume eseguito da Miguel sul PC (dump 2026-06): 30.000 partite utili
  su 681.191 lette → 1.562.239 righe in `data/dataset_lichess.csv`.
- Training combinato (1.150.774 mosse non tattiche, 33.275 partite, split per
  partita): **AUC 0.669 → 0.6979, MAE 41.66 vs baseline 44.54** [DATO].
  Criterio di accettazione (AUC > 0.669) SUPERATO: il volume media il rumore
  del target e il segnale posizionale emerge. Modello in produzione aggiornato
  (`data/modello_posizionale.joblib`, caricato da api/sparring.py all'avvio).
- Per estendere: altri mesi del dump con `--append` (e `--salta-partite` per
  riprendere un mese interrotto), poi riallenare.
- NOTA distribuzione: il modello ora e' allenato ~93% su partite Lichess
  1400-2200 e ~7% su partite di Miguel — coerente con l'uso (coaching nella
  stessa fascia), ma da ricordare quando si leggono le probabilita' [STIMA].

**Curva di scaling misurata** (`ml/curva_scaling.py`, test fisso da 6.655
partite, run di Miguel, luglio 2026) [DATO]:

| frazione train | partite | AUC | MAE |
|---|---|---|---|
| 10% | 2.662 | 0.6774 | 42.14 |
| 25% | 6.655 | 0.6876 | 41.87 |
| 50% | 13.310 | 0.6938 | 41.78 |
| 100% | 26.620 | 0.6979 | 41.66 |

Lettura: crescita ancora presente ma logaritmica (~+0.004-0.005 per raddoppio).
Proiezione onesta [STIMA]: con 2-3 mesi di dump in piu' si arriva verso
~0.70-0.71, poi plateau di questo approccio (feature fatte a mano + GBM).
Conclusione: altri mesi di dump sono un guadagno facile ma limitato; il salto
di qualita' successivo richiede S3.

### S3. Rete neurale con spiegazioni deterministiche — SCHELETRO PRONTO, training DA FARE

Decisione (dopo la curva di scaling): doppio binario — Miguel aggiunge 2-3 mesi
di dump al GBM (guadagno facile fino a ~0.70-0.71 [STIMA]), in parallelo si
prepara la rete. Scheletro scritto e validato in sandbox (luglio 2026):

- `ml/rete/estrai_posizioni.py`: CSV (partita, fen, mossa, cp_loss, tattica,
  eval_prima) da data/analisi E/O dal dump Lichess — la rete ha bisogno delle
  FEN, non delle feature. Stessi filtri dei dataset a feature. TESTATO.
- `ml/rete/tensori.py` (solo numpy, testato): 24 piani 8x8 (posizione prima +
  dopo la mossa), PROSPETTIVA DI CHI MUOVE (mirror per il Nero — proprieta' di
  simmetria verificata su casi reali), eval_prima scalare normalizzato.
- `ml/rete/modello.py` (PyTorch): ResNet configurabile — 64x6 ≈ 0.5M parametri
  (prova CPU), 128x10 ≈ 3M (default), 192x12 ≈ 8M (GPU).
- `ml/rete/allena_rete.py` (PyTorch): split per partita, BCE, AUC su val per
  epoca, salva il migliore in `data/rete_posizionale.pt`.
- Il sandbox non puo' installare torch (wheel troppo grande): i file PyTorch
  sono verificati solo a sintassi — il primo run e' anche il loro smoke test.

**ESITO (run di Miguel, GPU NVIDIA, luglio 2026) — RETE PROMOSSA** ✅:
- Training 128x10 (3.0M parametri), 920k mosse train / 231k val (split per
  partita): AUC val **0.7095** in 8 epoche (~5 min/epoca su GPU), curva ancora
  in lieve crescita all'ultima epoca.
- Confronto onesto (`ml/rete/confronta_gbm_rete.py`, GBM riallenato sulle
  STESSE partite di train e valutato sulle STESSE partite di val):
  GBM 0.6996 vs RETE 0.7095 = **+0.0099** [DATO] -> promozione motivata.
- Integrata in `api/sparring.py`: 1a scelta la rete (`data/rete_posizionale.pt`,
  richiede torch), fallback automatico al GBM (`modello_posizionale.joblib`),
  senza entrambi il pannello funziona senza campo rischio. Il campo
  `modello_rischio` nella risposta dichiara quale modello ha stimato il rischio.
  Fallback testato in sandbox (senza torch -> GBM, nessun errore).
- PRINCIPIO RISPETTATO: la rete RILEVA (probabilita' di errore), le SPIEGAZIONI
  restano deterministiche (feature peggiorate = [DATO]).

**Round 2 (deciso da Miguel): piu' dati + rete 192x12 + 16 epoche.**
- torch DOCUMENTATO in requirements.txt come dipendenza consigliata (il
  fallback GBM resta: senza torch il backend funziona).
- `ml/rete/valuta_rete.py` (nuovo): valuta piu' checkpoint sullo STESSO val set
  ricostruito dai CSV attuali — necessario perche' aggiungendo un mese di dump
  lo split cambia e le AUC salvate nei .pt non sono confrontabili tra loro.
- Procedura (sul PC):
  1. secondo mese di posizioni (sera): `estrai_posizioni.py --url <dump 2026-05>
     --max-partite 30000 --out ..\..\data\posizioni_lichess.csv --append`
  2. training grande (notte, GPU): `allena_rete.py --dati <personali> <lichess>
     --canali 192 --blocchi 12 --epoche 16 --batch 384 --workers 2
     --out ..\..\data\rete_192.pt`  (OOM -> ridurre --batch)
     NB: --out SEPARATO per non toccare la rete in produzione durante il run.
  3. confronto pulito: SU UN MESE TERZO mai visto da nessuna delle due reti
     (vedi sotto — lezione contaminazione).
  4. se la nuova vince [DATO]: `copy /Y data\rete_192.pt data\rete_posizionale.pt`
     e riavvio del backend. Se perde: resta la 128x10 e lo si scrive qui.

**LEZIONE — contaminazione del confronto (luglio 2026)**: il primo confronto
tra 128x10 e 192x12 era INVALIDO: ricostruendo lo split sul dataset a due mesi,
il val set conteneva partite che erano nel TRAINING della rete vecchia → il suo
AUC usciva gonfiato (0.7427 apparente vs 0.7095 reale del suo split originale).
Regola da qui in poi: reti allenate su dataset diversi si confrontano SOLO su
un mese di dump neutrale, mai usato in training, con `valuta_rete.py --tutte`:
```cmd
python estrai_posizioni.py --url <dump 2026-04> --max-partite 5000 --out ..\..\data\posizioni_test.csv
python valuta_rete.py --dati ..\..\data\posizioni_test.csv --tutte --reti ..\..\data\rete_posizionale.pt ..\..\data\rete_192.pt
```

**ESITO ROUND 2 (test neutrale su dump 2026-04, 5k partite) — 192x12 PROMOSSA** ✅:
- 128x10: AUC 0.7082 (≈ il suo 0.7095 originale: conferma che il test neutrale
  e' sano e che il 0.7427 era contaminazione);
- 192x12 (8M parametri, 2 mesi di dump, 16 epoche): **AUC 0.7324** = +0.024 [DATO].
- Promossa: copiata su `data/rete_posizionale.pt` (il vecchio checkpoint resta
  in `data/rete_192.pt` come copia). torch documentato in requirements.txt.
- Storia completa del rischio posizionale: GBM feature 0.667 → S1 0.669 →
  S2 volume 0.698 → rete 3M 0.7095 → rete 8M **0.7324** (test neutrale).

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

#### 5f. Punti 3, 4, 5 della visione ✅/🔶 FATTI in questa sessione
- **Punto 3** ✅ (base) — coaching visivo: freccia verde sulla soluzione (chessground `drawable`) +
  mossa in SAN leggibile, pulizia frecce tra puzzle. Futuro: freccia rossa dell'errore, replay
  passo-passo multi-mossa.
- **Punto 4** ✅ (sostanza) — confronto prima/dopo: già coperto dalla Tappa D del punto 2 + grafico
  "📉 Evoluzione nel tempo" (tassi dei PERIODI, anti-diluizione; endpoint `/storico-profili`; stato
  vuoto finché <2 snapshot). Futuro: piano dinamico pieno.
- **Punto 5** ✅ CHIUSO (verdetto dimostrato) — due tappe:
  - **5a. Conversione del vantaggio** (`ml/converti_vantaggio.py`, endpoint `/diagnosi-conversione`,
    blocco "🎯 Conversione del vantaggio"). Distingue crollo da **erosione** (calo graduale senza
    errore singolo). Filtri onesti: **no bullet** + **tetto picco +2÷+6** → da 388 grezze a **56
    erosioni vere**. Solo consapevolezza (partite da rivedere), niente puzzle.
  - **5b. Diagnosi posizionali generali** — il MURO. Affrontato con due giri di SOLA MISURAZIONE
    (`ml/analizza_posizionale.py`, `ml/analizza_aperture.py`), verificati a campione. ESITO: NON
    diagnosticabili in pattern allenabili con euristiche semplici. Dettagli in 5g più sotto.
- Dettagli in `docs/VISIONE_ESTESA.md` (punti 3/4/5).

#### 5g. Diagnosi posizionali — MISURAZIONE e VERDETTO ✅ (il muro, dimostrato)
- Errori posizionali puri = mia mossa cl≥200, non-bullet, best che NON cattura / NON dà scacco /
  NON promuove / NON è tattica riconosciuta (riusa `ml/tattica.py`). Sola lettura, niente puzzle.
- **Denominatore misurato**: 1352 errori posizionali puri = **32.1%** degli errori gravi non-bullet
  (4214). [Più affidabile della stima ~75%×45% dell'handoff: lì mancavano i filtri scacco/promozione
  e l'esclusione delle tattiche già etichettate.]
- **Segnali VERI** (DATO): fase (apertura 46.4% / mediogioco 36.5% / finale 17.2%) e tipo di pezzo.
- **Segnali BUTTATI** ([STIMA] smentite dai campioni): "re esposto" (marcava esposto il ~65% — non
  discrimina; segnava esposto pure re in casa a mossa 7) e "natura della best" (43.9% in "altro",
  guarda la geometria non l'idea). Stessa trappola di T3: numeri che fanno scena, vuoti.
- **Secondo giro mirato all'apertura** (`analizza_aperture.py`, separato per colore, chiave-sequenza
  + chiave-FEN4 con trasposizioni collassate): quota cumulativa top-5 fen4 BIANCO **18.8%** (sparso,
  sotto soglia 25%), NERO **31.0%** ma trainato da un solo gruppo (`1.e4 e5 2.Nf3 Nc6`, 18.8%) che è
  l'apertura più GIOCATA, non un buco di teoria. I campioni confermano: errori a mossa 9/12/13 dentro
  lo stesso "gruppo d'apertura" → i gruppi condividono l'inizio, NON il pattern d'errore.
- **VERDETTO**: il posizionale d'apertura e di mediogioco NON è scomponibile in diagnosi allenabili
  con regole semplici. Coerente con la visione ("alcune non si fanno"). Un "no" dimostrato con
  misurazione + verifica a campione, non un abbandono.
- **Unica pista NON esclusa** (ipotesi, non verificata): tecnica di FINALE (17.2%, quasi tutto
  torre+re). Posizioni-tipo con soluzione netta → in teoria compatibile col filtro-unicità del
  punto 6. Da valutare semmai più avanti; oggi NON fatta. (Annotata nel docstring di
  `analizza_posizionale.py`.)
- Script tenuti e documentati con blocco ESITO in cima (commit a6e5f62), non cancellati: sono la
  prova ricostruibile del "no".

#### 5i. Tecnica di finale — DIAGNOSTICA e COSTRUITA end-to-end ✅ (15/06)
- Il PRIMO "si'" del punto 5, dopo cinque "no". La tecnica di finale SI scompone per tipo.
- Misurato (`ml/analizza_finali.py`, tasso non volume, bullet escluso, verificato a campione
  col controllo-fase): finale_torre 3.4% (3443 mosse) = peggiore, finale_donna 0.9% (3020) =
  migliore; rapporto 3.63x, estremi entrambi robusti. Donna basso = calcolo tattico già
  allenato; torre alto = tecnica posizionale, il vero margine (coerente con tutto il punto 5).
- COSTRUITO in pipeline (strada snella, NON script orfano):
  - `ml/finali.py` (nuovo): conta_pezzi, classifica_finale (spostate da analizza_finali.py,
    una sola versione), tassi_finali_per_tipo.
  - `ml/profilo.py`: campo `finali_per_tipo` in costruisci_profilo (stesso ciclo di vita del
    profilo, rispetta solo_file → eredita gratis l'anti-diluizione in futuro).
  - `api/server.py`: sezione report `studio_fasi` (funzione _studio_fasi), SEPARATA dal piano
    tattico, con denominatore dichiarato ("mosse in finale di quel tipo, diverso dal tattico").
  - frontend: sezione "🎯 Studio per fasi di gioco — Finali" sotto il piano tattico, barre oneste,
    peggiore evidenziato, pulsante "allenati su questo finale" che attiva Temi>finale_di_torre.
- Il tema finale_di_torre→rookEndgame ESISTEVA GIA' in TEMI (server.py ~156); il DB ha 54k
  puzzle rookEndgame alla fascia ~1000. Quindi diagnosi→azione quasi gratis: nessun generatore.
- ⚠️ ASIMMETRIA BULLET VOLUTA: `studio_fasi` esclude il bullet (coerente con TUTTA la diagnostica
  del progetto: nel bullet l'errore è il tempo, non la posizione). Il resto del profilo tattico
  è invece bullet-inclusivo. NON è una svista: è la scelta che rende i tassi finali coerenti con
  la diagnosi verificata (a bullet incluso il peggiore diventava finale_pedoni, falsato). Non
  "correggere" allineando i due senza ripensarci.

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

**Rifinitura (R) — GRUPPO COMPLETO ✅:**
- R1. ✅ Flusso `temi`: allargamento SIMMETRICO della finestra di pesca (prima su, poi giù) in
  `_pesca_allargando`, + messaggio di esaurimento VERITIERO ("hai esaurito i puzzle vicini al tuo
  livello, ne esistono di più difficili"). Misurato: nessun tema è povero nel DB (anche infilata ha
  133k puzzle); il blocco era l'allargamento solo-verso-l'alto. La fascia di BASE resta intatta
  (test anti-regressione). Niente fallback a puzzle misti (tradirebbe la scelta del tema).
- R2. ✅ Era GIÀ CORRETTO: tema migliore/peggiore già su `risolti_primo / tentati`. Nessuna modifica.
  (Guardrail sul campione minimo NON aggiunto — scelta dell'utente.)
- R3. ✅ Grafici resi non-ingannevoli: sottotitolo onesto sull'85% sul grafico % primo colpo (+ linea
  di riferimento tratteggiata a 85%, "performance reale" vs "bersaglio adattivo"); grafico Elo con
  scala Y senza beginAtZero (grace 10%) e sottotitolo "vero indicatore di crescita".
- R4. ✅ Schermate separate per flusso (3 tappe): cornice a 3 pannelli con scacchiera UNICA condivisa
  + `pulisciScacchiera()` al cambio flusso (no stato residuo); progressi spostati DENTRO ogni pannello
  via toggle (un solo set di canvas, appendChild); estratto-carenze nel Piano (riusa /profilo, mostra
  le 2 debolezze principali + link "Vedi tutte le carenze →"). Carenze restano GLOBALI separate.

**Coaching (C):**
- C1. ✅ Flusso `piano`: INTERLACCIAMENTO dei blocchi (era il vero fastidio: i blocchi erano
  CONCATENATI, ~20 puzzle stesso tema di fila). Helper `_interlaccia_blocchi` (mini-blocchi da
  DIMENSIONE_MINI_BLOCCO=5, round-robin tra i temi, mai 2 mini-blocchi stesso tema di fila). Stesso
  multiset di puzzle (test anti-perdita). NON pesato per priorità (Livello 2, rimandato).
- C2/C3. (parzialmente coperti dal punto 2 / estratto-carenze). Restano: pesare la rotazione del Piano
  per priorità (Livello 2 di C1).

**Trasparenza e motore (T):**
- T3. ✅ FATTO (sola misurazione) — `ml/analizza_non_tattico.py` + `/`. Scompone il "non_tattico"
  classificando sulla BEST move. CORRETTO in corso d'opera per allinearsi al profilo (prima misurava
  sulla mia mossa, ingannava). Risultato VERO sui dati: non_tattico ~45% degli errori gravi non-bullet,
  di cui ~25% "tattica non coperta" e ~75% POSIZIONALE puro (il muro). Niente tesoro tattico nascosto.
- FIX CLASSIFICAZIONE ✅ (scoperto grazie a T3) — `ml/arricchisci.py` ora calcola `tipo_tattico` dalla
  BEST move (tattica MANCATA) invece che dalla mia mossa. Concettualmente corretto. EFFETTO NUMERICO
  QUASI NULLO (i flussi nei due sensi si compensano: non_tattico resta ~45%) — NON il grande recupero
  che sembrava. Richiede di rigenerare `data/categorie/` con `python ml/arricchisci.py`.
- T2. 🔶 AVVIATO e FERMATO (ritorno ~0). Aggiunto lo SCACCO DI SCOPERTA a `ml/tattica.py`
  (`scoperta_creata`, etichetta "scoperta") — il tipo più affidabile da riconoscere. Misurato: recupera
  solo ~6 errori su 12046. Conclusione onesta: gli scacchi di scoperta sono rari nei miei errori; gli
  altri tipi (deviazione/attrazione/sovraccarico) sono più concettuali, più inclini a falsi positivi, e
  renderebbero anch'essi poco. T2 fermato qui. La scoperta resta (non fa danno). Il margine di crescita
  vero è POSIZIONALE, non tattico.
- T1. ❌ NON fatto — disclaimer alla prima partita. Minore. NOTA onesta: segretezza lato client debole.

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
