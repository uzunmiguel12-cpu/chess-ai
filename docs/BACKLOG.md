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
- [ ] Aperture: dataset ECO (nomi <-> sequenze di mosse) scaricato e caricabile
- [ ] Aperture: query al Lichess Opening Explorer per posizione, filtrata per fascia Elo (con cache locale)
- [ ] Aperture: questionario iniziale (fascia Elo, obiettivo, minuti al giorno)
- [ ] Aperture: motore di consiglio (da quali aperture partire; "semplicita'" = ramificazione dai dati Explorer)
- [ ] Aperture: quarto flusso indipendente 'aperture' con studio passo-passo (linee reali + varianti + statistiche)
- [ ] Aperture: puzzle d'apertura (prosegui dalla mossa N; risposta corretta = mossa da libro dell'Explorer alla fascia)
- [ ] Aperture v2: coach LLM narratore VINCOLATO ai dati reali (mai mosse inventate); provider LLM da decidere

## Modulo Principi (studio posizionale - copre gli 'errori posizionali' non tattici)
- [ ] Principi: sezione dedicata nel sito (nav + struttura a temi consultabile)
- [ ] Principi: struttura dei temi (centro, sviluppo, sicurezza del re, struttura pedonale, attivita' dei pezzi, spazio, case deboli, formulare un piano)
- [ ] Principi: contenuti teorici per tema (spiegazione onesta = teoria consolidata, niente invenzioni; esempi e diagrammi)
- [ ] Principi: mini-diagrammi/posizioni illustrative per ogni principio (scacchiera statica)
- [ ] Principi: collegamento con le Carenze (consiglia i temi dai tuoi errori posizionali 'non_tattico')
- [ ] Principi: quiz di comprensione per tema (verifica la teoria posizionale, non la tattica)
- [ ] Principi: approfondire OGNI principio come mini-lezione (definizione, come riconoscerlo, come sfruttarlo o difendersi, esempi con diagrammi, errore comune da evitare)
- [ ] Principi: ampliare il numero di principi/card per un'ampia gamma di studio (piu' temi e piu' voci per tema)
- [ ] Principi v2: coach che spiega il principio applicato alla posizione (LLM locale, vincolato ai dati)

## Fase 5 - multi-utente (grande, futura)
- [ ] Fase 5: sistema di account e login sicuro
- [ ] Fase 5: database utenti con dati isolati
- [ ] Fase 5: hosting di un server sempre acceso
- [ ] Fase 5: analisi Stockfish lato server (coda di lavori)
- [ ] Fase 5: migrazione dello stato da JSON a database
- [ ] Fase 5: decisione sulla licenza chessground GPL-3.0 per un servizio pubblico
