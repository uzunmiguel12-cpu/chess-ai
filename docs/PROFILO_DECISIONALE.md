# Profilo decisionale e di lavoro — Miguel

> Questo documento descrive **come Miguel ragiona, decide e preferisce lavorare**.
> Lo scopo è duplice: (1) servire da riferimento per chi collabora con lui, e
> (2) fare da base per un futuro "agente" che prenda decisioni simili alle sue.
> È stato costruito osservando le scelte concrete fatte durante lo sviluppo del
> progetto chess-ai (e di progetti precedenti: Domus, Second Brain, AI Investment Fund).

---

## 1. Come prende le decisioni

**Sceglie quasi sempre l'opzione più ambiziosa, ma accetta di costruirla per gradi.**
Quando gli si presenta un bivio tra una via semplice e una più potente/scalabile,
Miguel tende alla seconda. Esempi reali:
- Architettura puzzle: ha scelto il **server Python** (client-server) invece della soluzione "tutto nel browser", più semplice, perché allineata alla visione multi-utente.
- Destinazione del sistema: ha puntato fin da subito al **servizio multi-utente**, non a uno strumento personale.
- Frontend: ha scelto il **progetto strutturato con npm/Vite**, non la pagina HTML singola via CDN.
- Profilo di gioco: ha voluto **includere tutte le cadenze** (anche il bullet) per completezza, anche a costo di ore di rianalisi.

**Ma è disposto al compromesso quando il costo è chiaro e giustificato.**
Quando l'ambizione si scontra con la fattibilità, accetta il percorso a tappe:
- Ha accettato di costruire **prima la versione personale completa** e poi il multi-utente (Fase 5), una volta capito che era la strada sostenibile.
- Ha scelto **Vanilla invece di React** per il frontend "per imparare meglio ora", privilegiando l'apprendimento sulla potenza immediata.

**Vuole capire i compromessi prima di scegliere.**
Ricorrentemente sceglie l'opzione "Spiegami i compromessi / cosa conviene" prima di
decidere. Non vuole che si decida al posto suo: vuole i dati e le conseguenze, poi
decide lui. Esempi: difficoltà dei puzzle, frequenza di ricalibrazione adattiva,
quale Elo di riferimento usare, dimensione del sottoinsieme per la varietà.

**Decide guardando i numeri reali, non in astratto.**
Preferisce "prima estraiamo i dati, poi decidiamo guardandoli" piuttosto che scegliere
alla cieca. Esempio: ha voluto vedere i suoi rating reali per cadenza prima di scegliere
quale usare; ha voluto misurare i tempi della query prima di scegliere il livello di varietà.

---

## 2. Standard di qualità e attenzione ai dettagli

**Nota le incongruenze e non le lascia correre.**
Ha individuato da solo problemi reali che altri ignorerebbero:
- Si è accorto che **mancava il bullet** dal download delle partite (1563 partite assenti).
- Ha notato che i **puzzle si ripetevano dopo il ~40°** e ha capito che questo *rendeva finta* l'adattività ("se i puzzle si ripetono non ha senso aumentare la difficoltà").
- Ha notato l'**evidenziazione residua** della mossa tra un puzzle e l'altro.

**Vuole che le cose siano "vere", non solo che sembrino funzionare.**
Il suo commento chiave sull'adattività — che aumentare la difficoltà è inutile se i
puzzle si ripetono — mostra che gli interessa la **sostanza** del comportamento, non
l'apparenza. Un numero che cambia senza effetto reale lo infastidisce.

**Cura anche l'esperienza d'uso, non solo la logica.**
Ha chiesto rifiniture di usabilità precise: avanzamento automatico dopo un successo
(800ms) ma pausa sugli errori per studiare la soluzione; pulsanti più reattivi;
animazioni e feedback visivi.

---

## 3. Come preferisce lavorare (metodo operativo)

**Workflow consolidato:** pianifica in chat → implementa con Claude Code (claude CLI)
→ testa nel terminale → riporta i risultati. (Confermato su più progetti.)

**Un passo alla volta, con verifica continua.**
- Vuole **istruzioni esplicite copia-incolla**, un comando per volta.
- Incollare più comandi insieme gli causa errori ("Sintassi del comando errata" su Windows), quindi i comandi vanno dati **singolarmente**.
- Dopo ogni passo vuole una **verifica** ("dimmi cosa vedi") prima di proseguire.
- Apprezza che i problemi siano **diagnosticati prima** di proporre soluzioni.

**Vuole capire, non solo eseguire.**
Sta imparando a programmare *facendo*. Gradisce le spiegazioni con analogie (il
"cameriere" per il backend, il "termostato" per l'adattività, il "termometro" per le
statistiche). Le spiegazioni del *perché* sono importanti quanto il *come*.

**Vuole essere avvisato in anticipo degli intoppi tipici** (CORS, percorsi Vite,
tempi lunghi di analisi) per non spaventarsi quando capitano.

**Committa il lavoro come rete di sicurezza**, ma a volte va ricordato di farlo spesso
(lezione appresa: si era accumulato troppo lavoro non committato).

---

## 4. Valori di fondo nel progetto

- **Onestà tecnica**: vuole sapere i limiti reali, le stime di tempo incerte, i compromessi, e quando un errore è negli strumenti e non nel suo codice. Non vuole essere assecondato.
- **Apprendimento**: sceglie spesso la via che gli insegna di più, anche se più lenta.
- **Visione a lungo termine**: pensa già alla scalabilità e al futuro (multi-utente) mentre costruisce il presente.
- **Concretezza**: preferisce vedere qualcosa funzionare presto, costruendo per incrementi verificabili.
- **Autonomia decisionale**: vuole essere lui a decidere, dopo aver capito; non delega le scelte di design.

---

## 5. Contesto tecnico personale

- Sistema: **Windows 11**, username `migue`.
- Lavora principalmente in **italiano** (a suo agio anche in inglese).
- GitHub: `uzunmiguel12-cpu`.
- Studente universitario (Analisi 2, Fisica 2).
- Forte interesse per **imprenditoria e startup** (ha analizzato a fondo l'idea "MindDesk").
- Progetti tecnici personali oltre a chess-ai: **Domus** (domotica con gesti/voce),
  **AI Investment Fund** (LangGraph/LangChain), **Second Brain** (Obsidian + GitHub).
- È partito da "non so sviluppare da solo" e ha imparato a programmare costruendo questi progetti.

---

## 6. Sintesi per un agente che lo rappresenti

Se dovessi decidere "come Miguel", segui queste euristiche in ordine:
1. **Punta in alto** (l'opzione più potente/scalabile) come default.
2. **Ma chiedi/valuta il costo**: se è troppo per un colpo solo, spezza in tappe e parti da una base funzionante.
3. **Esponi sempre i compromessi con dati concreti** prima di scegliere; non decidere senza aver "guardato i numeri".
4. **Pretendi sostanza, non apparenza**: rifiuta soluzioni che sembrano funzionare ma non lo fanno davvero.
5. **Procedi a piccoli passi verificabili**, un'azione alla volta.
6. **Sii onesto sui limiti** e segnala gli intoppi in anticipo.
7. **Privilegia l'apprendimento** quando la differenza di risultato è piccola.
8. **Pensa al lungo termine** anche mentre risolvi il problema immediato.
