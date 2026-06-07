"""
Backend FastAPI (api) - serve i puzzle dell'allenamento, separati in FLUSSI.

Espone il "cervello" del sistema via web: il browser puo' chiedere il prossimo
puzzle da fare, e il server lo pesca dal flusso attivo.

Il sistema gestisce TRE flussi indipendenti (punto 1 della visione estesa):
  - "piano"  : puzzle dalle debolezze del profilo (piano automatico)
  - "temi"   : puzzle del tema scelto liberamente dall'utente
  - "errori" : puzzle dai propri errori (PREDISPOSTO, non ancora implementato; punto 6)

Ogni flusso ha, in modo INDIPENDENTE: la propria coda, la propria fascia di Elo
adattiva (regola dell'85%), le proprie statistiche (tentati / risolti al primo /
snapshot storici / statistiche-per-tema). I puzzle "visti" sono invece GLOBALI tra
i flussi, cosi' non si rivede lo stesso puzzle passando da un flusso all'altro.

Endpoint principali:
  GET  /                  -> info backend
  GET  /flussi            -> elenco flussi, flusso attivo, riepilogo complessivo
  POST /flusso/{nome}     -> cambia il flusso attivo
  GET  /prossimo-puzzle   -> il prossimo puzzle del flusso attivo
  POST /esito             -> registra l'esito (sul flusso attivo)
  GET  /statistiche       -> statistiche del flusso attivo (+ riepilogo complessivo)
  POST /scegli-tema/{t}   -> attiva il flusso "temi" su un tema
  GET  /progressi         -> snapshot/tendenza/riepilogo del flusso attivo

Avvio (dalla cartella api, con ambiente attivo):
    uvicorn server:app --reload
"""

import os
import sys
import json
import logging
import datetime
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

# --- I tre flussi indipendenti ---
# L'ordine e' anche quello di presentazione nel frontend.
FLUSSI = ("piano", "temi", "errori")
FLUSSO_DEFAULT = "piano"
# Flussi gia' implementati (il flusso "errori" e' solo predisposto: verra' col punto 6).
FLUSSI_IMPLEMENTATI = ("piano", "temi")
# Versione del formato del file di stato (1 = vecchio stato singolo; 2 = tre flussi).
VERSIONE_STATO = 2

# --- Parametri della difficolta' adattiva ---
BLOCCO_ADATTIVO = 10     # ogni quanti puzzle ricalibrare
SOGLIA_ALZA = 90.0       # sopra questa % (sul blocco) -> alza la fascia
SOGLIA_ABBASSA = 70.0    # sotto questa % -> abbassa la fascia
PASSO_ELO = 100          # di quanti punti spostare la fascia
PUZZLE_PER_BLOCCO = 30   # quanti puzzle pescare per blocco (varieta')

# --- Parametri degli snapshot di progresso ---
# Ogni SNAPSHOT_OGNI puzzle tentati salviamo una fotografia (percentuale al primo
# colpo storica + fascia Elo) per i grafici dei progressi nel tempo. La tendenza
# del miglioramento si calcola sugli ultimi TENDENZA_FINESTRA snapshot.
# Tutto qui e' SOLO lettura/conteggio: NON influenza la fascia adattiva.
SNAPSHOT_OGNI = 10
TENDENZA_FINESTRA = 5

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


# --- Struttura dello stato: un dizionario per flusso ---------------------
# Campi di un flusso che vengono PERSISTITI su file (tutto il resto e' transitorio
# e si ricostruisce all'avvio: piano, coda, serviti, blocco_*).
CAMPI_PERSISTENTI_FLUSSO = (
    "tentati", "risolti_primo", "risolti_secondo", "falliti",
    "elo_min", "elo_max", "storico_fasce", "statistiche_temi",
    "snapshot_progresso", "tema_libero",
)


def _nuovo_flusso():
    """
    Stato fresco di UN flusso: coda propria, fascia adattiva propria, statistiche
    proprie. I "visti" NON stanno qui: sono globali alla sessione (vedi _sessione).
    """
    return {
        # Transitori (ricostruiti all'avvio, non persistiti):
        "piano": None,           # output di costruisci_piano (solo flusso "piano")
        "coda": [],              # puzzle da servire, in ordine
        "serviti": 0,
        "blocco_primo": 0,       # risolti al primo nel blocco corrente
        "blocco_conteggio": 0,   # puzzle nel blocco corrente
        "esaurito": False,       # True se i puzzle nuovi scarseggiano
        # Persistiti:
        "tentati": 0,            # puzzle di cui e' arrivato un esito
        "risolti_primo": 0,      # risolti al primo tentativo (= successo)
        "risolti_secondo": 0,    # risolti dopo qualche errore
        "falliti": 0,            # soluzione mostrata
        "elo_min": ELO_MIN,      # fascia adattiva PROPRIA del flusso
        "elo_max": ELO_MAX,
        "storico_fasce": [],     # cambi di fascia di QUESTO flusso
        "tema_libero": None,     # tema attivo (solo flusso "temi")
        "statistiche_temi": {},  # tema -> {"tentati", "risolti_primo"}
        "snapshot_progresso": [],  # fotografie periodiche dei progressi
    }


# Stato in memoria della sessione: i tre flussi + lo stato globale condiviso.
_sessione = {
    "pronta": False,               # True dopo _prepara_sessione
    "flusso_attivo": FLUSSO_DEFAULT,
    # I "visti" sono GLOBALI tra i flussi (scelta progettuale): cosi' non si
    # rivede lo stesso puzzle passando da piano a temi a errori.
    "visti": set(),
    "flussi": {nome: _nuovo_flusso() for nome in FLUSSI},
}


def _flusso(nome=None):
    """Restituisce lo stato del flusso indicato (o di quello attivo)."""
    return _sessione["flussi"][nome or _sessione["flusso_attivo"]]


def _assicura_pronta():
    """Prepara la sessione alla prima richiesta utile (lazy init)."""
    if not _sessione["pronta"]:
        _prepara_sessione()


# --- Persistenza (tre flussi separati, con migrazione dal vecchio formato) ---

def _serializza_flusso(f):
    """Estrae da un flusso i soli campi da persistere."""
    return {k: f[k] for k in CAMPI_PERSISTENTI_FLUSSO}


def _applica_stato_flusso(f, dati):
    """Riversa i campi persistiti dentro un flusso fresco (mancanti -> default)."""
    for k in CAMPI_PERSISTENTI_FLUSSO:
        if k in dati:
            f[k] = dati[k]


def _salva_stato():
    """
    Salva lo stato persistente dei TRE flussi su file JSON (formato v2).
    Scrittura sicura: scrive su file temporaneo e poi rinomina, cosi' non
    resta mai un file a meta' se qualcosa si interrompe.
    """
    stato = {
        "versione": VERSIONE_STATO,
        "flusso_attivo": _sessione["flusso_attivo"],
        "visti": list(_sessione["visti"]),  # set -> lista per il JSON; globale
        "flussi": {nome: _serializza_flusso(_sessione["flussi"][nome])
                   for nome in FLUSSI},
    }
    try:
        tmp = PERCORSO_STATO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(stato, fp)
        os.replace(tmp, PERCORSO_STATO)  # rinomina atomica
    except OSError as e:
        logger.warning("Impossibile salvare lo stato: %s", e)


def _carica_stato():
    """
    Carica lo stato persistente all'avvio, se il file esiste.

    Gestisce DUE formati per retrocompatibilita':
      - v2 (tre flussi): ricarica ogni flusso separatamente + visti globali.
      - v1 (stato singolo, vecchio file): MIGRA tutto nel flusso "piano" (default
        sensato, perche' la vecchia modalita' di base era proprio il piano), con i
        visti che diventano globali. Non si perde nulla e non si crasha.

    RESTITUISCE True se ha caricato uno stato salvato, False altrimenti.
    """
    if not os.path.exists(PERCORSO_STATO):
        return False
    try:
        with open(PERCORSO_STATO, "r", encoding="utf-8") as fp:
            stato = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Impossibile caricare lo stato (riparto pulito): %s", e)
        return False

    # Riparto sempre da flussi freschi e ci riverso i dati salvati.
    _sessione["flussi"] = {nome: _nuovo_flusso() for nome in FLUSSI}
    _sessione["visti"] = set(stato.get("visti", []))  # globale in entrambi i formati

    if "flussi" in stato:
        # Formato nuovo (v2): tre flussi separati.
        _sessione["flusso_attivo"] = stato.get("flusso_attivo", FLUSSO_DEFAULT)
        if _sessione["flusso_attivo"] not in FLUSSI:
            _sessione["flusso_attivo"] = FLUSSO_DEFAULT
        for nome in FLUSSI:
            if nome in stato["flussi"]:
                _applica_stato_flusso(_sessione["flussi"][nome], stato["flussi"][nome])
        logger.info("Stato (v2) ripristinato: %d flussi, %d puzzle visti globali",
                    len(FLUSSI), len(_sessione["visti"]))
    else:
        # Formato vecchio (v1, stato singolo): migrazione nel flusso "piano".
        _applica_stato_flusso(_sessione["flussi"]["piano"], stato)
        _sessione["flusso_attivo"] = FLUSSO_DEFAULT
        logger.info("Stato VECCHIO (v1) migrato nel flusso 'piano': %d tentati, "
                    "%d visti globali", _sessione["flussi"]["piano"]["tentati"],
                    len(_sessione["visti"]))
    return True


def _prepara_sessione():
    """
    Carica lo stato (o parte dai default) e costruisce il piano del flusso "piano".
    Se un tema era attivo nel flusso "temi" (da persistenza), ne ricostruisce la coda.
    RESTITUISCE True se il flusso "piano" e' stato costruito, False altrimenti.
    """
    if not _carica_stato():
        # Nessun file: flussi gia' freschi ai default.
        _sessione["flussi"] = {nome: _nuovo_flusso() for nome in FLUSSI}
        _sessione["visti"] = set()
        _sessione["flusso_attivo"] = FLUSSO_DEFAULT

    fp = _sessione["flussi"]["piano"]
    piano = costruisci_piano(GIOCATORE, PERCORSO_DB,
                             elo_min=fp["elo_min"], elo_max=fp["elo_max"],
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
    fp["piano"] = piano
    fp["coda"] = coda
    fp["serviti"] = 0

    # Flusso "temi": se un tema era attivo (ripristinato da file), ricostruisci la coda.
    ft = _sessione["flussi"]["temi"]
    if ft["tema_libero"] in TEMI_DISPONIBILI:
        _riempi_coda_tema(ft, TEMI_DISPONIBILI[ft["tema_libero"]])

    _sessione["pronta"] = True
    logger.info("Sessione pronta: piano %d puzzle, flusso attivo '%s'",
                len(coda), _sessione["flusso_attivo"])
    return True


# --- Pesca dei puzzle (sempre relativa a un flusso `f`) ------------------

def _pesca_allargando(f, pesca):
    """
    Cerca puzzle NUOVI tenendo fisso il pavimento (l'elo_min del flusso) e alzando
    SOLO TEMPORANEAMENTE il tetto superiore quando i puzzle nuovi scarseggiano.

    `pesca(elo_max_eff)` deve restituire la lista di puzzle nuovi trovati nella
    fascia [elo_min del flusso, elo_max_eff].

    La fascia di base del flusso NON viene MAI toccata: e' solo un allargamento
    "effettivo" e temporaneo per la singola pesca, cosi' l'adattivita' resta
    l'unica padrona della fascia di base di quel flusso.

    RESTITUISCE (righe, esaurito): esaurito=True se nemmeno col tetto massimo si
    raggiungono PUZZLE_MINIMI puzzle nuovi.
    """
    base_max = f["elo_max"]
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


def _pesca_tema_righe(f, tema_lichess, elo_max):
    """
    Query diretta sul database: puzzle NUOVI di un tema nella fascia
    [elo_min del flusso, elo_max], escludendo i visti GLOBALI.
    `elo_max` puo' essere il tetto di base o uno allargato temporaneamente.
    """
    import sqlite3
    conn = sqlite3.connect(PERCORSO_DB)
    cur = conn.cursor()
    visti = list(_sessione["visti"])  # GLOBALE tra i flussi
    condizioni = ["themes LIKE ?", "rating BETWEEN ? AND ?"]
    parametri = [f"%{tema_lichess}%", f["elo_min"], elo_max]
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


def _riempi_coda_tema(f, tema_lichess):
    """
    Riempie la coda del flusso `f` con puzzle di UN SOLO tema, partendo dalla sua
    fascia Elo ed escludendo i visti globali. Se i puzzle nuovi scarseggiano allarga
    temporaneamente il tetto (senza toccare la fascia di base). Imposta f["esaurito"].
    RESTITUISCE True se il tema e' esaurito (puzzle nuovi insufficienti).
    """
    righe, esaurito = _pesca_allargando(
        f, lambda emax: _pesca_tema_righe(f, tema_lichess, emax))
    nuova_coda = f["coda"][:f["serviti"]]  # tieni i gia' serviti
    for r in righe:
        nuova_coda.append({
            "id": r[0], "fen": r[1], "moves": r[2], "rating": r[3], "themes": r[4],
            "motivo_allenamento": f["tema_libero"],
            "fase_allenamento": "tema scelto",
        })
        _sessione["visti"].add(r[0])
    f["coda"] = nuova_coda
    f["esaurito"] = esaurito
    if esaurito:
        logger.info("Tema '%s' esaurito: solo %d puzzle nuovi anche col tetto "
                    "allargato.", f["tema_libero"], len(righe))
    else:
        logger.info("Coda tema '%s' riempita: %d puzzle nuovi (fascia base %d-%d)",
                    f["tema_libero"], len(righe), f["elo_min"], f["elo_max"])
    return esaurito


def _ricostruisci_coda_con_fascia(f):
    """
    Dopo un cambio di fascia del flusso `f`, ripesca i puzzle con la nuova fascia.
    In modalita' tema libero ripesca quel tema; altrimenti i temi del piano.
    """
    # Flusso "temi": ripesca solo quel tema.
    if f["tema_libero"] is not None:
        _riempi_coda_tema(f, TEMI_DISPONIBILI[f["tema_libero"]])
        return
    piano = f["piano"]
    if piano is None:
        return
    from raccomanda import raccomanda
    nuova_coda = f["coda"][:f["serviti"]]  # tieni i gia' serviti
    nuovi = 0
    for blocco in piano["blocchi"]:
        # b=blocco fissa il blocco nella lambda (evita la late-binding nel ciclo).
        puzzle, _ = _pesca_allargando(
            f, lambda emax, b=blocco: raccomanda(
                PERCORSO_DB, fase=b["fase"], motivo=b["motivo"],
                elo_min=f["elo_min"], elo_max=emax,
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
    f["coda"] = nuova_coda
    # Esaurito se, in tutto il piano, i puzzle nuovi aggiunti sono insufficienti.
    f["esaurito"] = nuovi < PUZZLE_MINIMI
    logger.info("Coda ricostruita con fascia base %d-%d: %d puzzle nuovi aggiunti",
                f["elo_min"], f["elo_max"], nuovi)


def _valuta_adattivita(f):
    """
    Chiamata a fine blocco (ogni BLOCCO_ADATTIVO puzzle) sul flusso `f`: valuta la
    % di successo al primo colpo sul blocco e aggiusta la fascia di Elo PROPRIA del
    flusso secondo la regola dell'85%. Ogni flusso ha la sua fascia indipendente.
    """
    conteggio = f["blocco_conteggio"]
    if conteggio < BLOCCO_ADATTIVO:
        return None  # blocco non ancora completo

    primo = f["blocco_primo"]
    perc = 100 * primo / conteggio
    vecchia = (f["elo_min"], f["elo_max"])
    cambiamento = None

    if perc >= SOGLIA_ALZA:
        f["elo_min"] = min(f["elo_min"] + PASSO_ELO, ELO_MAX_ASSOLUTO - 200)
        f["elo_max"] = min(f["elo_max"] + PASSO_ELO, ELO_MAX_ASSOLUTO)
        cambiamento = "alzata"
    elif perc < SOGLIA_ABBASSA:
        f["elo_min"] = max(f["elo_min"] - PASSO_ELO, ELO_MIN_ASSOLUTO)
        f["elo_max"] = max(f["elo_max"] - PASSO_ELO, ELO_MIN_ASSOLUTO + 200)
        cambiamento = "abbassata"

    logger.info("Blocco completo: %d/%d al primo (%.0f%%) -> fascia %s",
                primo, conteggio, perc, cambiamento or "invariata")

    # azzera il blocco
    f["blocco_primo"] = 0
    f["blocco_conteggio"] = 0

    if cambiamento:
        f["storico_fasce"].append({
            "da": vecchia, "a": (f["elo_min"], f["elo_max"]),
            "percentuale": round(perc, 1), "azione": cambiamento,
        })
        _ricostruisci_coda_con_fascia(f)
        return cambiamento
    return None


def _crea_snapshot(f):
    """
    Salva una fotografia dei progressi del flusso `f`: percentuale storica al primo
    colpo e fascia Elo correnti, con timestamp. Chiamato ogni SNAPSHOT_OGNI tentati.

    SOLO lettura/conteggio: legge i valori correnti e li appende alla lista; NON
    tocca in alcun modo la fascia governata dall'adattivita'.
    """
    tentati = f["tentati"]
    perc = round(100 * f["risolti_primo"] / tentati, 1) if tentati else 0.0
    f["snapshot_progresso"].append({
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "tentati": tentati,
        "percentuale_primo_colpo": perc,
        "fascia_elo": [f["elo_min"], f["elo_max"]],
    })


def _punto_medio_fascia(fascia):
    """Punto medio di una fascia [min, max] (piu' leggibile di due valori)."""
    return (fascia[0] + fascia[1]) / 2


def _calcola_tendenza(snapshot, finestra=TENDENZA_FINESTRA):
    """
    Tendenza della fascia Elo sugli ultimi `finestra` snapshot: confronta il punto
    medio della fascia del primo e dell'ultimo snapshot della finestra.

    RESTITUISCE {"direzione", "freccia", "etichetta"}:
      - "su"      ↑ "In crescita"  se la fascia sta salendo
      - "stabile" → "Stabile"      se ferma (o snapshot insufficienti)
      - "giu"     ↓ "In calo"      se scende

    SOLO lettura: e' l'indicatore onesto di miglioramento, non tocca l'adattivita'.
    """
    recenti = snapshot[-finestra:]
    if len(recenti) < 2:
        return {"direzione": "stabile", "freccia": "→", "etichetta": "Stabile"}
    delta = (_punto_medio_fascia(recenti[-1]["fascia_elo"])
             - _punto_medio_fascia(recenti[0]["fascia_elo"]))
    if delta > 0:
        return {"direzione": "su", "freccia": "↑", "etichetta": "In crescita"}
    if delta < 0:
        return {"direzione": "giu", "freccia": "↓", "etichetta": "In calo"}
    return {"direzione": "stabile", "freccia": "→", "etichetta": "Stabile"}


def _riepilogo_progressi(f):
    """
    Tabella riassuntiva dei progressi del flusso `f` (SOLO lettura/conteggio):
    - puzzle totali tentati
    - percentuale al primo colpo storica complessiva
    - fascia Elo iniziale (la prima registrata) vs attuale, con il guadagno
    - tema con la percentuale di successo piu' alta e quello piu' bassa
    """
    tentati = f["tentati"]
    perc = round(100 * f["risolti_primo"] / tentati, 1) if tentati else 0.0

    # Fascia iniziale "la prima registrata": preferiamo il primo snapshot; se non
    # ce ne sono ancora, ricadiamo sul primo cambio di fascia, poi sulla fascia
    # attuale (flusso appena partito).
    snap = f["snapshot_progresso"]
    if snap:
        elo_iniziale = list(snap[0]["fascia_elo"])
    elif f["storico_fasce"]:
        elo_iniziale = list(f["storico_fasce"][0]["da"])
    else:
        elo_iniziale = [f["elo_min"], f["elo_max"]]
    elo_attuale = [f["elo_min"], f["elo_max"]]
    guadagno = round(_punto_medio_fascia(elo_attuale)
                     - _punto_medio_fascia(elo_iniziale))

    # Tema migliore/peggiore per % al primo colpo (dalle statistiche-per-tema).
    migliore = peggiore = None
    for tema, st in f["statistiche_temi"].items():
        if st["tentati"] == 0:
            continue
        p = round(100 * st["risolti_primo"] / st["tentati"], 1)
        voce = {"tema": tema, "percentuale_primo": p, "tentati": st["tentati"]}
        if migliore is None or p > migliore["percentuale_primo"]:
            migliore = voce
        if peggiore is None or p < peggiore["percentuale_primo"]:
            peggiore = voce

    return {
        "tentati_totali": tentati,
        "percentuale_primo_storica": perc,
        "elo_iniziale": elo_iniziale,
        "elo_attuale": elo_attuale,
        "guadagno": guadagno,
        "tema_migliore": migliore,
        "tema_peggiore": peggiore,
    }


def _riepilogo_complessivo():
    """
    Piccolo riepilogo COMPLESSIVO: somma i puzzle fatti su tutti i flussi.
    Le statistiche principali restano per-flusso; questo e' solo un totale di
    contorno (quanto ho fatto in tutto). SOLO lettura.
    """
    flussi = _sessione["flussi"]
    tot_tentati = sum(fl["tentati"] for fl in flussi.values())
    tot_primo = sum(fl["risolti_primo"] for fl in flussi.values())
    return {
        "tentati_totali": tot_tentati,
        "risolti_primo_totali": tot_primo,
        "percentuale_primo": round(100 * tot_primo / tot_tentati, 1) if tot_tentati else 0.0,
        "per_flusso": {nome: {"tentati": fl["tentati"],
                              "risolti_primo": fl["risolti_primo"]}
                       for nome, fl in flussi.items()},
    }


class Esito(BaseModel):
    """Esito di un puzzle inviato dal frontend."""
    puzzle_id: str
    risultato: str  # "primo" | "secondo" | "fallito"


def _tema_di_puzzle(f, puzzle_id):
    """
    Trova il tema (motivo_allenamento) del puzzle nella coda del flusso `f`.
    RESTITUISCE il nome del tema, "altro" se il puzzle non ha tema, None se
    il puzzle non e' nella coda del flusso.
    """
    for p in f["coda"]:
        if p["id"] == puzzle_id:
            return p.get("motivo_allenamento") or "altro"
    return None


def _aggiorna_statistiche_tema(f, puzzle_id, risultato):
    """
    Aggiorna i conteggi per-tema del flusso `f` (tentati / risolti_primo). Solo
    statistica: NON tocca fascia, blocco o adattivita'.
    """
    tema = _tema_di_puzzle(f, puzzle_id)
    if tema is None:
        return
    st = f["statistiche_temi"].setdefault(
        tema, {"tentati": 0, "risolti_primo": 0})
    st["tentati"] += 1
    if risultato == "primo":
        st["risolti_primo"] += 1


@app.post("/esito")
def registra_esito(esito: Esito):
    """Riceve l'esito di un puzzle e aggiorna le statistiche del FLUSSO ATTIVO."""
    f = _flusso()  # tutto si applica al flusso attivo, in modo indipendente
    f["tentati"] += 1
    f["blocco_conteggio"] += 1
    if esito.risultato == "primo":
        f["risolti_primo"] += 1
        f["blocco_primo"] += 1
    elif esito.risultato == "secondo":
        f["risolti_secondo"] += 1
    else:
        f["falliti"] += 1

    # Statistiche per tema (solo conteggi, indipendenti dall'adattivita').
    _aggiorna_statistiche_tema(f, esito.puzzle_id, esito.risultato)

    # A fine blocco, valuta se adattare la difficolta' di QUESTO flusso.
    cambiamento_fascia = _valuta_adattivita(f)

    # Snapshot periodico dei progressi (ogni SNAPSHOT_OGNI puzzle tentati del flusso).
    # Va DOPO l'adattivita' cosi' fotografa la fascia eventualmente appena aggiornata.
    if f["tentati"] % SNAPSHOT_OGNI == 0:
        _crea_snapshot(f)

    successo = f["risolti_primo"]
    perc = round(100 * successo / f["tentati"], 1) if f["tentati"] else 0.0
    logger.info("[%s] Esito %s per %s. Successo al primo: %d/%d (%.1f%%)",
                _sessione["flusso_attivo"], esito.risultato, esito.puzzle_id,
                successo, f["tentati"], perc)
    risposta = statistiche()
    risposta["fascia_cambiata"] = cambiamento_fascia
    _salva_stato()  # persisto lo stato (tre flussi) dopo ogni esito
    return risposta


@app.get("/statistiche")
def statistiche():
    """
    Statistiche del FLUSSO ATTIVO (principali), piu' un riepilogo complessivo che
    somma tutti i flussi (totale puzzle fatti).
    """
    _assicura_pronta()
    f = _flusso()
    tentati = f["tentati"]
    successo = f["risolti_primo"]
    perc_primo = round(100 * successo / tentati, 1) if tentati else 0.0
    return {
        "flusso": _sessione["flusso_attivo"],
        "tema_libero": f["tema_libero"],
        "tentati": tentati,
        "risolti_primo": f["risolti_primo"],
        "risolti_secondo": f["risolti_secondo"],
        "falliti": f["falliti"],
        "percentuale_primo": perc_primo,
        "elo_min": f["elo_min"],
        "elo_max": f["elo_max"],
        "complessivo": _riepilogo_complessivo(),
    }


@app.get("/flussi")
def lista_flussi():
    """
    Elenco dei flussi con un riassunto di ciascuno, il flusso attivo e il
    riepilogo complessivo. Serve al frontend per il selettore di flusso.
    """
    _assicura_pronta()
    return {
        "flusso_attivo": _sessione["flusso_attivo"],
        "flussi": {
            nome: {
                "implementato": nome in FLUSSI_IMPLEMENTATI,
                "tentati": f["tentati"],
                "risolti_primo": f["risolti_primo"],
                "percentuale_primo": (round(100 * f["risolti_primo"] / f["tentati"], 1)
                                      if f["tentati"] else 0.0),
                "elo_min": f["elo_min"],
                "elo_max": f["elo_max"],
                "tema_libero": f["tema_libero"],
                "rimanenti": len(f["coda"]) - f["serviti"],
            } for nome, f in _sessione["flussi"].items()
        },
        "complessivo": _riepilogo_complessivo(),
    }


@app.post("/flusso/{nome}")
def imposta_flusso(nome: str):
    """
    Cambia il flusso attivo. Il flusso "errori" e' predisposto ma non ancora
    implementato (verra' col punto 6): se richiesto, risponde 501 senza cambiare.
    """
    if nome not in FLUSSI:
        return JSONResponse(status_code=404,
                            content={"errore": f"Flusso sconosciuto: {nome}"})
    if nome not in FLUSSI_IMPLEMENTATI:
        return JSONResponse(status_code=501, content={
            "errore": "Il flusso 'errori' non e' ancora implementato "
                      "(verra' col punto 6 della visione).",
            "flusso": nome})
    _assicura_pronta()
    _sessione["flusso_attivo"] = nome
    _salva_stato()
    f = _flusso(nome)
    logger.info("Flusso attivo cambiato in '%s'", nome)
    return {
        "flusso_attivo": nome,
        "tema_libero": f["tema_libero"],
        "rimanenti": len(f["coda"]) - f["serviti"],
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
    Per ogni tema affrontato nel FLUSSO ATTIVO: quanti puzzle tentati e quanti
    risolti al primo colpo, con la percentuale. Dati persistiti per flusso.
    """
    _assicura_pronta()
    f = _flusso()
    risultato = {}
    for tema, st in f["statistiche_temi"].items():
        tentati = st["tentati"]
        primo = st["risolti_primo"]
        risultato[tema] = {
            "tentati": tentati,
            "risolti_primo": primo,
            "percentuale_primo": round(100 * primo / tentati, 1) if tentati else 0.0,
        }
    return {"flusso": _sessione["flusso_attivo"], "temi": risultato}


@app.get("/storico-fasce")
def storico_fasce():
    """
    Storico dei cambi di fascia del FLUSSO ATTIVO (per il grafico Elo nel tempo)
    e la sua fascia attuale.
    """
    _assicura_pronta()
    f = _flusso()
    return {
        "flusso": _sessione["flusso_attivo"],
        "storico_fasce": f["storico_fasce"],
        "elo_min": f["elo_min"],
        "elo_max": f["elo_max"],
    }


@app.get("/progressi")
def progressi():
    """
    Dati per la sezione "I miei progressi" del FLUSSO ATTIVO (SOLO lettura/conteggio):
      - "snapshot": serie storica della % al primo colpo nel tempo (grafico 1)
      - "tendenza": indicatore "stai migliorando?" sulla fascia Elo (indicatore 2)
      - "riepilogo": tabella riassuntiva del flusso
    Niente qui tocca la fascia governata dall'adattivita'.
    """
    _assicura_pronta()
    f = _flusso()
    return {
        "flusso": _sessione["flusso_attivo"],
        "snapshot": f["snapshot_progresso"],
        "tendenza": _calcola_tendenza(f["snapshot_progresso"]),
        "riepilogo": _riepilogo_progressi(f),
    }


@app.post("/scegli-tema/{tema}")
def scegli_tema(tema: str):
    """
    Attiva il flusso "temi" su un tema scelto liberamente. Cambia il flusso attivo
    a "temi" e ricostruisce la sua coda; il flusso "temi" mantiene la PROPRIA fascia
    Elo e la propria adattivita', indipendenti dal piano.
    """
    if tema not in TEMI_DISPONIBILI:
        return JSONResponse(status_code=404,
                            content={"errore": f"Tema sconosciuto: {tema}"})
    _assicura_pronta()
    # Attivo il flusso "temi" e ci lavoro.
    _sessione["flusso_attivo"] = "temi"
    f = _flusso("temi")
    f["tema_libero"] = tema
    # Nuova scelta di tema: riparto da una coda pulita per QUESTO flusso.
    f["coda"] = []
    f["serviti"] = 0
    esaurito = _riempi_coda_tema(f, TEMI_DISPONIBILI[tema])
    _salva_stato()
    logger.info("Flusso 'temi' attivato sul tema: %s", tema)
    risposta = {"flusso_attivo": "temi", "tema": tema,
                "messaggio": f"Allenamento focalizzato su: {tema}",
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
        "flusso_attivo": _sessione["flusso_attivo"],
    }


@app.get("/stato")
def stato():
    _assicura_pronta()
    f = _flusso()
    return {
        "giocatore": GIOCATORE,
        "flusso_attivo": _sessione["flusso_attivo"],
        "tema_libero": f["tema_libero"],
        "puzzle_totali": len(f["coda"]),
        "puzzle_serviti": f["serviti"],
        "rimanenti": len(f["coda"]) - f["serviti"],
    }


@app.get("/prossimo-puzzle")
def prossimo_puzzle():
    # Prepara la sessione alla prima richiesta.
    if not _sessione["pronta"]:
        if not _prepara_sessione():
            return JSONResponse(
                status_code=404,
                content={"errore": f"Nessun piano per {GIOCATORE}. "
                                   "Hai analizzato e arricchito le partite?"},
            )

    f = _flusso()
    idx = f["serviti"]
    if idx >= len(f["coda"]):
        risposta = {"fine": True, "flusso": _sessione["flusso_attivo"],
                    "messaggio": "Hai completato tutti i puzzle disponibili!"}
        if _sessione["flusso_attivo"] == "temi" and f["tema_libero"] is None:
            risposta["messaggio"] = "Scegli un tema per iniziare l'allenamento libero."
        if f["esaurito"]:
            risposta["esaurito"] = True
            risposta["suggerimento"] = (
                "I puzzle nuovi di questo tema sono esauriti, anche allargando la "
                "fascia di Elo. Prova a cambiare tema.")
        return risposta

    puzzle = f["coda"][idx]
    f["serviti"] += 1
    risposta = {
        "fine": False,
        "flusso": _sessione["flusso_attivo"],
        "numero": idx + 1,
        "totale": len(f["coda"]),
        "puzzle": puzzle,
        "esaurito": f["esaurito"],
    }
    if f["esaurito"]:
        risposta["suggerimento"] = (
            "I puzzle nuovi di questo tema stanno per finire, anche allargando la "
            "fascia di Elo. Valuta di cambiare tema.")
    return risposta
