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

# --- Parametri dell'esaurimento puzzle ---
# Quando un blocco/tema ha pochi puzzle nuovi nella fascia corrente, alziamo
# SOLO TEMPORANEAMENTE il tetto per ripescare, senza toccare la fascia di base.
PUZZLE_MINIMI = 5          # min. puzzle nuovi per considerare la fascia sufficiente
ALLARGAMENTO_PASSO = 100   # di quanto alzare il tetto a ogni tentativo
ALLARGAMENTO_MAX = 400     # allargamento massimo totale sopra il tetto di base

# Temi disponibili per la scelta libera, raggruppati per categoria.
# Mappa categoria -> {nome italiano -> tema Lichess}.
TEMI_CATEGORIE = {
    "Tattiche": {
        "forchetta": "fork",
        "inchiodatura": "pin",
        "infilata": "skewer",
        "pezzo_in_presa": "hangingPiece",
        "attacco_di_scoperta": "discoveredAttack",
        "deviazione": "deflection",
        "adescamento": "attraction",
        "interferenza": "interference",
        "attacco_a_raggi_x": "xRayAttack",
        "sacrificio": "sacrifice",
        "mossa_intermedia": "intermezzo",
    },
    "Matti": {
        "matto_in_1": "mateIn1",
        "matto_in_2": "mateIn2",
        "matto_in_3": "mateIn3",
        "matto_affogato": "smotheredMate",
        "matto_colonna_base": "backRankMate",
        "matto_arabo": "arabianMate",
    },
    "Finali": {
        "finale_di_torre": "rookEndgame",
        "finale_di_pedoni": "pawnEndgame",
        "finale_di_alfieri": "bishopEndgame",
        "finale_di_cavalli": "knightEndgame",
        "finale_di_donna": "queenEndgame",
        "pedone_avanzato": "advancedPawn",
        "promozione": "promotion",
    },
}
# Mappa piatta nome italiano -> tema Lichess (unione di tutte le categorie),
# usata da scegli_tema e dalla pesca. 24 temi in totale.
TEMI_DISPONIBILI = {
    it: en for temi in TEMI_CATEGORIE.values() for it, en in temi.items()
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
    "esaurito": False,       # True se i puzzle nuovi scarseggiano (vedi esaurimento)
    # Statistiche per tema: tema -> {"tentati": n, "risolti_primo": n}.
    # Solo conteggi: NON influenzano in alcun modo la fascia/adattivita'.
    "statistiche_temi": {},
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
        "statistiche_temi": _sessione["statistiche_temi"],
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
        _sessione["statistiche_temi"] = stato.get("statistiche_temi", {})
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




def _pesca_allargando(pesca):
    """
    Cerca puzzle NUOVI tenendo fisso il pavimento (l'elo_min di sessione) e alzando
    SOLO TEMPORANEAMENTE il tetto superiore quando i puzzle nuovi scarseggiano.

    `pesca(elo_max_eff)` deve restituire la lista di puzzle nuovi trovati nella
    fascia [elo_min di sessione, elo_max_eff].

    Parte dal tetto di base (la fascia adattiva di sessione). Finche' i puzzle
    nuovi sono meno di PUZZLE_MINIMI, alza il tetto di ALLARGAMENTO_PASSO alla
    volta, fino a +ALLARGAMENTO_MAX sopra il tetto di base oppure al tetto assoluto
    ELO_MAX_ASSOLUTO. La fascia di base in _sessione NON viene MAI toccata: questo
    e' solo un allargamento "effettivo" e temporaneo per la singola pesca, cosi'
    l'adattivita' resta l'unica padrona della fascia di base.

    RESTITUISCE (righe, esaurito): esaurito=True se nemmeno col tetto massimo si
    raggiungono PUZZLE_MINIMI puzzle nuovi.
    """
    base_max = _sessione["elo_max"]
    tetto_limite = min(base_max + ALLARGAMENTO_MAX, ELO_MAX_ASSOLUTO)
    elo_max_eff = base_max
    righe = pesca(elo_max_eff)
    while len(righe) < PUZZLE_MINIMI and elo_max_eff < tetto_limite:
        elo_max_eff = min(elo_max_eff + ALLARGAMENTO_PASSO, tetto_limite)
        righe = pesca(elo_max_eff)
        logger.info("Pochi puzzle nuovi: tetto allargato temporaneamente a %d "
                    "(base %d), trovati %d", elo_max_eff, base_max, len(righe))
    esaurito = len(righe) < PUZZLE_MINIMI
    return righe, esaurito


def _pesca_tema_righe(tema_lichess, elo_max):
    """
    Query diretta sul database: puzzle NUOVI di un tema nella fascia
    [elo_min di sessione, elo_max], escludendo i visti.
    `elo_max` puo' essere il tetto di base o uno allargato temporaneamente.
    """
    import sqlite3
    # raccomanda filtra per fase/motivo noti; qui usiamo il tema direttamente,
    # quindi facciamo una query diretta sul database per massima flessibilita'.
    conn = sqlite3.connect(PERCORSO_DB)
    cur = conn.cursor()
    visti = list(_sessione["visti"])
    condizioni = ["themes LIKE ?", "rating BETWEEN ? AND ?"]
    parametri = [f"%{tema_lichess}%", _sessione["elo_min"], elo_max]
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
    return righe


def _riempi_coda_tema(tema_lichess):
    """
    Riempie la coda con puzzle di UN SOLO tema, partendo dalla fascia Elo corrente
    ed escludendo i visti. Se i puzzle nuovi scarseggiano allarga temporaneamente
    il tetto (senza toccare la fascia di sessione). Imposta _sessione["esaurito"].
    RESTITUISCE True se il tema e' esaurito (puzzle nuovi insufficienti).
    """
    righe, esaurito = _pesca_allargando(
        lambda emax: _pesca_tema_righe(tema_lichess, emax))
    nuova_coda = _sessione["coda"][:_sessione["serviti"]]  # tieni i gia' serviti
    for r in righe:
        nuova_coda.append({
            "id": r[0], "fen": r[1], "moves": r[2], "rating": r[3], "themes": r[4],
            "motivo_allenamento": _sessione["tema_libero"],
            "fase_allenamento": "tema scelto",
        })
        _sessione["visti"].add(r[0])
    _sessione["coda"] = nuova_coda
    _sessione["esaurito"] = esaurito
    if esaurito:
        logger.info("Tema '%s' esaurito: solo %d puzzle nuovi anche col tetto "
                    "allargato.", _sessione["tema_libero"], len(righe))
    else:
        logger.info("Coda tema '%s' riempita: %d puzzle nuovi (fascia base %d-%d)",
                    _sessione["tema_libero"], len(righe),
                    _sessione["elo_min"], _sessione["elo_max"])
    return esaurito

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
    nuovi = 0
    for blocco in piano["blocchi"]:
        # b=blocco fissa il blocco nella lambda (evita la late-binding nel ciclo).
        puzzle, _ = _pesca_allargando(
            lambda emax, b=blocco: raccomanda(
                PERCORSO_DB, fase=b["fase"], motivo=b["motivo"],
                elo_min=_sessione["elo_min"], elo_max=emax,
                quanti=PUZZLE_PER_BLOCCO, escludi_id=list(_sessione["visti"])))
        for p in puzzle:
            nuova_coda.append({
                "id": p["id"], "fen": p["fen"], "moves": p["moves"],
                "rating": p["rating"], "themes": p["themes"],
                "motivo_allenamento": blocco["motivo"],
                "fase_allenamento": blocco["fase"],
            })
            _sessione["visti"].add(p["id"])
            nuovi += 1
    _sessione["coda"] = nuova_coda
    # Esaurito se, in tutto il piano, i puzzle nuovi aggiunti sono insufficienti.
    _sessione["esaurito"] = nuovi < PUZZLE_MINIMI
    logger.info("Coda ricostruita con fascia base %d-%d: %d puzzle nuovi aggiunti",
                _sessione["elo_min"], _sessione["elo_max"], nuovi)


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


def _tema_di_puzzle(puzzle_id):
    """
    Trova il tema (motivo_allenamento) del puzzle servito, cercandolo in coda.
    RESTITUISCE il nome del tema, "altro" se il puzzle non ha tema, None se
    il puzzle non e' in coda.
    """
    for p in _sessione["coda"]:
        if p["id"] == puzzle_id:
            return p.get("motivo_allenamento") or "altro"
    return None


def _aggiorna_statistiche_tema(puzzle_id, risultato):
    """
    Aggiorna i conteggi per-tema (tentati / risolti_primo). Solo statistica:
    NON tocca fascia, blocco o adattivita'.
    """
    tema = _tema_di_puzzle(puzzle_id)
    if tema is None:
        return
    st = _sessione["statistiche_temi"].setdefault(
        tema, {"tentati": 0, "risolti_primo": 0})
    st["tentati"] += 1
    if risultato == "primo":
        st["risolti_primo"] += 1


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

    # Statistiche per tema (solo conteggi, indipendenti dall'adattivita').
    _aggiorna_statistiche_tema(esito.puzzle_id, esito.risultato)

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
    """
    Restituisce i temi disponibili per la scelta libera. Sia la lista piatta
    (compatibilita') sia il raggruppamento per categoria (Tattiche/Matti/Finali).
    """
    return {
        "temi": list(TEMI_DISPONIBILI.keys()),
        "categorie": {cat: list(temi.keys())
                      for cat, temi in TEMI_CATEGORIE.items()},
    }


@app.get("/statistiche-temi")
def statistiche_temi():
    """
    Restituisce, per ogni tema affrontato, quanti puzzle tentati e quanti
    risolti al primo colpo, con la relativa percentuale. Dati persistiti.
    """
    if _sessione["piano"] is None:
        _prepara_sessione()
    risultato = {}
    for tema, st in _sessione["statistiche_temi"].items():
        tentati = st["tentati"]
        primo = st["risolti_primo"]
        risultato[tema] = {
            "tentati": tentati,
            "risolti_primo": primo,
            "percentuale_primo": round(100 * primo / tentati, 1) if tentati else 0.0,
        }
    return {"temi": risultato}


@app.get("/storico-fasce")
def storico_fasce():
    """
    Restituisce lo storico dei cambi di fascia (per il grafico Elo nel tempo)
    e la fascia attuale.
    """
    if _sessione["piano"] is None:
        _prepara_sessione()
    return {
        "storico_fasce": _sessione["storico_fasce"],
        "elo_min": _sessione["elo_min"],
        "elo_max": _sessione["elo_max"],
    }


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
    esaurito = _riempi_coda_tema(TEMI_DISPONIBILI[tema])
    logger.info("Modalita' tema attivata: %s", tema)
    risposta = {"tema": tema, "messaggio": f"Allenamento focalizzato su: {tema}",
                "esaurito": esaurito}
    if esaurito:
        risposta["suggerimento"] = (
            "Pochi puzzle nuovi per questo tema, anche allargando la fascia: "
            "prova a cambiare tema per continuare a variare.")
    return risposta


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
        risposta = {"fine": True,
                    "messaggio": "Hai completato tutti i puzzle disponibili!"}
        if _sessione["esaurito"]:
            risposta["esaurito"] = True
            risposta["suggerimento"] = (
                "I puzzle nuovi di questo tema sono esauriti, anche allargando la "
                "fascia di Elo. Prova a cambiare tema.")
        return risposta

    puzzle = _sessione["coda"][idx]
    _sessione["serviti"] += 1
    risposta = {
        "fine": False,
        "numero": idx + 1,
        "totale": len(_sessione["coda"]),
        "puzzle": puzzle,
        "esaurito": _sessione["esaurito"],
    }
    if _sessione["esaurito"]:
        risposta["suggerimento"] = (
            "I puzzle nuovi di questo tema stanno per finire, anche allargando la "
            "fascia di Elo. Valuta di cambiare tema.")
    return risposta
