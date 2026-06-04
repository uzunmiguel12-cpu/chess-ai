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
import json
import logging
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
PERCORSO_STATO = os.path.join(_QUI, "..", "data", "stato_sessione.json")
ELO_MIN = int(os.environ.get("CHESS_ELO_MIN", "1050"))
ELO_MAX = int(os.environ.get("CHESS_ELO_MAX", "1250"))

# --- Parametri della difficolta' adattiva ---
BLOCCO_ADATTIVO = 10     # ogni quanti puzzle ricalibrare
SOGLIA_ALZA = 90.0       # sopra questa % (sul blocco) -> alza la fascia
SOGLIA_ABBASSA = 70.0    # sotto questa % -> abbassa la fascia
PASSO_ELO = 100          # di quanti punti spostare la fascia
PUZZLE_PER_BLOCCO = 30   # quanti puzzle pescare per blocco (varieta')

# Temi disponibili per la scelta libera (nome italiano -> tema Lichess).
TEMI_DISPONIBILI = {
    "forchetta": "fork",
    "inchiodatura": "pin",
    "infilata": "skewer",
    "pezzo_in_presa": "hangingPiece",
    "attacco_di_scoperta": "discoveredAttack",
    "sacrificio": "sacrifice",
    "matto_in_2": "mateIn2",
    "finale_di_torre": "rookEndgame",
}
ELO_MIN_ASSOLUTO = 600   # limiti per non uscire dai puzzle esistenti
ELO_MAX_ASSOLUTO = 2800

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
    # Statistiche di sessione (si azzerano al riavvio del backend).
    "tentati": 0,            # puzzle di cui e' arrivato un esito
    "risolti_primo": 0,      # risolti al primo tentativo (= successo)
    "risolti_secondo": 0,    # risolti al secondo tentativo
    "falliti": 0,            # soluzione mostrata
    # Difficolta' adattiva
    "elo_min": ELO_MIN,      # fascia corrente (cambia con l'adattivita')
    "elo_max": ELO_MAX,
    "blocco_primo": 0,       # risolti al primo nel blocco corrente
    "blocco_conteggio": 0,   # puzzle nel blocco corrente
    "storico_fasce": [],     # traccia i cambi di fascia
    "visti": set(),          # ID dei puzzle gia' serviti (mai riproporli)
    "tema_libero": None,     # se impostato, allenamento focalizzato su un tema Lichess
}

def _salva_stato():
    """
    Salva lo stato persistente (fascia, visti, statistiche) su file JSON.
    Scrittura sicura: scrive su file temporaneo e poi rinomina, cosi' non
    resta mai un file a meta' se qualcosa si interrompe.
    """
    stato = {
        "elo_min": _sessione["elo_min"],
        "elo_max": _sessione["elo_max"],
        "tentati": _sessione["tentati"],
        "risolti_primo": _sessione["risolti_primo"],
        "risolti_secondo": _sessione["risolti_secondo"],
        "falliti": _sessione["falliti"],
        "visti": list(_sessione["visti"]),  # set -> lista per il JSON
        "storico_fasce": _sessione["storico_fasce"],
    }
    try:
        tmp = PERCORSO_STATO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(stato, f)
        os.replace(tmp, PERCORSO_STATO)  # rinomina atomica
    except OSError as e:
        logger.warning("Impossibile salvare lo stato: %s", e)


def _carica_stato():
    """
    Carica lo stato persistente all'avvio, se il file esiste.
    RESTITUISCE True se ha caricato uno stato salvato, False altrimenti.
    """
    if not os.path.exists(PERCORSO_STATO):
        return False
    try:
        with open(PERCORSO_STATO, "r", encoding="utf-8") as f:
            stato = json.load(f)
        _sessione["elo_min"] = stato.get("elo_min", ELO_MIN)
        _sessione["elo_max"] = stato.get("elo_max", ELO_MAX)
        _sessione["tentati"] = stato.get("tentati", 0)
        _sessione["risolti_primo"] = stato.get("risolti_primo", 0)
        _sessione["risolti_secondo"] = stato.get("risolti_secondo", 0)
        _sessione["falliti"] = stato.get("falliti", 0)
        _sessione["visti"] = set(stato.get("visti", []))  # lista -> set
        _sessione["storico_fasce"] = stato.get("storico_fasce", [])
        logger.info("Stato ripristinato: fascia %d-%d, %d puzzle visti, %d tentati",
                    _sessione["elo_min"], _sessione["elo_max"],
                    len(_sessione["visti"]), _sessione["tentati"])
        return True
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Impossibile caricare lo stato (riparto pulito): %s", e)
        return False




def _prepara_sessione():
    """Costruisce il piano e appiattisce i puzzle in una coda ordinata."""
    # Provo a ripristinare lo stato salvato; se non c'e', parto dai default.
    if not _carica_stato():
        _sessione["elo_min"] = ELO_MIN
        _sessione["elo_max"] = ELO_MAX
        _sessione["visti"] = set()
    piano = costruisci_piano(GIOCATORE, PERCORSO_DB,
                             elo_min=_sessione["elo_min"], elo_max=_sessione["elo_max"],
                             puzzle_per_blocco=PUZZLE_PER_BLOCCO)
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
            _sessione["visti"].add(p["id"])
    _sessione["piano"] = piano
    _sessione["coda"] = coda
    _sessione["serviti"] = 0
    logger.info("Sessione pronta: %d puzzle in coda per %s", len(coda), GIOCATORE)
    return True




def _riempi_coda_tema(tema_lichess):
    """
    Riempie la coda con puzzle di UN SOLO tema, nella fascia Elo corrente,
    escludendo i visti. Usata dalla modalita' allenamento focalizzato.
    """
    from raccomanda import raccomanda
    import sqlite3
    # raccomanda filtra per fase/motivo noti; qui usiamo il tema direttamente,
    # quindi facciamo una query diretta sul database per massima flessibilita'.
    conn = sqlite3.connect(PERCORSO_DB)
    cur = conn.cursor()
    visti = list(_sessione["visti"])
    condizioni = ["themes LIKE ?", "rating BETWEEN ? AND ?"]
    parametri = [f"%{tema_lichess}%", _sessione["elo_min"], _sessione["elo_max"]]
    if visti:
        segnaposto = ",".join("?" for _ in visti)
        condizioni.append(f"id NOT IN ({segnaposto})")
        parametri.extend(visti)
    # Random su sottoinsieme (veloce): limita i candidati, poi mescola.
    query = ("SELECT id, fen, moves, rating, themes FROM ("
             + "SELECT id, fen, moves, rating, themes FROM puzzle WHERE "
             + " AND ".join(condizioni) + " LIMIT 5000"
             + ") ORDER BY RANDOM() LIMIT ?")
    parametri.append(PUZZLE_PER_BLOCCO)
    cur.execute(query, parametri)
    righe = cur.fetchall()
    conn.close()
    nuova_coda = _sessione["coda"][:_sessione["serviti"]]  # tieni i gia' serviti
    for r in righe:
        nuova_coda.append({
            "id": r[0], "fen": r[1], "moves": r[2], "rating": r[3], "themes": r[4],
            "motivo_allenamento": _sessione["tema_libero"],
            "fase_allenamento": "tema scelto",
        })
        _sessione["visti"].add(r[0])
    _sessione["coda"] = nuova_coda
    logger.info("Coda tema '%s' riempita: %d puzzle (fascia %d-%d)",
                _sessione["tema_libero"], len(righe),
                _sessione["elo_min"], _sessione["elo_max"])

def _ricostruisci_coda_con_fascia():
    """
    Dopo un cambio di fascia, ripesca i puzzle con la nuova fascia di Elo.
    In modalita' tema libero ripesca quel tema; altrimenti i temi del piano.
    """
    # Modalita' tema libero: ripesca solo quel tema.
    if _sessione["tema_libero"] is not None:
        _riempi_coda_tema(TEMI_DISPONIBILI[_sessione["tema_libero"]])
        return
    piano = _sessione["piano"]
    if piano is None:
        return
    from raccomanda import raccomanda
    nuova_coda = _sessione["coda"][:_sessione["serviti"]]  # tieni i gia' serviti
    for blocco in piano["blocchi"]:
        puzzle = raccomanda(PERCORSO_DB, fase=blocco["fase"], motivo=blocco["motivo"],
                            elo_min=_sessione["elo_min"], elo_max=_sessione["elo_max"],
                            quanti=PUZZLE_PER_BLOCCO,
                            escludi_id=list(_sessione["visti"]))
        for p in puzzle:
            nuova_coda.append({
                "id": p["id"], "fen": p["fen"], "moves": p["moves"],
                "rating": p["rating"], "themes": p["themes"],
                "motivo_allenamento": blocco["motivo"],
                "fase_allenamento": blocco["fase"],
            })
            _sessione["visti"].add(p["id"])
    _sessione["coda"] = nuova_coda
    logger.info("Coda ricostruita con fascia %d-%d: %d puzzle totali",
                _sessione["elo_min"], _sessione["elo_max"], len(nuova_coda))


def _valuta_adattivita():
    """
    Chiamata a fine blocco (ogni BLOCCO_ADATTIVO puzzle): valuta la % di successo
    al primo colpo sul blocco e aggiusta la fascia di Elo secondo la regola dell'85%.
    """
    conteggio = _sessione["blocco_conteggio"]
    if conteggio < BLOCCO_ADATTIVO:
        return None  # blocco non ancora completo

    primo = _sessione["blocco_primo"]
    perc = 100 * primo / conteggio
    vecchia = (_sessione["elo_min"], _sessione["elo_max"])
    cambiamento = None

    if perc >= SOGLIA_ALZA:
        _sessione["elo_min"] = min(_sessione["elo_min"] + PASSO_ELO, ELO_MAX_ASSOLUTO - 200)
        _sessione["elo_max"] = min(_sessione["elo_max"] + PASSO_ELO, ELO_MAX_ASSOLUTO)
        cambiamento = "alzata"
    elif perc < SOGLIA_ABBASSA:
        _sessione["elo_min"] = max(_sessione["elo_min"] - PASSO_ELO, ELO_MIN_ASSOLUTO)
        _sessione["elo_max"] = max(_sessione["elo_max"] - PASSO_ELO, ELO_MIN_ASSOLUTO + 200)
        cambiamento = "abbassata"

    logger.info("Blocco completo: %d/%d al primo (%.0f%%) -> fascia %s",
                primo, conteggio, perc, cambiamento or "invariata")

    # azzera il blocco
    _sessione["blocco_primo"] = 0
    _sessione["blocco_conteggio"] = 0

    if cambiamento:
        _sessione["storico_fasce"].append({
            "da": vecchia, "a": (_sessione["elo_min"], _sessione["elo_max"]),
            "percentuale": round(perc, 1), "azione": cambiamento,
        })
        _ricostruisci_coda_con_fascia()
        return cambiamento
    return None

class Esito(BaseModel):
    """Esito di un puzzle inviato dal frontend."""
    puzzle_id: str
    risultato: str  # "primo" | "secondo" | "fallito"


@app.post("/esito")
def registra_esito(esito: Esito):
    """Riceve l'esito di un puzzle e aggiorna le statistiche di sessione."""
    _sessione["tentati"] += 1
    _sessione["blocco_conteggio"] += 1
    if esito.risultato == "primo":
        _sessione["risolti_primo"] += 1
        _sessione["blocco_primo"] += 1
    elif esito.risultato == "secondo":
        _sessione["risolti_secondo"] += 1
    else:
        _sessione["falliti"] += 1

    # A fine blocco, valuta se adattare la difficolta'.
    cambiamento_fascia = _valuta_adattivita()

    tentati = _sessione["tentati"]
    successo = _sessione["risolti_primo"]
    perc = round(100 * successo / tentati, 1) if tentati else 0.0
    logger.info("Esito %s per %s. Successo al primo: %d/%d (%.1f%%)",
                esito.risultato, esito.puzzle_id, successo, tentati, perc)
    risposta = statistiche()
    risposta["fascia_cambiata"] = cambiamento_fascia
    _salva_stato()  # persisto lo stato dopo ogni esito
    return risposta


@app.get("/statistiche")
def statistiche():
    """Restituisce le statistiche di sessione correnti."""
    # Garantisco che lo stato salvato sia caricato prima di leggere i valori.
    if _sessione["piano"] is None:
        _prepara_sessione()
    tentati = _sessione["tentati"]
    successo = _sessione["risolti_primo"]
    perc_primo = round(100 * successo / tentati, 1) if tentati else 0.0
    return {
        "tentati": tentati,
        "risolti_primo": _sessione["risolti_primo"],
        "risolti_secondo": _sessione["risolti_secondo"],
        "falliti": _sessione["falliti"],
        "percentuale_primo": perc_primo,
        "elo_min": _sessione["elo_min"],
        "elo_max": _sessione["elo_max"],
    }


@app.get("/temi")
def lista_temi():
    """Restituisce i temi disponibili per la scelta libera."""
    return {"temi": list(TEMI_DISPONIBILI.keys())}


@app.post("/scegli-tema/{tema}")
def scegli_tema(tema: str):
    """
    Avvia l'allenamento focalizzato su un tema. Mantiene la fascia Elo corrente
    e l'adattivita'; cambia solo COSA viene proposto.
    """
    if tema not in TEMI_DISPONIBILI:
        return JSONResponse(status_code=404,
                            content={"errore": f"Tema sconosciuto: {tema}"})
    # Assicuriamoci che la sessione sia pronta (per avere fascia/visti).
    if _sessione["piano"] is None:
        _prepara_sessione()
    _sessione["tema_libero"] = tema
    _riempi_coda_tema(TEMI_DISPONIBILI[tema])
    logger.info("Modalita' tema attivata: %s", tema)
    return {"tema": tema, "messaggio": f"Allenamento focalizzato su: {tema}"}


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
