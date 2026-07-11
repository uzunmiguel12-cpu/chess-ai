# chess-ai — Architettura Fase 5 (multi-utente) — proposta

> Documento di **system design** per le issue #13-#18. Bersaglio scelto: **prodotto pubblico
> scalabile**, budget iniziale **€5-15/mese**. Serve a decidere *come* costruirlo e *quali
> compromessi* accettare — non a scrivere codice. Principio del progetto: **sostanza non
> apparenza**. Numeri marcati **[DATO]** (misurato/dai doc) o **[STIMA]** (ipotesi dichiarata).
> Le "Decisioni aperte" in fondo le decidi tu. NB: sulla licenza NON sono un avvocato — è una
> valutazione tecnica, da confermare con chi di dovere.

---

## 0. La tensione che governa tutto

Vuoi **scala pubblica** ma partendo con **€5-15/mese**. Sono conciliabili solo se il costo
più pesante non grava sul tuo server. Quel costo è l'**analisi Stockfish**: ~3,5 h per ~3000
partite **[DATO]**. Moltiplicato per N utenti, su un server piccolo, è insostenibile.

**La decisione che sblocca tutto: l'analisi gira nel BROWSER dell'utente (Stockfish WASM),
non sul tuo server.** Ogni utente usa la propria CPU → costo di compute per te ≈ **€0**, e
scala all'infinito (più utenti = più CPU, ma non tue). È esattamente il motivo per cui Lichess
fa l'analisi lato client. Cambia il senso della #14: da "Stockfish lato server (coda)" a
"Stockfish nel client, il server orchestra e salva i risultati".

Con questa mossa, "pubblico + lean" diventa realistico. Il resto dell'architettura segue.

---

## 1. Requisiti

**Funzionali (multi-utente):** registrazione/login; ogni utente coi propri dati isolati
(partite, profilo, stato, visti); caricamento e analisi delle proprie partite; l'esperienza
attuale (piano/temi/errori + carenze) per-utente; interfaccia web pubblica.

**Non funzionali:** **costo lean** (€5-15/mese all'inizio); **scalabile** senza riscrivere
tutto; sicurezza (password, isolamento dati); **onestà** delle metriche invariata; non
buttare il lavoro fatto (il motore di diagnosi in `ml/`, `rag/`, `api/` si riusa).

**Vincoli:** oggi è single-user con stato su **file JSON** [DATO]; `puzzle.db` è ~1,5 GB
[DATO] (DB condiviso in sola lettura); frontend usa **chessground GPL-3.0** [DATO].

---

## 2. Architettura consigliata (lean-ma-scalabile)

```
   Browser utente                         Server (piccolo)                Servizi gestiti
  ┌───────────────────┐   HTTPS   ┌──────────────────────────┐        ┌──────────────────┐
  │ Frontend (Vite)   │──────────▶│ API FastAPI (la tua)     │───────▶│ Postgres gestito │
  │  - scacchiera     │           │  - auth (sessioni/JWT)   │        │  (utenti, stato, │
  │  - Stockfish WASM │◀──────────│  - profilo/piano/puzzle  │        │   profili)       │
  │    (ANALISI qui!) │  risultati│  - riusa ml/ rag/ api/   │        └──────────────────┘
  └───────────────────┘  analisi  │  - puzzle.db (read-only) │
                                  └──────────────────────────┘
```

Il **compute pesante** (Stockfish) sta nel browser; il tuo server fa solo orchestrazione +
lettura/scrittura dati. Il `puzzle.db` (1,5 GB, statico) sta sul disco del server piccolo.

---

## 3. Decisioni per componente (mappate su #13-#18)

### #14 — Analisi Stockfish: **client WASM** (consigliato) vs server
- **Client (Stockfish WASM)** [consigliato]: analisi nella CPU dell'utente. Costo server ≈ €0,
  scala all'infinito. Contro: più lenta della macchina dell'utente, va gestita la progress-bar
  e il salvataggio incrementale dei risultati al server. È la scelta che rende possibile il lean.
- **Server con coda** (Redis/RQ o simili): più controllo, ma **costa compute** e a €5-15/mese
  regge pochissimi utenti. Rimandabile a quando avrai entrate.

### #16 — Database utenti: **Postgres dall'inizio** (consigliato) vs SQLite
- **Postgres** (gestito, free/low tier: Neon/Supabase hanno free tier) [consigliato]: eviti la
  migrazione dolorosa SQLite→Postgres dopo. Isolamento dati per utente con una colonna `user_id`.
  Costo iniziale ~€0 (free tier) → cresce con l'uso [STIMA].
- **SQLite**: semplicissimo per iniziare, ma monofile/monoscrittore → ti blocca sulla scala.
  Sconsigliato dato il bersaglio pubblico.
- Nota: `puzzle.db` resta **SQLite in sola lettura** (è un asset statico condiviso, non dati utente).

### #17 — Migrazione stato JSON → DB
- Oggi `stato_sessione.json` (tre flussi + visti + snapshot) è single-user. Diventa tabelle
  Postgres chiavate su `user_id`. Il codice attuale legge/scrive JSON: va introdotto uno strato
  di persistenza (repository) che oggi usa il DB. Lavoro contenuto ma trasversale. I contratti
  dati restano gli stessi (i doc in `contracts/` aiutano).

### #13 — Account e login
- **Email + password** (hash **bcrypt/argon2**, mai in chiaro) + sessioni o JWT. Semplice, nessun
  costo. Oppure **OAuth** (Google, o **Lichess/Chess.com** che è tematicamente perfetto) per
  togliere la gestione password. Un servizio gestito (es. Supabase Auth) fa da scorciatoia se non
  vuoi scrivere l'auth a mano. [Decisione tua: fatto-in-casa vs gestito.]

### #15 — Hosting (dentro €5-15/mese)
- **PaaS** (Fly.io / Railway / Render): free/hobby tier per iniziare, deploy semplice, si scala
  pagando. + **Postgres gestito** (free tier). Totale iniziale ~**€0-10/mese** [STIMA].
- **VPS piccolo** (es. Hetzner ~€4/mese [STIMA]): più controllo, ci sta app + puzzle.db 1,5 GB +
  Postgres locale; più manutenzione a mano.
- Entrambi rientrano nel budget. PaaS = meno lavoro sistemistico; VPS = più economico/controllo.

### #18 — Licenza chessground (GPL-3.0)
- **Problema reale:** un servizio web **serve il JS al browser** = distribuzione. Con chessground
  GPL-3.0 linkato, il tuo frontend andrebbe rilasciato sotto GPL (copyleft). [Valutazione tecnica,
  non legale.]
- Opzioni: **(a) rendere pubblico il frontend sotto GPL** — per un progetto nato per imparare è
  accettabile e anche onesto; **(b) sostituire chessground** con una libreria permissiva (MIT/ISC,
  es. una board-lib con licenza libera) per tenere il codice chiuso; **(c)** consulenza per il caso
  esatto. Da decidere PRIMA di aprire al pubblico, non dopo.

---

## 4. Percorso a tappe (pubblico ma lean)

1. **T0 — Decisioni** (nessun codice): auth fatto-in-casa vs gestito; PaaS vs VPS; licenza (a/b);
   confermare "analisi nel client".
2. **T1 — Persistenza:** introdurre Postgres + lo strato repository; migrare lo stato da JSON a
   tabelle `user_id`. (Ancora single-user in locale, ma su DB.)
3. **T2 — Account:** registrazione/login, isolamento dati per utente.
4. **T3 — Analisi client:** integrare Stockfish WASM nel frontend; il server riceve e salva i
   risultati d'analisi per utente (la pipeline `ml/` gira sui risultati, come oggi).
5. **T4 — Deploy pubblico:** hosting + Postgres gestito + dominio; sistemare la licenza (T0).
6. **T5 — Scala quando serve:** coda server per l'analisi solo se/quando ci saranno entrate;
   caching; monitoraggio.

Ogni tappa è verificabile e non butta il lavoro esistente (il cuore diagnostico si riusa intatto).

---

## 5. Decisioni aperte (le decidi tu)
1. **Auth:** fatto-in-casa (bcrypt+sessioni/JWT) o **gestito** (Supabase Auth / OAuth Lichess)?
2. **Hosting:** PaaS (Fly/Railway/Render) o **VPS** (Hetzner)?
3. **Licenza:** frontend **GPL pubblico** (tieni chessground) o **sostituisci** con lib permissiva?
4. **Conferma** analisi nel client (WASM) invece che sul server?
5. **Modello di sostenibilità** (per quando cresce): gratuito con limiti? freemium? Il tuo vecchio
   interesse per startup/MindDesk può ispirare il modello — ma non serve deciderlo ora.

## 6. Cosa NON ho deciso / da verificare
- I costi sono **[STIMA]** su tier pubblici noti: vanno confermati sui prezzi attuali al momento.
- La licenza è una **valutazione tecnica**, non un parere legale: per un servizio reale, conferma.
- La velocità di Stockfish WASM sul browser dell'utente dipende dalla sua macchina **[STIMA]**:
  più lenta del nativo, ma gratis e scalabile.
