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

### 6. Puzzle dai propri errori, validati con Stockfish ✅ FATTO
**Difficoltà: media (calcolo).** Approccio scelto (il "terzo approccio"): NON generare
puzzle nuovi da zero, ma prendere le posizioni reali dove il giocatore ha sbagliato e
**validarle con Stockfish** tenendo solo quelle che fanno un BUON puzzle (soluzione unica
e netta). Risultato: rigiocare i propri errori veri, ma solo quelli di qualità.

Realizzato come **pipeline a tappe verificabili**, senza rifare l'analisi delle partite
(le analisi a profondità 15 esistono già in `data/analisi/*.json` e contengono per ogni
mossa `fen`, `move_uci`, `best_move_uci`, `eval_prima/dopo`, `centipawn_loss`):

- **Estrazione** (`ml/estrai_errori.py`, sola lettura): scorre le ~3269 analisi, riconosce
  le mie mosse (colore dai campi `bianco`/`nero`, turno dal FEN), applica un **filtro di
  sanità** (scarta posizioni già perse/vinte a fondo, oltre ±700cp, e i mate-score) e conta
  i candidati a soglie di `centipawn_loss` ≥100/200/300, separando bullet da non-bullet.
  Salva i candidati ≥200 in `data/candidati_errori.json`. **Scelta**: il **bullet è
  ESCLUSO** dai puzzle-errore (un errore in bullet è spesso mancanza di tempo, non un buco
  di visione); il campo `cadenza` resta salvato, così la scelta è reversibile.
  Misurato: 4604 candidati non-bullet a ≥200.
- **Validazione unicità** (`ml/valida_errori.py`, usa Stockfish): per ogni candidato
  rianalizza la posizione **prima** dell'errore in **MultiPV=2** e calcola il `gap` (cp) tra
  1ª e 2ª mossa; tiene il puzzle solo se la soluzione è netta (**gap ≥ 200**), i matti a
  favore di chi muove passano sempre. La soluzione salvata è quella **rivalidata a
  profondità 18** (NON il vecchio best a prof. 15). Modalità `--campione` per la taratura
  (tasso di sopravvivenza per soglia, tempo medio, stima del batch) e `--batch` con
  salvataggio incrementale e ripartenza. **Taratura**: prof. 18 vs 20 quasi identiche →
  scelta prof. 18 (più veloce, stessa sostanza). **Esito batch**: 4604 → **1027 puzzle
  tenuti** (gap ≥200), 3577 scartati come "rotti"; **714/1027 (70%) avevano soluzione
  diversa dal vecchio dato a prof. 15** — la rivalidazione non era pignoleria.
- **Formato-coda** (`ml/coda_errori.py`, sola lettura): trasforma i puzzle validati nello
  **schema esatto della coda** (`id, fen, moves, rating, themes, motivo_allenamento,
  fase_allenamento`). Punti chiave: `moves` ha la **mossa di setup davanti** (la mossa
  avversaria a `indice-1`, recuperata dall'analisi originale) seguita dalla soluzione,
  perché il frontend fa `moves.slice(1)` (la 1ª è setup giocato in automatico); il `fen` è
  la posizione prima del setup. **Verifica di coerenza** con python-chess (applicando il
  setup al fen si ottiene la posizione dell'errore): **1027/1027 coerenti, 0 scartati**.
  Il `rating` è una **stima ibrida DICHIARATA RUVIDA**: centro 1150, gap grande→più facile
  (rating più basso), gap piccolo→più difficile (più alto), matto→1000, clamp [1000,1300].
  Distribuzione reale ben sparsa (media 1177).
- **Estensione multi-mossa** (`ml/estendi_sequenze.py`, usa Stockfish): allunga ogni puzzle
  in **sequenza forzata** finché entrambi i lati sono costretti (mia mossa: gap ≥200; difesa
  avversaria: gap ≥100 — **asimmetrico**, perché il cuore del puzzle è la MIA mossa), con
  stop su scelta/matto/posizione decisa (+800) e **tetto di 3 mosse mie**; invariante: la
  soluzione finisce sempre su una mia mossa. Aggiunge `lunghezza_soluzione` (1/2/3) e salva
  `data/coda_errori_estesa.json` (senza toccare il file base). **Esito onesto**: i miei
  errori sono per lo più **tattiche secche** → **903 da 1 mossa (87.9%), 94 da 2 (9.2%),
  30 da 3 (2.9%)** = 124 combinazioni vere. Non forzato oltre: allungare di più avrebbe
  creato sequenze finte (per le combinazioni lunghe c'è il flusso `temi` sui 6M Lichess).
- **Aggancio al flusso `errori`** (`api/server.py` + frontend): rimosso il **501**; il
  flusso carica i puzzle a cascata (esteso → base → vuoto, con fallback robusto),
  `_riempi_coda_errori(f)` (gemella di `_riempi_coda_tema`) pesca **prima dai miei errori**
  nella fascia adattiva (riusando `_pesca_allargando`) e, se si esauriscono, **completa con
  rinforzi Lichess** della stessa fascia **marcati** (`origine: "lichess"`,
  `motivo_allenamento: "rinforzo"`) — così non si blocca mai ma resta sempre chiaro cosa si
  sta giocando. Persistenza via flag `errori_attivo`; ricostruzione coda dopo ricalibro
  adattivo; visti globali rispettati. **Frontend**: selettore `errori` abilitato (via il
  "(presto)"), badge **"📍 Tuo errore"** vs **"♟ Rinforzo Lichess"**, e
  **"🧩 Combinazione (N mosse)"** per `lunghezza_soluzione > 1`.
- **Test**: 61 test verdi in `api/test_server.py` (caricamento a cascata + fallback, pesca
  errori-prima-poi-rinforzo, niente più 501, indipendenza fascia, persistenza `errori_attivo`,
  visti globali, sopravvivenza di `lunghezza_soluzione`), più i test dei moduli ml
  (`estrai_errori`, `valida_errori`, `coda_errori`, `estendi_sequenze`).
- **Verificato dal vivo** nel browser: il flusso errori serve i puzzle col badge corretto e
  le **sequenze multi-mossa si giocano fino in fondo** (mia mossa → risposta avversaria
  automatica → mia mossa successiva).

### 2. Report leggibile delle carenze ✅ FATTO
**Difficoltà: medio-bassa (presentazione)** — ampliata in corso d'opera con consigli azionabili
(C2/C3) e un anticipo onesto del punto 4 (snapshot nel tempo). Realizzato in 4 tappe verificabili:

- **Tappa A — Report statico + tassi.** Endpoint `GET /profilo` che arricchisce il profilo già
  calcolato (`ml/profilo.py` resta puro; arricchimento nel server). Aggiunge:
  - `tasso_su_mosse_per_tipo` — **tasso VERO con denominatore dichiarato** = errori-di-quel-tipo /
    mosse totali (es. "pezzo in presa: 9.4% delle mosse, una ogni ~11"). NON il volume assoluto, NON
    un tasso-su-occasioni (quello — "forchette mancate / forchette disponibili" — richiederebbe di
    riconoscere le occasioni su ~108k posizioni: rimandato, è vicino al punto 5).
  - **Soglia di rilevanza** (≥5% degli errori gravi): separa i temi reali dal rumore. Sui dati di
    Miguel: pezzo_in_presa (45.5%) e forchetta (15.1%) rilevanti; inchiodatura (0.8%) e infilata
    (0.1%) **dichiarati non-problema** — non si consigliano temi che sono rumore statistico.
  - **`sintesi`** onesta generata dai numeri (tema dominante + fasi; temi non-problema; e che il
    ~38.5% `non_tattico` è posizionale, **non allenabile coi puzzle tattici** — gancio a punto 5/T3).
  - Nota se i tassi per fase sono **vicini** (`fasi_divario_piccolo`), per non drammatizzare divari
    piccoli (mediogioco 24.8% vs finale 17.8%).
  - Frontend: sezione dedicata **"🩺 Le mie carenze"** (sintesi → COME → DOVE → QUANTO).
- **Tappa C — Piano di studio personalizzato (C2+C3), ONESTO.** Campo `piano_studio`: solo temi
  rilevanti, **pesi RELATIVI non minuti** (peso = tasso_tema / tasso_dominante; il dominante = 1.0;
  priorità alta/media/bassa). Niente minuti inventati: dice *cosa* conta di più e *quanto* di più.
  `progressione` = consiglio di metodo statico ("inizia dal dominante, poi alterna"). `nota_posizionale`
  ricorda che il piano copre solo i temi tattici allenabili. Ogni voce ha un pulsante "allenati su
  questo tema" che apre il flusso `temi` col tema giusto (chiude il cerchio diagnosi→azione). Mostrato
  sotto il report nella sezione carenze.
- **Tappa D — Snapshot nel tempo (anticipo del punto 4), ANTI-DILUIZIONE.** Principio fondante: il
  profilo cumulativo **diluisce** il miglioramento (100 partite nuove su 3300 spostano i tassi in modo
  impercettibile anche con grandi progressi). Quindi il confronto onesto è **profilo delle SOLE partite
  nuove vs lo snapshot storico precedente**, MAI cumulativo vs cumulativo. `data/storico_profili.json`
  conserva gli snapshot; rilevazione **pigra** (confronto dei file in `data/categorie` con quelli
  registrati); `ml/profilo.py` esteso con `solo_file` per profilare un sottoinsieme. **Guardrail del
  rumore**: sotto 50 partite nuove (~1650 mosse) il confronto è marcato "indicativo, non conclusivo"
  (euristica dichiarata). Frontend: blocco **"📈 Stai migliorando?"** con stato-vuoto onesto finché non
  ci sono partite nuove, poi `storico → recente` con frecce; le voci del piano mostrano la tendenza.
  Tutto **di sola lettura** rispetto all'allenamento (non-interferenza con flussi/adattività).
- **Test**: 89 verdi (incl. il **test anti-diluizione**: il tasso recente riflette solo le partite
  nuove, non il cumulativo diluito) + i test di `ml/profilo.py` su `solo_file`. Verificato dal vivo.

> Restano come raffinamenti futuri (NON fatti): il **tasso-su-occasioni** (denominatore vero per
> tema, vicino al punto 5); il **piano dinamico pieno** (ricalibrare i pesi sulle partite recenti,
> non solo annotare la tendenza) — naturale completamento quando il **punto 4** sarà fatto per intero.

### 3. Coaching visivo degli errori ✅ FATTO (base)
**Difficoltà: media (frontend).** Quando si sbaglia un puzzle (3 tentativi esauriti), una **freccia
verde** (chessground `drawable/shapes`, nativa) mostra la mossa giusta dalla casa di partenza a quella
d'arrivo, e il testo mostra la mossa in **notazione SAN leggibile** (helper `uciToSan`, fallback UCI).
Pulizia delle frecce al puzzle successivo (no residui). Per i puzzle multi-mossa mostra la PRIMA mossa.
> Raffinamenti futuri (NON fatti): **freccia rossa** della mia mossa sbagliata accanto alla verde
> ("hai giocato questa, dovevi giocare quella"); **replay passo-passo** della sequenza per i multi-mossa.

### 4. Confronto "prima vs dopo" (verifica dei progressi) ✅ FATTO (sostanza)
**Difficoltà: media.** Realizzato in gran parte già con la **Tappa D del punto 2** (snapshot del profilo
nel tempo, confronto anti-diluizione "partite nuove vs storico", guardrail del rumore, blocco
"📈 Stai migliorando?") + il **grafico "📉 Evoluzione nel tempo"** (linee per tema/fase sui tassi DEI
PERIODI, non cumulativi — anti-diluizione; stato-vuoto onesto finché non ci sono ≥2 snapshot).
Endpoint `/storico-profili`. Tutto si popola man mano che si giocano e ricaricano partite nuove.
> Raffinamenti futuri (NON fatti): **piano dinamico pieno** (ricalibrare i PESI del piano sulle partite
> recenti, non solo annotare la tendenza).

### 5. Diagnosi profonde e contestuali 🔶 AVVIATO (1 diagnosi fatta; il resto è il muro)
**Difficoltà: ALTA (il muro — alcune quasi-ricerca).** Va affrontato DIAGNOSI PER DIAGNOSI.
- **"Non converte il vantaggio"** ✅ **FATTA** (diagnosi-consapevolezza, sola lettura, niente puzzle).
  `ml/converti_vantaggio.py` + endpoint `/diagnosi-conversione` + blocco "🎯 Conversione del vantaggio"
  in "🩺 Le mie carenze". Misura le partite dove raggiungo un vantaggio e non lo converto (patta/sconfitta),
  distinguendo **crollo** (un singolo errore ≥300cp — già coperto dal profilo errori) da **erosione**
  (calo graduale SENZA un errore singolo — il pattern che gli altri strumenti NON vedono). Filtri di
  onestà decisi sui dati reali: **bullet escluso** (lì si perde a tempo, non per tecnica) e **tetto al
  picco +2÷+6** (sotto non è vantaggio chiaro; sopra +6 è matto facile, non tecnica di conversione).
  Risultato pulito: da 388 "erosioni" grezze a **56 vere** (il percorso di filtraggio è esemplare —
  ogni filtro ha ridotto il numero ma aumentato la verità). La diagnosi MOSTRA il pattern e le partite
  da rivedere; NON genera puzzle (l'erosione è tecnica di conversione — semplificare, non rischiare,
  migliorare i pezzi — non una mossa-soluzione validabile). 29 test modulo + endpoint.
- **"Sbaglia in posizioni chiuse/aperte"** ❌ NON FATTA — DIFFICILE (il muro vero). Richiede di
  classificare la natura posizionale (struttura dei pedoni), concetto non geometrico.
- **"Combinazioni"** e altri concetti strategici: da valutare caso per caso.
Meglio poche diagnosi VERE e oneste che tante superficiali. Le diagnosi posizionali restano aperte,
da affrontare solo se fattibili senza grande sforzo (e, se non lo sono, dire onestamente "non si fa").

---

## Step successivo (dopo i sei pezzi)

### Studio delle aperture
Aggiungere progressivamente lo studio di **tutte le aperture**. Capitolo ampio e a sé,
da progettare quando i sei pezzi saranno completati.

---

## Miglioramenti del sistema personale (raccolti dopo l'uso reale)

> Richieste emerse usando il sistema. NON sono i sei pezzi del coach: sono rifiniture e
> nuove capacità. Sono raggruppate per **natura** (rifinitura / coaching / motore), così è
> chiaro cosa è veloce e cosa richiede pensiero. Diverse si **sovrappongono col punto 2**
> (report delle carenze): conviene affrontarle insieme a quello.
> Vale per tutte il principio guida del progetto: **onestà sopra l'apparenza** — niente
> numeri che sembrano precisi ma sono arbitrari.

> **STATO (aggiornato a fine sessione R/C/T):**
> - **Gruppo R: COMPLETO ✅** — R1 (allargamento simmetrico pesca temi + messaggio veritiero),
>   R2 (era già corretto), R3 (grafici non-ingannevoli, nota 85%), R4 (schermate separate per flusso).
> - **C1: ✅** interlacciamento blocchi del Piano (no più temi ripetuti di fila). C2/C3 in parte
>   coperti dal punto 2; resta pesare la rotazione per priorità (Livello 2).
> - **T3: ✅** scomposizione del non_tattico (sola misurazione). **FIX CLASSIFICAZIONE ✅**: i tipi
>   tattici ora si calcolano sulla BEST move (tattica mancata), concettualmente corretto ma effetto
>   numerico ~nullo. **T2: avviato e FERMATO** — lo scacco di scoperta recupera solo ~6 errori;
>   conclusione onesta: il margine è posizionale, non tattico. **T1: non fatto** (minore).
> - Dettagli e numeri nello "Stato attuale" in fondo e in `docs/DA_FARE.md`.

### Gruppo R — Rifinitura di cose già esistenti (difficoltà: bassa)

**R1. Continuità quando un tema libero si esaurisce.**
Nel flusso `temi`, quando finiscono i puzzle nuovi della fascia per quel tema, oggi si
arriva a "esaurito". Si vuole invece poter **proseguire**: o salendo di difficoltà, o
continuando con altri puzzle utili guidati dall'adattività. NOTA: nel flusso `errori` questo
è già risolto (rinforzo Lichess marcato + allargamento fascia); qui si tratta di portare la
stessa logica — o una scelta esplicita dell'utente "continua / cambia tema" — anche al
flusso `temi`. Riusa `_pesca_allargando`.

**R2. Percentuale "tema migliore/peggiore" basata sul primo colpo.**
La % del tema migliore/peggiore (flusso `temi` e ovunque compaia) deve essere
**risolti-al-primo-colpo / totale-tentati** su quel tema — coerente con la definizione di
"successo" del resto del sistema (il primo colpo). Da verificare che `_riepilogo_progressi`
e le statistiche-per-tema usino già questa formula; se no, correggere.

**R3. Grafici dei progressi più chiari.**
Rendere leggibili i due grafici esistenti: **"fascia Elo nel tempo"** e **"% di successo al
primo colpo nel tempo"**. Migliorare assi, etichette, titoli e una breve legenda che spiega
cosa significano (es. perché la % tende all'85% per via dell'adattività, e che il vero
segnale di crescita è la fascia Elo che sale). È lavoro di presentazione, non di calcolo.

**R4. Separazione ESTETICA dei flussi (schermate distinte).**
Ogni flusso deve avere la **propria schermata** coi soli dati pertinenti. Nel flusso `piano`
NON si devono vedere i pulsanti dei temi liberi; nel flusso `temi` compaiono i temi; nel
flusso `errori` i suoi badge. La separazione logica esiste già (punto 1); questa è la sua
resa visiva. Lavoro di frontend.

### Gruppo C — Coaching intelligente (difficoltà: media; lega col punto 2)

**C1. Tema più definito e a rotazione nel flusso `piano`.**
Oggi il piano serve blocchi da `PUZZLE_PER_BLOCCO = 30` sullo stesso tema → si fanno ~30
puzzle di fila sullo stesso motivo senza accorgersi del cambio. Si vuole: (a) **mostrare
chiaramente che tipo di puzzle si sta facendo** (etichetta del tema/motivo visibile); (b)
far **ruotare il tema ogni tot puzzle**, dove l'avanzamento al tema successivo dipende da
**quanti puzzle si risolvono al primo colpo** (non dal totale tentati).
> DECISIONE APERTA: ogni quanti puzzle ruotare? E la regola d'avanzamento è "passa al tema
> dopo N risolti al primo colpo" oppure "dopo N tentati"? Sono regole diverse — decidere sui
> numeri reali (quanti puzzle servono perché la rotazione sia utile senza essere dispersiva).
> Probabile riduzione di `PUZZLE_PER_BLOCCO` o introduzione di una soglia di "padronanza"
> del tema prima di passare oltre.

**C2. Consiglio sui temi liberi in base alle carenze.**
Il sistema, leggendo il profilo di debolezze (che già calcola), **suggerisce su quali temi
liberi concentrarsi**. È il ponte tra il profilo automatico e la modalità a temi liberi.

**C3. Piano di studio personalizzato, schematizzato, prima dell'allenamento.**
Prima di iniziare, il sistema **dichiara le carenze** e propone un **piano a punti** (come un
piano di studio): quali temi liberi affrontare, **quanto tempo dedicare a ciascuno**, e
**come variare nel tempo** la rotazione dei temi.
> DECISIONE APERTA (cruciale per l'onestà): su quale base si calcola il "tempo consigliato"
> per tema? Deve derivare da un dato reale — es. frequenza dell'errore nel profilo, o tasso
> di fallimento sul tema — NON da un numero inventato che sembra preciso. Meglio un consiglio
> ruvido ma giustificato ("ci sbagli spesso → dedicaci di più") che minuti finti. C2 e C3
> sono di fatto la parte "azionabile" del **punto 2** (report carenze): farli insieme.

### Gruppo T — Trasparenza e motore (difficoltà: variabile)

**T1. Disclaimer alla prima partita (onesto ma non manualistico).**
Alla prima volta che si gioca, mostrare un breve disclaimer: su **quali statistiche** si basa
il sistema e **che** la difficoltà si adatta per stimare i progressi. Tono divulgativo, non
le formule.
> NOTA ONESTA (da tenere a mente): l'obiettivo dichiarato è anche "non far copiare il
> sistema". Va detto chiaramente che la segretezza lato client è debole per natura (chiunque
> può ispezionare le chiamate o, se il codice è pubblico, leggerlo). Un disclaimer vago dà
> l'*impressione* di proteggere senza proteggere davvero. La protezione reale sta nella
> licenza e nel fatto che i DATI (le partite) sono dell'utente — non nell'oscurità
> dell'algoritmo. Quindi: scrivere il disclaimer per **informare onestamente l'utente**, non
> illudersi che difenda la proprietà intellettuale. Mostrare una sola volta (flag persistente
> "disclaimer_visto").

**T2. Nuovi tipi tattici riconosciuti dal motore.**
Ampliare i motivi tattici che il sistema sa riconoscere e su cui valuta gli errori (oggi il
profilo automatico usa: pezzo_in_presa, forchetta, inchiodatura, infilata). Aggiungerne altri
(es. deviazione, attrazione, scoperta, intermedia/zwischenzug, sovraccarico, attacco doppio…)
estendendo `ml/tattica.py`. Beneficio diretto anche sui **puzzle-errore** (punto 6): più temi
riconosciuti → errori meglio etichettati → si potrebbero pescare rinforzi Lichess davvero
"simili" al tema dell'errore, non solo della stessa fascia.
> NOTA: ogni nuovo tipo tattico va riconosciuto in modo VERO (validabile), non a regola
> approssimativa. Aggiungere i temi uno per uno, ciascuno con test, come fatto finora.

**T3. Capire cosa c'è davvero nel "non tattico" (38.5%).**
Il report delle carenze (punto 2) mostra che il **38.5% degli errori gravi** finisce in
`non_tattico`. Ma "non tattico" è una categoria-RESIDUO: ci finisce tutto ciò che
`tattica.py` non riconosce, NON una famiglia omogenea di errori posizionali. Primo passo
(LIVELLO 1, fattibile, l'unico da fare ora): **scomporre quel 38.5%** per capire cosa
contiene davvero, invece di trattarlo come un blocco unico. Misure possibili senza grande
sforzo: per ogni errore non-tattico, qual era la natura della mossa migliore (cattura?
spinta di pedone? mossa di pezzo "tranquilla"?), in che fase, con che entità di perdita
(piccola/grande). Solo CONTEGGIO e CLASSIFICAZIONE grezza — niente puzzle ancora.
Obiettivo: scoprire la composizione, perché probabilmente si divide in tre parti:
- **Tattiche non ancora riconosciute** → vanno spostate aggiungendo tipi tattici (cfr. **T2**:
  più riconoscitori → questa fetta si svuota in favore di etichette vere).
- **Posizionale CON soluzione netta** (es. mossa che perde materiale lentamente, tecnica di
  finale): è allenabile come i tattici, perché ha una mossa migliore dimostrabile da Stockfish
  (gap netto) → il filtro di unicità del **punto 6** la terrebbe automaticamente come puzzle,
  scartando il resto. Questo è il LIVELLO 2, da valutare DOPO aver visto la composizione.
- **Posizionale PURO senza mossa netta** (idee strategiche: struttura, casa debole, pezzo
  passivo): qui i puzzle "trova la mossa" NON funzionano (più mosse buone, differenze di
  sfumatura) → è il **muro del punto 5**, richiede un approccio diverso (principi, partite
  modello), concettualmente più difficile. LIVELLO 3, non ora.
> ONESTÀ: non tutto il 38.5% è allenabile coi puzzle, e fingere il contrario sarebbe
> apparenza. I livelli 2 e 3 dipendono da COSA emerge dal livello 1 — non si progettano al
> buio. Si decide la composizione prima, poi come allenare ciascuna parte (o ammettere che
> una parte non è allenabile coi puzzle).

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

## Stato attuale (Fase 4 completa + TUTTI E SEI i pezzi del coach toccati)

Funziona già end-to-end: analisi partite, profilo debolezze, piano automatico, scacchiera
giocabile, difficoltà adattiva con gestione esaurimento, persistenza tra sessioni, 24 temi
categorizzati, statistiche e grafici dei progressi. Suite di test ampia, CI verde.

I sei pezzi del coach (ordine 1 → 6 → 2 → 3 → 4 → 5):
- **Punto 1** ✅ flussi separati (`piano`/`temi`/`errori`).
- **Punto 6** ✅ puzzle dai propri errori, validati Stockfish, sequenze multi-mossa, rinforzo Lichess.
- **Punto 2** ✅ report carenze + tassi + piano di studio (pesi relativi) + snapshot anti-diluizione.
- **Punto 3** ✅ (base) coaching visivo: freccia verde sulla soluzione + SAN leggibile.
- **Punto 4** ✅ (sostanza) confronto prima/dopo: Tappa D + grafico evoluzione (delta, non cumulativi).
- **Punto 5** 🔶 AVVIATO: diagnosi "non converti il vantaggio" fatta (56 erosioni vere, no bullet,
  picco +2÷+6); le diagnosi posizionali restano il muro, aperte.

Raffinamenti futuri annotati (non urgenti): freccia rossa dell'errore (p.3), piano dinamico pieno
(p.4), tasso-su-occasioni (p.2), diagnosi posizionali (p.5, il muro).

**Miglioramenti R/C/T (sessione successiva):**
- Gruppo R COMPLETO ✅ (R1 allargamento simmetrico pesca temi + messaggio veritiero; R2 era già
  corretto; R3 grafici non-ingannevoli con nota 85%; R4 schermate separate per flusso con scacchiera
  condivisa pulita al cambio).
- C1 ✅ interlacciamento blocchi del Piano (mini-blocchi da 5, niente più temi ripetuti di fila).
- T3 ✅ scomposizione del non_tattico. FIX CLASSIFICAZIONE ✅ (tipo tattico dalla best move = tattica
  mancata; concettualmente giusto, effetto numerico ~nullo). T2 avviato e FERMATO (scacco di scoperta
  recupera ~6 errori; il resto è posizionale). T1 non fatto.
- **Lezione chiave della sessione:** il non_tattico (~45% degli errori gravi non-bullet) è per ~75%
  POSIZIONALE puro. Non c'è una riserva di tattiche nascoste da allenare: il margine di crescita vero
  è posizionale (il "muro" del punto 5). T3 ha anche insegnato a verificare le misure prima di
  fidarsene (un suo bug iniziale aveva fatto credere a un recupero di ~1456 tattiche inesistente).

Possibili prossimi passi (nessuno urgente, sistema completo e coerente):
- Raffinamenti dei pezzi del coach (freccia rossa, piano dinamico, tasso-su-occasioni).
- C1-Livello2 (pesare la rotazione del Piano per priorità), T1 (disclaimer).
- Le diagnosi POSIZIONALI del punto 5 (il muro vero) — coerente con la lezione che il margine è lì.
- Fase 5 multi-utente (grande salto: account, hosting, DB — altro progetto).
- ATTENZIONE snapshot: il fix classificazione ha cambiato i tipi del profilo; il prossimo confronto
  Tappa D potrebbe segnalare un "cambiamento" enorme che è solo la riclassificazione, non gioco reale.
  Valutare un reset della baseline degli snapshot.
