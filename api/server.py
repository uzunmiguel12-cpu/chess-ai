"""
Backend FastAPI (Fase 4 / api) - serve i puzzle del piano di allenamento.

Espone il "cervello" del sistema via web: il browser puo' chiedere il prossimo
puzzle da fare, e il server lo pesca dal piano di allenamento costruito a partire
dal profilo del giocatore.

Endpoint principali:
  GET /                  -> pagina di prova (testo)
  GET /prossimo-puzzle   -> il prossimo puzzle del piano (JSON)
  GET /stato             -> info sulla sessione (quanti puzzle, a che punto)

Avvio (dalla cartella api, con ambiente attivo):
    uvicorn server:app --reload

Poi nel browser: http://localhost:8000/prossimo-puzzle
"""

import os
import sys
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Il piano vive in rag/, il profilo in ml/: aggiungiamo i percorsi per importarli.
_QUI = os.path.dirname(os.path.abspath(__file__))
_RAG = os.path.join(_QUI, "..", "rag")
_ML = os.path.join(_QUI, "..", "ml")
for p in (_RAG, _ML):
    if p not in sys.path:
        sys.path.insert(0, p)

from piano import costruisci_piano  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("api")

# --- Configurazione (per ora fissa; un domani vera gestione utenti) ---
GIOCATORE = os.environ.get("CHESS_PLAYER", "MigueL_uz")
PERCORSO_DB = os.path.join(_QUI, "..", "data", "puzzle.db")
ELO_MIN = int(os.environ.get("CHESS_ELO_MIN", "1050"))
ELO_MAX = int(os.environ.get("CHESS_ELO_MAX", "1250"))

app = FastAPI(title="Chess-AI - Allenamento puzzle")

# CORS: permette al frontend (su un'altra porta, es. 5173) di interrogare
# questo backend. Senza, il browser bloccherebbe le richieste per sicurezza.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stato in memoria della sessione: il piano e quanti puzzle abbiamo servito.
_sessione = {
    "piano": None,
    "coda": [],     # lista piatta di puzzle da servire, in ordine di piano
    "serviti": 0,
}


def _prepara_sessione():
    """Costruisce il piano e appiattisce i puzzle in una coda ordinata."""
    piano = costruisci_piano(GIOCATORE, PERCORSO_DB, elo_min=ELO_MIN, elo_max=ELO_MAX)
    if piano is None:
        return False
    coda = []
    for blocco in piano["blocchi"]:
        for p in blocco["puzzle"]:
            # arricchiamo ogni puzzle con il contesto del blocco (perche' lo fai)
            coda.append({
                "id": p["id"],
                "fen": p["fen"],
                "moves": p["moves"],
                "rating": p["rating"],
                "themes": p["themes"],
                "motivo_allenamento": blocco["motivo"],
                "fase_allenamento": blocco["fase"],
            })
    _sessione["piano"] = piano
    _sessione["coda"] = coda
    _sessione["serviti"] = 0
    logger.info("Sessione pronta: %d puzzle in coda per %s", len(coda), GIOCATORE)
    return True


@app.get("/")
def home():
    return {
        "messaggio": "Chess-AI backend attivo.",
        "prova": "Vai su /prossimo-puzzle per ricevere un puzzle.",
        "giocatore": GIOCATORE,
    }


@app.get("/stato")
def stato():
    if _sessione["piano"] is None:
        _prepara_sessione()
    return {
        "giocatore": GIOCATORE,
        "puzzle_totali": len(_sessione["coda"]),
        "puzzle_serviti": _sessione["serviti"],
        "rimanenti": len(_sessione["coda"]) - _sessione["serviti"],
    }


@app.get("/prossimo-puzzle")
def prossimo_puzzle():
    # Prepara la sessione alla prima richiesta.
    if _sessione["piano"] is None:
        if not _prepara_sessione():
            return JSONResponse(
                status_code=404,
                content={"errore": f"Nessun piano per {GIOCATORE}. "
                                   "Hai analizzato e arricchito le partite?"},
            )

    idx = _sessione["serviti"]
    if idx >= len(_sessione["coda"]):
        return {"fine": True, "messaggio": "Hai completato tutti i puzzle del piano!"}

    puzzle = _sessione["coda"][idx]
    _sessione["serviti"] += 1
    return {
        "fine": False,
        "numero": idx + 1,
        "totale": len(_sessione["coda"]),
        "puzzle": puzzle,
    }
