# chess-ai — Visione estesa: da allenatore a coach personale

> Questo documento descrive la **visione estesa** del sistema, decisa dopo il
> completamento della Fase 4 (sistema personale completo). L'obiettivo è
> trasformare chess-ai da "allenatore di puzzle" a **vero coach**: analizza le
> partite, spiega le carenze in modo profondo, allena su misura, mostra gli
> errori, e verifica i progressi nel tempo.
>
> Tutto viene costruito PRIMA per l'utente singolo (Miguel), poi avvolto nel
> multi-utente (Fase 5). Ordine di costruzione concordato: 1 → 6 → 2 → 3 → 4 → 5.

---

## L'esperienza-obiettivo (come la vive l'utente)

1. Il giocatore **carica le sue partite**.
2. Il sistema le analizza e produce un **report delle carenze** — non superficiale,
   ma contestuale e specifico (es. "sbagli le combinazioni in posizioni chiuse",
   "quando sei in vantaggio non converti").
3. Il sistema propone **temi di allenamento mirati** alle carenze, e **puzzle
   ricavati dalle posizioni reali dove ha sbagliato**.
4. Durante l'allenamento fa da **coach**: quando si sbaglia, mostra l'errore e la
   mossa/sequenza corretta (frecce o sequenza passo-passo).
5. Dopo che il giocatore si è allenato e ha giocato altre partite, **ricarica le
   nuove partite** e il sistema gli mostra **se e in cosa è migliorato** rispetto a prima.

---

## I sei pezzi, in ordine di costruzione

### 1. Separazione puzzle tematici vs puzzle del piano (+ statistiche separate) ✅ FATTO
**Difficoltà: bassa (refactoring).** ~~Oggi le due modalità (piano automatico dalle
debolezze, e temi liberi) condividono coda e statistiche.~~ Separate in **tre flussi
indipendenti** (`piano`, `temi`, `errori`), strutturati fin da subito per accogliere
anche il terzo (il flusso `errori` è **predisposto ma non ancora implementato** —
arriverà col punto 6). È il fondamento strutturale su cui appoggia il resto.

Implementazione (`api/server.py` + frontend):
- **Stato per-flusso**: ogni flusso ha la PROPRIA coda, la PROPRIA fascia Elo adattiva
  (stessa regola dell'85%, indipendente), le PROPRIE statistiche (tentati, risolti al
  primo, percentuale, snapshot storici, statistiche-per-tema, storico fasce).
  `_sessione["flussi"] = {piano, temi, errori}`; `_flusso(nome)` accede a quello attivo.
- **Funzioni parametrizzate sul flusso**: `_valuta_adattivita(f)`, `_crea_snapshot(f)`,
  `_riempi_coda_tema(f, …)`, `_ricostruisci_coda_con_fascia(f)`, `_riepilogo_progressi(f)`,
  ecc. operano sul flusso passato — niente più stato globale unico.
- **Visti GLOBALI** (scelta progettuale): l'insieme dei puzzle già visti è condiviso tra
  i flussi, così non si rivede lo stesso puzzle passando da un flusso all'altro.
- **Persistenza v2**: `data/stato_sessione.json` salva i tre flussi separatamente
  (`{"versione":2, "flusso_attivo", "visti", "flussi":{…}}`). **Retrocompatibilità**: il
  vecchio file a stato singolo (v1) viene **migrato nel flusso `piano`** (default sensato:
  era la modalità di base), con i visti che diventano globali; nessun crash, nessuna perdita.
- **Riepilogo complessivo**: oltre alle statistiche per-flusso, un piccolo totale che
  somma i puzzle fatti su tutti i flussi (`/flussi` e `/statistiche` → `complessivo`).
- **Endpoint nuovi**: `GET /flussi` (elenco + attivo + complessivo) e `POST /flusso/{nome}`
  (cambio flusso; `errori` → 501 "non implementato"). `/scegli-tema` ora attiva il flusso
  `temi`. Tutti gli endpoint di lettura (`/statistiche`, `/statistiche-temi`,
  `/storico-fasce`, `/progressi`) si riferiscono al **flusso attivo**.
- **Frontend**: selettore di flusso in alto (con `errori` disabilitato "(presto)"),
  evidenzia il flusso attivo, mostra il totale complessivo; statistiche e grafici seguono
  il flusso attivo. I pulsanti-tema compaiono solo nel flusso `temi`.
- **Non-interferenza**: la regola dell'adattività resta invariata per ciascun flusso
  (successo = solo primo tentativo); le metriche/snapshot restano di sola lettura.
- **Test**: indipendenza delle fasce tra flussi, persistenza dei tre stati,
  retrocompatibilità col vecchio file, visti globali, riepilogo complessivo
  (`api/test_server.py`, 50 test verdi).

### 6. Puzzle dai propri errori, validati con Stockfish
**Difficoltà: media (calcolo).** Approccio scelto (il "terzo approccio"): NON generare
puzzle nuovi da zero (troppo complesso/ricerca), ma prendere le posizioni reali dove
il giocatore ha sbagliato e **validarle con Stockfish** tenendo solo quelle che fanno
un BUON puzzle (soluzione unica e netta — scartando i casi dove più mosse sono
equivalenti, che darebbero puzzle "rotti"). Risultato: rigiocare i propri errori veri,
ma solo quelli di qualità. Costo: ore di analisi extra (una tantum, graduale).
NOTA: estende il `puzzle.py` esistente aggiungendo la validazione di unicità.

### 2. Report leggibile delle carenze
**Difficoltà: medio-bassa (presentazione).** Trasformare il profilo (che già esiste)
in un report chiaro e leggibile: dove si è carenti (fasi), su cosa si sbaglia (motivi),
con numeri e priorità. È soprattutto presentazione di dati già calcolati.

### 3. Coaching visivo degli errori
**Difficoltà: media (frontend).** Quando si sbaglia un puzzle, mostrare l'errore e la
soluzione in modo intuitivo: frecce sulla scacchiera (chessground le supporta) e/o la
sequenza corretta passo-passo. Lavoro di frontend, non concettualmente difficile.

### 4. Confronto "prima vs dopo" (verifica dei progressi)
**Difficoltà: media.** Salvare i profili nel tempo; quando il giocatore ricarica nuove
partite, confrontare il nuovo profilo col precedente e mostrare cosa è migliorato e cosa
no (es. "mediogioco: da 24% a 19% di errori"). Attenzione all'onestà statistica: con
poche partite un cambiamento può essere rumore — il sistema deve dirlo.

### 5. Diagnosi profonde e contestuali
**Difficoltà: ALTA (il muro — alcune quasi-ricerca).** Questo è il pezzo più difficile e
va affrontato DIAGNOSI PER DIAGNOSI, perché alcune sono fattibili e altre molto complesse:
- **"Non converte il vantaggio"**: FATTIBILE. Si individuano le partite dove il giocatore
  era in vantaggio secondo Stockfish e ha pareggiato/perso, tracciando l'evoluzione della
  valutazione.
- **"Sbaglia in posizioni chiuse/aperte"**: DIFFICILE. Richiede di classificare la natura
  della posizione (struttura dei pedoni) — concetto posizionale, non geometrico.
- **"Combinazioni"** e altri concetti strategici: da valutare caso per caso.
Va trattato come discussione dedicata, separando ciò che è calcolabile da ciò che non lo è
senza un grande sforzo. Meglio poche diagnosi VERE e oneste che tante superficiali.

---

## Step successivo (dopo i sei pezzi)

### Studio delle aperture
Aggiungere progressivamente lo studio di **tutte le aperture**. Capitolo ampio e a sé,
da progettare quando i sei pezzi saranno completati.

---

## Principi da rispettare (validi per tutto)

- **Onestà sopra l'apparenza**: niente diagnosi superficiali o metriche ingannevoli.
  Se un dato è rumore statistico, dirlo. (Es: la % di successo tende all'85% per
  l'adattività — non è un segno di non-miglioramento; il vero indicatore è la fascia Elo.)
- **Separazione netta dei flussi**: piano automatico, temi liberi, errori propri —
  flussi e statistiche distinti.
- **Costruire prima per l'utente singolo**, poi avvolgere nel multi-utente (Fase 5).
- **Validare sempre con Stockfish** ciò che si propone come puzzle (unicità soluzione).
- **Non-interferenza con l'adattività**: le nuove metriche/statistiche sono di sola
  lettura, non influenzano la fascia Elo di base.

---

## Stato attuale (Fase 4 completa + punto 1 della visione)

Funziona già end-to-end: analisi partite, profilo debolezze, piano automatico, scacchiera
giocabile, difficoltà adattiva con gestione esaurimento, persistenza tra sessioni, 24 temi
categorizzati, statistiche e grafici dei progressi (fascia Elo + % nel tempo + tendenza +
tabella riassuntiva). Suite di test ampia, CI verde.

**Punto 1 fatto**: i flussi sono ora separati (`piano` / `temi` / `errori`), ciascuno con
coda, fascia Elo adattiva e statistiche proprie; visti globali; persistenza a tre stati con
migrazione dal vecchio formato; flusso `errori` predisposto. Prossimo passo: **punto 6**
(puzzle dai propri errori, validati con Stockfish), che popolerà il flusso `errori`.
