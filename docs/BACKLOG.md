# chess-ai — Backlog sincronizzabile

> Sorgente ESPLICITA per il sync n8n -> issue GitHub. Regola semplice e verificabile:
> - `- [ ] Titolo`  -> se non esiste gia' una issue aperta con quel titolo, la crea.
> - `- [x] Titolo`  -> se esiste una issue aperta con quel titolo, la chiude.
> Il match e' per TITOLO ESATTO. Il racconto completo (con motivazioni e "no" dimostrati)
> resta in docs/DA_FARE.md e docs/VISIONE_ESTESA.md: qui solo le voci ancora APERTE.
>
> RIVEDI E POTA questa lista: quello che togli non verra' sincronizzato; quello che segni
> [x] verra' chiuso al prossimo giro. I titoli sono anche i titoli delle issue: cambiali
> con cura (cambiare un titolo qui = il sync non ritrova la issue e ne crea una nuova).

## Priorita' alta
- [ ] Verifica server-side finale delle soluzioni (anti-cheat, multi-utente)

## Rifiniture dei pezzi del coach
- [x] Freccia rossa della mossa sbagliata accanto alla verde (coach visivo, punto 3)
- [x] Replay passo-passo delle sequenze multi-mossa (punto 3)
- [x] Piano dinamico pieno: ricalibrare i pesi sulle partite recenti (punto 4)
- [x] Tasso-su-occasioni come denominatore per tema (punto 2)
- [x] C1-Livello2: pesare la rotazione del Piano per priorita'

## Trasparenza / motore
- [x] Disclaimer alla prima partita (onesto, non manualistico) - T1
- [x] Reset della baseline degli snapshot dopo il fix classificazione

## Diagnosi (punto 5)
- [x] Valutare la tecnica di finale torre+re come diagnosi allenabile

## Infrastruttura / qualita'
- [x] Estendere la CI a ml/ api/ rag/ (oggi testa solo engine/)
- [x] Rimuovere gli .svg di esempio residui in frontend/src/assets

## Modulo Aperture (nuovo capitolo) - deciso: fonte = Lichess Explorer + ECO, LLM in v2
- [x] Aperture: dataset ECO (nomi <-> sequenze di mosse) scaricato e caricabile
- [ ] Aperture: query al Lichess Opening Explorer per posizione, filtrata per fascia Elo (con cache locale)
- [x] Aperture: questionario iniziale (fascia Elo, obiettivo, minuti al giorno)
- [x] Aperture: motore di consiglio (da quali aperture partire; "semplicita'" = ramificazione dai dati Explorer)
- [x] Aperture: quarto flusso indipendente 'aperture' con studio passo-passo (linee reali + varianti + statistiche)
- [x] Aperture: puzzle d'apertura (prosegui dalla mossa N; risposta corretta = mossa da libro dell'Explorer alla fascia)
- [x] Aperture v2: coach LLM narratore VINCOLATO ai dati reali (mai mosse inventate); provider LLM da decidere
> Note: consiglio basato su rosa CURATA (~31 aperture) + complessità ECO, non su query live al Lichess
> Explorer (l'unica voce ancora aperta). Coach = Ollama/qwen3:8b precompute → cache `rag/coach_aperture.json`.

## Modulo Principi (studio posizionale - copre gli 'errori posizionali' non tattici)
- [x] Principi: sezione dedicata nel sito (nav + struttura a temi consultabile)
- [x] Principi: struttura dei temi (centro, sviluppo, sicurezza del re, struttura pedonale, attivita' dei pezzi, spazio, case deboli, formulare un piano)
- [x] Principi: contenuti teorici per tema (spiegazione onesta = teoria consolidata, niente invenzioni; esempi e diagrammi)
- [x] Principi: mini-diagrammi/posizioni illustrative per ogni principio (scacchiera statica)
- [x] Principi: collegamento con le Carenze (consiglia i temi dai tuoi errori posizionali 'non_tattico')
- [x] Principi: quiz di comprensione per tema (verifica la teoria posizionale, non la tattica)
- [x] Principi: approfondire OGNI principio come mini-lezione (definizione, come riconoscerlo, come sfruttarlo o difendersi, esempi con diagrammi, errore comune da evitare)
- [x] Principi: ampliare il numero di principi/card per un'ampia gamma di studio (piu' temi e piu' voci per tema)
- [ ] Principi v2: coach che spiega il principio applicato alla posizione (LLM locale, vincolato ai dati)
> Fatto: 12 temi (aggiunti Attacco al re, Motivi tattici, Cambi e semplificazione; Finali ampliati),
> con esempi giocabili + quiz; tutte le posizioni verificate con python-chess. Contenuto statico in
> `frontend/src/data/principi.js`. Resta solo il coach LLM per-posizione (v2).

## Estrazione dati Chess.com (pagina "I miei dati" - frontend pronto, manca il backend)
- [ ] Chess.com: backend che scarica le partite pubbliche via API ufficiale (per nome utente) e le prepara all'analisi
- [ ] Chess.com: collegare la pagina "I miei dati" al backend (avvio import + stato avanzamento + esito)
- [ ] Chess.com: pipeline di analisi automatica delle partite importate (Stockfish -> profilo carenze)

## Impostazioni (sezioni fondamentali del sito)
- [ ] Impostazioni: rendere funzionali Abbonamenti e Account quando ci sara' il backend utenti (Fase 5)
> Fatto in questa fase: 9 sezioni (Profilo, Scacchiera e pezzi, Preferenze allenamento, Accessibilita,
> Dati e privacy, Sistema e connessione, Info e note legali; Abbonamenti/Account = segnaposto onesti).

## Fase 5 - multi-utente (grande, futura)
- [ ] Fase 5: sistema di account e login sicuro
- [ ] Fase 5: database utenti con dati isolati
- [ ] Fase 5: hosting di un server sempre acceso
- [ ] Fase 5: analisi Stockfish lato server (coda di lavori)
- [ ] Fase 5: migrazione dello stato da JSON a database
- [ ] Fase 5: decisione sulla licenza chessground GPL-3.0 per un servizio pubblico
