# Come avviare il progetto da zero

Questa guida permette di prendere il progetto chess-ai e farlo funzionare sul
proprio computer partendo da zero. Se seguendo solo questi passi il progetto
parte, le fondamenta sono a posto.

Le istruzioni sono per Windows. Su Mac/Linux i comandi sono quasi identici;
le differenze sono segnalate dove servono.

---

## Prerequisiti

Servono due programmi installati sul computer. Per verificare se ci sono,
aprire il Prompt dei comandi (cmd) e digitare:

```
python --version
```
Deve rispondere con una versione 3.x (es. `Python 3.12.10`). Se manca:
scaricarlo da https://www.python.org

```
node --version
```
Deve rispondere con una versione (es. `v20.20.2`). Se manca:
scaricarlo da https://nodejs.org

---

## 1. Clonare il progetto

"Clonare" significa scaricare una copia del progetto da GitHub. Spostarsi
dove si vuole il progetto (es. il Desktop) e clonare:

```
cd Desktop
git clone https://github.com/uzunmiguel12-cpu/chess-ai.git
cd chess-ai
```

Ora si è dentro la cartella del progetto.

---

## 2. Preparare il backend Python

Creare l'ambiente virtuale (la "bolla" isolata delle librerie Python):

```
python -m venv .venv
```

Attivarlo (su Windows):

```
.venv\Scripts\activate
```
Su Mac/Linux invece: `source .venv/bin/activate`

A conferma dell'attivazione, a inizio riga compare `(.venv)`.

Installare le dipendenze Python dalla lista:

```
pip install -r requirements.txt
```

Verificare che python-chess sia a posto:

```
python -c "import chess; print(chess.__version__)"
```
Deve stampare un numero di versione.

---

## 3. Preparare il frontend

Entrare nella cartella del frontend e installare le sue dipendenze:

```
cd frontend
npm install
```

Avviare il frontend:

```
npm run dev
```

Comparira' un indirizzo, di solito `http://localhost:5173/`. Aprirlo nel
browser per vedere il frontend. Per fermare il server: `Ctrl + C` nella
finestra dove gira.

---

## 4. Struttura del progetto

| Cartella     | Contenuto                                              |
|--------------|--------------------------------------------------------|
| `frontend/`  | Interfaccia React (Vite)                               |
| `engine/`    | Dialogo con Stockfish (Fase 2)                         |
| `ml/`        | Classificazione errori (Fase 3)                        |
| `rag/`       | Knowledge base e spiegazioni (Fase 4)                  |
| `api/`       | Orchestrazione della pipeline                          |
| `docs/`      | Documentazione (contratti dati, logging)               |
| `contracts/` | Esempi JSON dei contratti dati                          |

---

## Note utili

- Ricordarsi di attivare l'ambiente `(.venv)` ogni volta che si apre una
  nuova finestra per lavorare sul backend Python.
- Le cartelle `.venv` e `node_modules` non sono su GitHub: si rigenerano dai
  passi 2 e 3. E' normale e voluto.
- Per salvare il proprio lavoro su GitHub: `git add .` poi
  `git commit -m "messaggio"` poi `git push`.
