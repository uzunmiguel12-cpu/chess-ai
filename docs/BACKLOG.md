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
- [ ] Freccia rossa della mossa sbagliata accanto alla verde (coach visivo, punto 3)
- [ ] Replay passo-passo delle sequenze multi-mossa (punto 3)
- [ ] Piano dinamico pieno: ricalibrare i pesi sulle partite recenti (punto 4)
- [ ] Tasso-su-occasioni come denominatore per tema (punto 2)
- [ ] C1-Livello2: pesare la rotazione del Piano per priorita'

## Trasparenza / motore
- [ ] Disclaimer alla prima partita (onesto, non manualistico) - T1
- [ ] Reset della baseline degli snapshot dopo il fix classificazione

## Diagnosi (punto 5)
- [ ] Valutare la tecnica di finale torre+re come diagnosi allenabile

## Infrastruttura / qualita'
- [x] Estendere la CI a ml/ api/ rag/ (oggi testa solo engine/)
- [ ] Rimuovere gli .svg di esempio residui in frontend/src/assets

## Fase 5 - multi-utente (grande, futura)
- [ ] Fase 5: sistema di account e login sicuro
- [ ] Fase 5: database utenti con dati isolati
- [ ] Fase 5: hosting di un server sempre acceso
- [ ] Fase 5: analisi Stockfish lato server (coda di lavori)
- [ ] Fase 5: migrazione dello stato da JSON a database
- [ ] Fase 5: decisione sulla licenza chessground GPL-3.0 per un servizio pubblico
