"""
Backend FastAPI (api) - serve i puzzle dell'allenamento, separati in FLUSSI.

Espone il "cervello" del sistema via web: il browser puo' chiedere il prossimo
puzzle da fare, e il server lo pesca dal flusso attivo.

Il sistema gestisce TRE flussi indipendenti (punto 1 della visione estesa):
  - "piano"  : puzzle dalle debolezze del profilo (piano automatico)
  - "temi"   : puzzle del tema scelto liberamente dall'utente
  - "errori" : puzzle dai propri errori (file coda_errori.json), completati da
               puzzle di rinforzo Lichess quando i propri errori si esauriscono

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
import glob
import random
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
from profilo import costruisci_profilo, TIPI_TATTICI, FASI  # noqa: E402

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
# Puzzle dai miei errori, gia' nel formato della coda (prodotti da ml/coda_errori.py).
# Il flusso "errori" usa di preferenza la versione ESTESA (sequenze multi-mossa,
# prodotte da ml/estendi_sequenze.py); se manca, ripiega sulla base da 1 mossa.
PERCORSO_CODA_ERRORI = os.path.join(_QUI, "..", "data", "coda_errori_estesa.json")
PERCORSO_CODA_ERRORI_BASE = os.path.join(_QUI, "..", "data", "coda_errori.json")
# Partite arricchite (una per file) da cui costruisci_profilo ricava il profilo.
# Stesso percorso del default di profilo.py; esplicito qui per poterlo reindirizzare
# nei test e per elencare i file ai fini dello SNAPSHOT NEL TEMPO (Tappa D).
PERCORSO_CATEGORIE = os.path.join(_QUI, "..", "data", "categorie")
# Storico degli snapshot del profilo (Tappa D): lista di fotografie nel tempo +
# l'ultimo confronto "partite nuove vs storico". Vedi _aggiorna_e_confronta.
PERCORSO_STORICO = os.path.join(_QUI, "..", "data", "storico_profili.json")
ELO_MIN = int(os.environ.get("CHESS_ELO_MIN", "1050"))
ELO_MAX = int(os.environ.get("CHESS_ELO_MAX", "1250"))

# --- I tre flussi indipendenti ---
# L'ordine e' anche quello di presentazione nel frontend.
FLUSSI = ("piano", "temi", "errori")
FLUSSO_DEFAULT = "piano"
# Flussi gia' implementati: tutti e tre (il flusso "errori" e' il punto 6 della visione).
FLUSSI_IMPLEMENTATI = ("piano", "temi", "errori")
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

# --- Parametri del REPORT DELLE CARENZE (punto 2 della visione) ---
# Un tema tattico e' "rilevante" solo se pesa almeno questa % sugli errori gravi;
# sotto soglia e' rumore statistico (es. infilata allo 0.1%) e NON va consigliato.
SOGLIA_RILEVANZA = 5.0
# Le fasi si considerano "vicine" (nessuna drammaticamente peggiore) se la forbice
# tra il tasso di errore piu' alto e quello piu' basso resta sotto questo divario.
DIVARIO_FASI_PICCOLO = 10.0

# --- Parametri dello SNAPSHOT NEL TEMPO (Tappa D del punto 2) ---
# Una tendenza e' "stabile" se il tasso si muove meno di questo (punti percentuali):
# sotto questa soglia il movimento e' rumore, non un vero miglioramento/peggioramento.
SOGLIA_STABILE = 0.5
# Guardrail anti-rumore: sotto questo numero di partite NUOVE il confronto e' marcato
# "non affidabile" (~1650 mosse a ~33 mosse/partita). E' un'EURISTICA DICHIARATA, non
# una soglia statistica formale: serve solo a non gridare al miglioramento su 5 partite.
GUARDRAIL_PARTITE = 50

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
    "snapshot_progresso", "tema_libero", "errori_attivo",
)


# Puzzle dai miei errori, caricati UNA volta in memoria all'avvio (sono pochi).
# Ogni voce e' gia' nel formato della coda (id, fen, moves, rating, themes,
# motivo_allenamento="errore", fase_allenamento). Il flusso "errori" li pesca da qui.
_PUZZLE_ERRORI = []


def _carica_puzzle_errori():
    """
    Carica in memoria i puzzle dai miei errori (una volta), preferendo la versione
    ESTESA con sequenze multi-mossa. Strategia a cascata:

    1. PERCORSO_CODA_ERRORI (esteso): se c'e' ed e' leggibile, lo usa.
    2. PERCORSO_CODA_ERRORI_BASE (1 mossa): fallback con warning se l'esteso manca
       o e' illeggibile, cosi' il flusso non parte vuoto inutilmente.
    3. Nessuno dei due: lista vuota + warning. Il flusso "errori" esistera' comunque,
       ma sara' subito "esaurito"/fallback (i puzzle si rimpiazzano con rinforzi
       Lichess in _riempi_coda_errori).
    """
    global _PUZZLE_ERRORI
    # 1. Prova prima il file esteso, poi il base.
    for percorso, etichetta in ((PERCORSO_CODA_ERRORI, "esteso"),
                                (PERCORSO_CODA_ERRORI_BASE, "base")):
        if not os.path.exists(percorso):
            continue
        try:
            with open(percorso, "r", encoding="utf-8") as fp:
                _PUZZLE_ERRORI = json.load(fp)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Impossibile caricare gli errori (%s) da %s.", e, percorso)
            continue
        if etichetta == "base":
            logger.warning("File errori esteso mancante (%s): ripiego sul file base "
                           "da 1 mossa (%s).", PERCORSO_CODA_ERRORI, percorso)
        logger.info("Caricati %d puzzle-errore (%s) da %s",
                    len(_PUZZLE_ERRORI), etichetta, percorso)
        return
    # 3. Nessun file utilizzabile.
    logger.warning("Nessun file errori utilizzabile (esteso %s, base %s): il flusso "
                   "errori parte vuoto.", PERCORSO_CODA_ERRORI, PERCORSO_CODA_ERRORI_BASE)
    _PUZZLE_ERRORI = []


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
        "errori_attivo": False,  # True quando si entra nel flusso "errori" (solo flusso "errori")
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

    # Carico una volta i puzzle dai miei errori (lista in memoria, vuota se manca il file).
    _carica_puzzle_errori()

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
                "origine": "lichess",  # uniformita': il campo c'e' sempre
            })
            _sessione["visti"].add(p["id"])
    fp["piano"] = piano
    fp["coda"] = coda
    fp["serviti"] = 0

    # Flusso "temi": se un tema era attivo (ripristinato da file), ricostruisci la coda.
    ft = _sessione["flussi"]["temi"]
    if ft["tema_libero"] in TEMI_DISPONIBILI:
        _riempi_coda_tema(ft, TEMI_DISPONIBILI[ft["tema_libero"]])

    # Flusso "errori": se era gia' attivo (ripristinato da file), ricostruisci la coda
    # come si fa per i temi con tema_libero.
    fe = _sessione["flussi"]["errori"]
    if fe["errori_attivo"]:
        _riempi_coda_errori(fe)

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
            "origine": "lichess",  # uniformita': il campo c'e' sempre
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


def _pesca_errori_righe(f, elo_max):
    """
    Pesca dai MIEI errori (_PUZZLE_ERRORI, in memoria) i puzzle NUOVI nella fascia
    [elo_min del flusso, elo_max], escludendo i visti GLOBALI. Mescola per varieta'
    (random a seed non fisso: e' runtime, va benissimo). `elo_max` puo' essere il
    tetto di base o uno allargato temporaneamente da _pesca_allargando.
    """
    visti = _sessione["visti"]  # GLOBALE tra i flussi
    candidati = [p for p in _PUZZLE_ERRORI
                 if f["elo_min"] <= p["rating"] <= elo_max and p["id"] not in visti]
    random.shuffle(candidati)
    return candidati[:PUZZLE_PER_BLOCCO]


def _riempi_coda_errori(f):
    """
    Riempie la coda del flusso "errori", gemella di _riempi_coda_tema:

    1. Pesca dai MIEI errori (_PUZZLE_ERRORI) nella fascia del flusso, allargando
       temporaneamente il tetto se scarseggiano (senza toccare la fascia di base).
       Questi puzzle sono marcati origine="errore", motivo_allenamento="errore".
    2. Se i miei errori nuovi non bastano a riempire PUZZLE_PER_BLOCCO, COMPLETA con
       puzzle di RINFORZO da Lichess (stessa fascia di base, esclusi i visti), marcati
       origine="lichess", motivo_allenamento="rinforzo". NON blocca mai: se anche
       Lichess non basta, serve quel che c'e'.

    Aggiunge gli id ai visti globali come fanno gli altri flussi e imposta f["esaurito"].
    """
    # 1. I miei errori, con allargamento temporaneo del tetto se scarseggiano.
    errori, _ = _pesca_allargando(
        f, lambda emax: _pesca_errori_righe(f, emax))
    nuova_coda = f["coda"][:f["serviti"]]  # tieni i gia' serviti
    for p in errori:
        nuova_coda.append({
            "id": p["id"], "fen": p["fen"], "moves": p["moves"],
            "rating": p["rating"], "themes": p["themes"],
            "motivo_allenamento": "errore",       # le statistiche-per-tema lo useranno
            "fase_allenamento": p.get("fase_allenamento"),
            "origine": "errore",                  # puzzle dai MIEI errori
            # Quante mosse "mie" richiede la soluzione (1/2/3): i puzzle estesi lo
            # portano, quelli base implicitamente 1. Serve al frontend per il badge.
            "lunghezza_soluzione": p.get("lunghezza_soluzione", 1),
        })
        _sessione["visti"].add(p["id"])

    # 2. Completamento con rinforzi Lichess se i miei errori nuovi non bastano.
    mancanti = PUZZLE_PER_BLOCCO - len(errori)
    n_rinforzi = 0
    if mancanti > 0:
        from raccomanda import raccomanda
        rinforzi = raccomanda(
            PERCORSO_DB, elo_min=f["elo_min"], elo_max=f["elo_max"],
            quanti=mancanti, escludi_id=list(_sessione["visti"]))
        for p in rinforzi:
            nuova_coda.append({
                "id": p["id"], "fen": p["fen"], "moves": p["moves"],
                "rating": p["rating"], "themes": p["themes"],
                "motivo_allenamento": "rinforzo",  # rinforzo, non un mio errore
                "fase_allenamento": None,
                "origine": "lichess",              # pescato dal DB Lichess
            })
            _sessione["visti"].add(p["id"])
            n_rinforzi += 1

    f["coda"] = nuova_coda
    # Esaurito solo se nemmeno i rinforzi bastano a dare puzzle nuovi a sufficienza.
    f["esaurito"] = (len(f["coda"]) - f["serviti"]) < PUZZLE_MINIMI
    logger.info("Coda errori riempita: %d dai miei errori + %d rinforzi Lichess "
                "(fascia base %d-%d)", len(errori), n_rinforzi,
                f["elo_min"], f["elo_max"])
    return f["esaurito"]


def _ricostruisci_coda_con_fascia(f):
    """
    Dopo un cambio di fascia del flusso `f`, ripesca i puzzle con la nuova fascia.
    Per il flusso "errori" ripesca dai miei errori (+ rinforzi); in modalita' tema
    libero ripesca quel tema; altrimenti i temi del piano.
    """
    # Flusso "errori": ripesca dai miei errori, completando con rinforzi Lichess.
    if f["errori_attivo"]:
        _riempi_coda_errori(f)
        return
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
                "origine": "lichess",  # uniformita': il campo c'e' sempre
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


# --- REPORT DELLE CARENZE (punto 2 della visione) ------------------------
# Arricchimento "di presentazione" del profilo: profilo.py resta puro (calcola
# conteggi, tassi per fase, percentuali tattiche). Qui ci aggiungiamo i tassi sulle
# MOSSE TOTALI, la classificazione dei temi per rilevanza, una sintesi onesta e la
# nota sul divario tra le fasi. Tutto a partire dai numeri reali, niente hardcoded.

def _tassi_su_mosse(profilo):
    """
    Per ogni tipo tattico (+ non_tattico): il tasso sulle MOSSE TOTALI ("ogni quante
    mosse commetti quel tipo di errore") e il "una ogni ~N mosse". Estratto perche'
    serve sia all'arricchimento del profilo sia agli snapshot nel tempo (Tappa D).
    Restituisce (tasso_per_tipo, ogni_quante_per_tipo).
    """
    mosse_totali = profilo.get("mosse_totali", 0)
    conteggio_tattico = profilo.get("conteggio_tattico", {})
    tasso = {}
    ogni = {}
    for tipo in list(TIPI_TATTICI) + ["non_tattico"]:
        n = conteggio_tattico.get(tipo, 0)
        tasso[tipo] = round(100 * n / mosse_totali, 1) if mosse_totali else 0.0
        ogni[tipo] = round(mosse_totali / n) if n > 0 else None
    return tasso, ogni


def _fase_dominante_tipo(profilo, tipo):
    """Fase in cui un tipo tattico compare di piu' (da tattico_per_fase). None se
    quel tipo non ha occorrenze per fase."""
    per_fase = profilo.get("tattico_per_fase", {}).get(tipo, {})
    if not per_fase:
        return None
    return max(per_fase, key=per_fase.get)


def _sintesi_carenze(profilo, tasso_su_mosse, ogni_quante_mosse,
                     temi_rilevanti, temi_non_rilevanti):
    """
    Compone 1-3 frasi ONESTE dai numeri del profilo (mai hardcodate):
      - il tipo di errore dominante (tasso_su_mosse piu' alto tra i rilevanti) e in
        quale fase si concentra;
      - il secondo tema rilevante, se c'e';
      - che i temi sotto-soglia (es. inchiodatura/infilata) NON sono un problema;
      - che la quota non_tattico e' posizionale/strategica e NON e' allenabile coi
        puzzle tattici (gancio onesto verso le diagnosi profonde, punto 5).
    Se mancano dati, le parti relative si omettono invece di inventare.
    """
    def etichetta(tipo):
        return tipo.replace("_", " ")

    frasi = []
    # Temi rilevanti ordinati per tasso sulle mosse, decrescente.
    rilevanti_ordinati = sorted(
        temi_rilevanti, key=lambda t: tasso_su_mosse.get(t, 0.0), reverse=True)

    if rilevanti_ordinati:
        dominante = rilevanti_ordinati[0]
        fase_dom = _fase_dominante_tipo(profilo, dominante)
        ogni = ogni_quante_mosse.get(dominante)
        pezzo = (f"Il tuo errore tattico piu' frequente e' «{etichetta(dominante)}» "
                 f"({tasso_su_mosse.get(dominante, 0.0)}% delle mosse")
        if ogni:
            pezzo += f", una ogni ~{ogni} mosse"
        pezzo += ")"
        if fase_dom:
            pezzo += f", soprattutto in {fase_dom}"
        frasi.append(pezzo + ".")
        if len(rilevanti_ordinati) >= 2:
            secondo = rilevanti_ordinati[1]
            frasi.append(f"Segue «{etichetta(secondo)}» "
                         f"({tasso_su_mosse.get(secondo, 0.0)}% delle mosse).")
    else:
        frasi.append("Nessun tipo tattico spicca come problema ricorrente.")

    # I temi sotto-soglia: onestamente, non sono un problema per questo giocatore.
    if temi_non_rilevanti:
        elenco = ", ".join(etichetta(t) for t in temi_non_rilevanti)
        frasi.append(f"Invece {elenco} non sono un problema per te: troppo rari "
                     f"per valere un allenamento dedicato.")

    # Quota non_tattico: posizionale/strategica, non coperta dai puzzle tattici.
    perc_non_tattico = profilo.get("percentuali_tattico", {}).get("non_tattico", 0.0)
    if perc_non_tattico > 0:
        frasi.append(f"Attenzione: il {perc_non_tattico}% dei tuoi errori gravi e' "
                     f"posizionale/strategico, non tattico: i puzzle tattici non lo "
                     f"allenano (servira' una diagnosi piu' profonda).")

    return " ".join(frasi)


def _piano_studio(profilo, tasso_su_mosse, ogni_quante_mosse, temi_rilevanti):
    """
    PIANO DI STUDIO PERSONALIZZATO (Tappa C del punto 2): la parte AZIONABILE del
    report. E' STATICO (una foto del profilo attuale, non una misura di progresso:
    quella sara' la Tappa D) ed e' ONESTO: espone PESI RELATIVI e priorita'
    qualitative, MAI minuti ne' percentuali assolute di tempo (sarebbero finte).

      - Considera solo i temi tattici RILEVANTI (>= SOGLIA_RILEVANZA): i sotto-soglia
        (es. inchiodatura/infilata troppo rari) NON entrano nel piano.
      - "Peso grezzo" di un tema = il suo tasso_su_mosse; il peso_relativo lo
        normalizza sul tema dominante (dominante = 1.0, gli altri una frazione).
      - Priorita': "alta" al dominante; per gli altri "media" se peso_relativo >= 0.5,
        "bassa" se < 0.5.
      - Ogni voce porta il "tema_libero" corrispondente (pezzo_in_presa, forchetta, ...)
        cosi' il frontend puo' agganciarci i pulsanti del flusso temi.
    Restituisce {voci, progressione, nota_posizionale}.
    """
    def etichetta(tipo):
        return tipo.replace("_", " ")

    # La quota posizionale/strategica: serve sia alla nota normale sia al caso limite.
    perc_non_tattico = profilo.get("percentuali_tattico", {}).get("non_tattico", 0.0)

    # 6. CASO LIMITE: nessun tema rilevante (improbabile sui dati reali). Niente piano,
    #    ma un messaggio neutro e onesto invece di crashare.
    if not temi_rilevanti:
        return {
            "voci": [],
            "progressione": "",
            "nota_posizionale": (
                f"Nessun tema tattico spicca abbastanza da costruire un piano: "
                f"il {perc_non_tattico}% dei tuoi errori gravi e' posizionale/"
                f"strategico e va oltre i puzzle tattici (serve una diagnosi piu' "
                f"profonda, punto 5 della visione)."),
        }

    conteggio_tattico = profilo.get("conteggio_tattico", {})

    # 1-2. Ordino i rilevanti per tasso sulle mosse, decrescente: il primo e' il
    #      tema dominante, sul quale normalizzo i pesi relativi.
    rilevanti_ordinati = sorted(
        temi_rilevanti, key=lambda t: tasso_su_mosse.get(t, 0.0), reverse=True)
    dominante = rilevanti_ordinati[0]
    tasso_dominante = tasso_su_mosse.get(dominante, 0.0) or 1.0  # guardia anti /0

    # 3. Le voci del piano, dal dominante in giu'.
    voci = []
    for i, tipo in enumerate(rilevanti_ordinati):
        tasso = tasso_su_mosse.get(tipo, 0.0)
        rapporto = tasso / tasso_dominante          # grezzo, per decidere la priorita'
        peso_relativo = round(rapporto, 1)          # esposto, a 1 decimale
        if i == 0:
            priorita = "alta"                        # il dominante
        elif rapporto >= 0.5:
            priorita = "media"
        else:
            priorita = "bassa"
        voci.append({
            "tema": tipo,
            # Tema-libero del frontend (i TIPI_TATTICI coincidono coi nomi dei temi
            # liberi); None se un tipo non avesse un tema allenabile corrispondente.
            "tema_libero": tipo if tipo in TEMI_DISPONIBILI else None,
            "conteggio": conteggio_tattico.get(tipo, 0),
            "tasso_su_mosse": tasso,
            "ogni_quante_mosse": ogni_quante_mosse.get(tipo),
            "peso_relativo": peso_relativo,
            "priorita": priorita,
        })

    # 4. PROGRESSIONE: consiglio di METODO (statico), generato dai temi reali.
    if len(rilevanti_ordinati) >= 2:
        secondo = rilevanti_ordinati[1]
        progressione = (
            f"Inizia da «{etichetta(dominante)}» finche' non lo senti piu' solido, "
            f"poi alterna con «{etichetta(secondo)}» per non trascurarlo.")
    else:
        # Un solo tema rilevante: adatto il testo, niente "secondo tema".
        progressione = (
            f"Concentrati su «{etichetta(dominante)}»: e' l'unico tema che pesa "
            f"abbastanza da meritare un allenamento dedicato adesso.")

    # 5. NOTA POSIZIONALE: disclaimer onesto sul fatto che il piano copre SOLO i temi
    #    tattici dei puzzle; cita la percentuale non_tattico reale (gancio al punto 5).
    nota_posizionale = (
        f"Questo piano copre solo i temi tattici allenabili coi puzzle. "
        f"Il {perc_non_tattico}% dei tuoi errori gravi e' posizionale/strategico: "
        f"resta fuori dai puzzle e va affrontato a parte (diagnosi piu' profonda, "
        f"punto 5 della visione).")

    return {
        "voci": voci,
        "progressione": progressione,
        "nota_posizionale": nota_posizionale,
    }


def _arricchisci_profilo(profilo, confronto=None):
    """
    Arricchisce il profilo puro (output di costruisci_profilo) con i dati del REPORT
    DELLE CARENZE: tassi sulle mosse totali, temi rilevanti/non rilevanti, sintesi
    onesta, nota sul divario tra le fasi e PIANO DI STUDIO azionabile. Restituisce una
    copia arricchita; non modifica ne' il profilo originale ne' profilo.py.

    `confronto` (Tappa D, opzionale) e' l'esito di _aggiorna_e_confronta: se presente
    viene esposto nel campo "confronto" e le sue tendenze annotano le voci del piano.
    """
    percentuali_tattico = profilo.get("percentuali_tattico", {})

    # 1. TASSO SUL DENOMINATORE "MOSSE TOTALI" (non sulle occasioni!): e' "ogni
    #    quante mosse commetti quel tipo di errore", NON "quante occasioni hai
    #    mancato". Aggiungiamo anche "una ogni ~N mosse" (mosse_totali / conteggio).
    tasso_su_mosse_per_tipo, ogni_quante_mosse_per_tipo = _tassi_su_mosse(profilo)

    # 2. RILEVANZA: un tema tattico conta solo se pesa >= SOGLIA_RILEVANZA % sugli
    #    errori gravi; sotto soglia e' rumore statistico e non va consigliato.
    temi_rilevanti = []
    temi_non_rilevanti = []
    for tipo in TIPI_TATTICI:
        perc = percentuali_tattico.get(tipo, 0.0)
        if perc >= SOGLIA_RILEVANZA:
            temi_rilevanti.append(tipo)
        else:
            temi_non_rilevanti.append(tipo)

    # 4. DIVARIO TRA LE FASI: se i tassi per fase sono vicini, non far sembrare una
    #    fase drammaticamente peggiore. Considero solo le fasi con mosse giocate.
    tasso_per_fase = profilo.get("tasso_errore_per_fase", {})
    mosse_per_fase = profilo.get("mosse_per_fase", {})
    tassi_validi = [tasso_per_fase[f] for f in FASI
                    if mosse_per_fase.get(f, 0) > 0 and f in tasso_per_fase]
    if len(tassi_validi) >= 2:
        fasi_divario = round(max(tassi_validi) - min(tassi_validi), 1)
        fasi_divario_piccolo = fasi_divario < DIVARIO_FASI_PICCOLO
    else:
        # Una sola fase con dati (o nessuna): nessun confronto sensato -> "vicine".
        fasi_divario = 0.0
        fasi_divario_piccolo = True

    # 3. SINTESI onesta, generata dai numeri appena calcolati.
    sintesi = _sintesi_carenze(profilo, tasso_su_mosse_per_tipo,
                               ogni_quante_mosse_per_tipo,
                               temi_rilevanti, temi_non_rilevanti)

    # 5. PIANO DI STUDIO (Tappa C): la parte azionabile, dai soli temi rilevanti.
    piano_studio = _piano_studio(profilo, tasso_su_mosse_per_tipo,
                                 ogni_quante_mosse_per_tipo, temi_rilevanti)

    # 6. TENDENZA (Tappa D): se c'e' un confronto, annoto ogni voce del piano con la
    #    tendenza del suo tema (migliorato/peggiorato/stabile) sulle partite recenti.
    if confronto and confronto.get("voci"):
        tendenza_per_tema = {v["tema"]: v["tendenza"]
                             for v in confronto["voci"] if "tema" in v}
        for voce in piano_studio.get("voci", []):
            if voce["tema"] in tendenza_per_tema:
                voce["tendenza"] = tendenza_per_tema[voce["tema"]]

    arricchito = dict(profilo)  # copia: il profilo originale resta intatto
    arricchito.update({
        "tasso_su_mosse_per_tipo": tasso_su_mosse_per_tipo,
        # Esplicito perche' il tasso NON inganni: il denominatore e' mosse_totali.
        "tasso_su_mosse_denominatore": "mosse_totali",
        "ogni_quante_mosse_per_tipo": ogni_quante_mosse_per_tipo,
        "temi_rilevanti": temi_rilevanti,
        "temi_non_rilevanti": temi_non_rilevanti,
        "soglia_rilevanza": SOGLIA_RILEVANZA,
        "fasi_divario": fasi_divario,
        "fasi_divario_piccolo": fasi_divario_piccolo,
        "sintesi": sintesi,
        "piano_studio": piano_studio,
        # Confronto "partite nuove vs storico" (Tappa D); None se non disponibile.
        "confronto": confronto,
    })
    return arricchito


# --- SNAPSHOT DEL PROFILO NEL TEMPO + confronto (Tappa D del punto 2) -----
# PRINCIPIO ANTI-DILUIZIONE: il profilo cumulativo nasconde i miglioramenti (100
# partite nuove su 3300 spostano i tassi in modo impercettibile). Quindi il confronto
# ONESTO e': profilo delle SOLE partite nuove vs lo snapshot storico precedente. MAI
# cumulativo vs cumulativo. Tutto qui e' a SOLA LETTURA rispetto all'allenamento:
# non tocca flussi, code o adattivita' (principio di non-interferenza).
#
# Lo storico (data/storico_profili.json) e' {"snapshot": [...], "ultimo_confronto": ...}.
# Per non gonfiare il file, "file_inclusi" (l'elenco dei file di data/categorie) viene
# tenuto SOLO nell'ultimo snapshot: e' l'unico che serve per rilevare le partite nuove;
# gli snapshot piu' vecchi conservano solo i tassi, che e' tutto cio' che il confronto
# usa di loro.

def _elenco_file_categorie(cartella):
    """Nomi (basename) dei file partita presenti nella cartella, ordinati. [] se la
    cartella non esiste."""
    if not os.path.isdir(cartella):
        return []
    return sorted(os.path.basename(p)
                  for p in glob.glob(os.path.join(cartella, "*.json")))


def _carica_storico():
    """Storico degli snapshot. Struttura sempre valida anche se il file manca o e'
    illeggibile (riparto da storico vuoto, senza crashare)."""
    vuoto = {"snapshot": [], "ultimo_confronto": None}
    if not os.path.exists(PERCORSO_STORICO):
        return vuoto
    try:
        with open(PERCORSO_STORICO, "r", encoding="utf-8") as fp:
            dato = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Storico profili illeggibile (riparto vuoto): %s", e)
        return vuoto
    # Difesa minima sul formato: garantisco le chiavi attese.
    dato.setdefault("snapshot", [])
    dato.setdefault("ultimo_confronto", None)
    return dato


def _salva_storico(storico):
    """Salvataggio atomico dello storico (scrive su .tmp e rinomina)."""
    try:
        tmp = PERCORSO_STORICO + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(storico, fp, ensure_ascii=False, indent=2)
        os.replace(tmp, PERCORSO_STORICO)
    except OSError as e:
        logger.warning("Impossibile salvare lo storico profili: %s", e)


def _snapshot_da_profilo(profilo, file_inclusi, profilo_periodo=None):
    """
    Fotografia compatta del profilo: solo i tassi che servono al confronto, piu'
    timestamp, conteggi e l'elenco dei file inclusi (per rilevare i nuovi).

    I tassi del corpo (tasso_errore_per_fase, tasso_su_mosse_per_tipo, ...) sono
    CUMULATIVI: descrivono tutto lo storico, e servono al confronto della Tappa D.

    Se `profilo_periodo` e' fornito (il profilo delle SOLE partite NUOVE di questo
    snapshot, gia' calcolato in _aggiorna_e_confronta), salva ANCHE i tassi DEL
    PERIODO (campi periodo_*), coerenti col principio anti-diluizione: sono i tassi
    delle sole partite nuove, non i cumulativi, ed e' su questi che si costruisce il
    grafico dell'evoluzione nel tempo (/storico-profili). Lo snapshot BASE (il primo,
    senza partite nuove proprie) NON ha questi campi: non rappresenta un periodo nuovo.
    """
    tasso_su_mosse, _ = _tassi_su_mosse(profilo)
    snap = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "partite": profilo.get("partite_analizzate", 0),
        "mosse": profilo.get("mosse_totali", 0),
        "tasso_errore_per_fase": dict(profilo.get("tasso_errore_per_fase", {})),
        "tasso_su_mosse_per_tipo": tasso_su_mosse,
        "percentuali_tattico": dict(profilo.get("percentuali_tattico", {})),
        "file_inclusi": list(file_inclusi),
    }
    if profilo_periodo is not None:
        periodo_tasso_su_mosse, _ = _tassi_su_mosse(profilo_periodo)
        periodo_partite = profilo_periodo.get("partite_analizzate", 0)
        snap.update({
            "periodo_partite": periodo_partite,
            "periodo_tasso_su_mosse_per_tipo": periodo_tasso_su_mosse,
            "periodo_tasso_errore_per_fase": dict(
                profilo_periodo.get("tasso_errore_per_fase", {})),
            # Stesso guardrail anti-rumore del confronto (Tappa D): poche partite
            # nel periodo -> punto "indicativo, non conclusivo".
            "periodo_affidabile": periodo_partite >= GUARDRAIL_PARTITE,
        })
    return snap


def _voce_confronto(genere, nome, tasso_storico, tasso_recente):
    """
    Una voce di confronto per un tema o una fase: delta = recente - storico (un tasso
    d'errore che SCENDE = miglioramento). "stabile" se |delta| < SOGLIA_STABILE.
    La chiave del nome e' "tema" o "fase" a seconda del genere.
    """
    delta = round(tasso_recente - tasso_storico, 1)
    if abs(delta) < SOGLIA_STABILE:
        tendenza = "stabile"
    elif delta < 0:
        tendenza = "migliorato"   # meno errori di prima
    else:
        tendenza = "peggiorato"
    voce = {
        genere: nome,             # chiave "tema" o "fase"
        "tasso_storico": tasso_storico,
        "tasso_recente": tasso_recente,
        "delta": delta,
        "tendenza": tendenza,
    }
    return voce


def _confronto(profilo_recente, snapshot_storico):
    """
    Confronto ONESTO "partite nuove vs storico": per ogni tipo tattico RILEVANTE nel
    profilo recente e per ogni fase, mette a confronto il tasso recente con quello
    dello snapshot storico precedente. GUARDRAIL: se le partite nuove sono meno di
    GUARDRAIL_PARTITE il confronto e' marcato "affidabile": false (con avvertenza),
    ma le tendenze si mostrano comunque (indicative, non conclusive).
    """
    partite_nuove = profilo_recente.get("partite_analizzate", 0)
    affidabile = partite_nuove >= GUARDRAIL_PARTITE

    tasso_recente_tipo, _ = _tassi_su_mosse(profilo_recente)
    tasso_storico_tipo = snapshot_storico.get("tasso_su_mosse_per_tipo", {})
    perc_recente = profilo_recente.get("percentuali_tattico", {})

    voci = []
    # Temi tattici: solo i RILEVANTI nelle partite recenti (>= soglia).
    for tipo in TIPI_TATTICI:
        if perc_recente.get(tipo, 0.0) < SOGLIA_RILEVANZA:
            continue
        voci.append(_voce_confronto(
            "tema", tipo,
            tasso_storico_tipo.get(tipo, 0.0),
            tasso_recente_tipo.get(tipo, 0.0)))

    # Fasi: tutte e tre (il "dove" sbagli e' sempre informativo).
    tasso_storico_fase = snapshot_storico.get("tasso_errore_per_fase", {})
    tasso_recente_fase = profilo_recente.get("tasso_errore_per_fase", {})
    for fase in FASI:
        voci.append(_voce_confronto(
            "fase", fase,
            tasso_storico_fase.get(fase, 0.0),
            tasso_recente_fase.get(fase, 0.0)))

    confronto = {
        "partite_nuove": partite_nuove,
        "affidabile": affidabile,
        "voci": voci,
    }
    if not affidabile:
        confronto["avvertenza"] = (
            f"Confronto basato su poche partite ({partite_nuove} < "
            f"{GUARDRAIL_PARTITE}): indicativo, non conclusivo.")
    return confronto


def _aggiorna_e_confronta(profilo_cumulativo, cartella):
    """
    RILEVAZIONE PIGRA dei file nuovi + confronto onesto (Tappa D). A sola lettura
    rispetto all'allenamento. Restituisce il confronto da esporre (o None) e lo
    aggiorna su disco solo quando ci sono davvero partite nuove.

      - Nessuno snapshot: crea lo snapshot-base col profilo cumulativo e tutti i file;
        confronto None (non c'e' ancora niente con cui confrontare).
      - File nuovi: costruisce il profilo delle SOLE partite nuove (anti-diluizione!)
        e lo confronta con l'ultimo snapshot; poi salva un nuovo snapshot cumulativo.
      - Nessun file nuovo: restituisce l'ultimo confronto salvato, senza ricalcolare
        ne' creare snapshot duplicati.
    """
    storico = _carica_storico()
    snapshots = storico["snapshot"]
    file_presenti = _elenco_file_categorie(cartella)

    # Primo avvio: nessuno snapshot -> creo la base, nessun confronto possibile.
    if not snapshots:
        snapshots.append(_snapshot_da_profilo(profilo_cumulativo, file_presenti))
        storico["ultimo_confronto"] = None
        _salva_storico(storico)
        return None

    ultimo = snapshots[-1]
    file_storici = set(ultimo.get("file_inclusi", []))
    file_nuovi = [f for f in file_presenti if f not in file_storici]

    # Niente di nuovo: riuso l'ultimo confronto, nessuna scrittura.
    if not file_nuovi:
        return storico.get("ultimo_confronto")

    # Profilo delle SOLE partite nuove vs lo snapshot storico (il cuore anti-diluizione).
    profilo_nuove = costruisci_profilo(GIOCATORE, cartella=cartella,
                                       solo_file=file_nuovi)
    if profilo_nuove is None:
        # I file nuovi non contengono partite del giocatore: aggiorno solo l'elenco
        # file dell'ultimo snapshot (cosi' non li riconsidero) senza inventare un
        # confronto, e tengo l'ultimo confronto valido.
        ultimo["file_inclusi"] = file_presenti
        _salva_storico(storico)
        return storico.get("ultimo_confronto")

    confronto = _confronto(profilo_nuove, ultimo)

    # Nuovo snapshot cumulativo. Tengo file_inclusi SOLO sull'ultimo: lo tolgo dal
    # precedente per non gonfiare il file con elenchi ripetuti. Passo anche il profilo
    # delle SOLE partite nuove (profilo_nuove): lo snapshot salva cosi' i tassi DEL
    # PERIODO (campi periodo_*) per il grafico anti-diluizione di /storico-profili.
    ultimo.pop("file_inclusi", None)
    snapshots.append(_snapshot_da_profilo(profilo_cumulativo, file_presenti,
                                          profilo_periodo=profilo_nuove))
    storico["ultimo_confronto"] = confronto
    _salva_storico(storico)
    return confronto


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
    Cambia il flusso attivo. Per il flusso "errori" (punto 6 della visione), alla
    prima attivazione segna errori_attivo=True e riempie la coda dai miei errori
    (completati da rinforzi Lichess). La forma della risposta e' uguale per tutti i flussi.
    """
    if nome not in FLUSSI:
        return JSONResponse(status_code=404,
                            content={"errore": f"Flusso sconosciuto: {nome}"})
    _assicura_pronta()
    _sessione["flusso_attivo"] = nome
    f = _flusso(nome)
    # Flusso "errori": attivalo e (se serve) riempi la coda dai miei errori.
    if nome == "errori":
        primo_ingresso = not f["errori_attivo"]
        f["errori_attivo"] = True
        # Riempi alla prima attivazione o quando non restano piu' puzzle da servire.
        if primo_ingresso or (len(f["coda"]) - f["serviti"]) <= 0:
            _riempi_coda_errori(f)
    _salva_stato()
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


@app.get("/profilo")
def profilo_carenze():
    """
    REPORT DELLE CARENZE (punto 2 della visione): espone il profilo di debolezze
    gia' calcolato da costruisci_profilo, ARRICCHITO (vedi _arricchisci_profilo) con
    i tassi sulle mosse totali, la classificazione dei temi per rilevanza, una sintesi
    onesta, la nota sul divario tra le fasi, il PIANO DI STUDIO (Tappa C) e il CONFRONTO
    "partite nuove vs storico" (Tappa D). Non costruisce piano o coda: e' una pura
    diagnosi a sola lettura dalle partite analizzate.
    """
    profilo = costruisci_profilo(GIOCATORE, cartella=PERCORSO_CATEGORIE)
    if profilo is None:
        return JSONResponse(
            status_code=404,
            content={"errore": f"Nessun profilo per {GIOCATORE}. "
                               "Hai analizzato e arricchito le partite?"},
        )
    # Rilevazione pigra delle partite nuove + confronto onesto (vedi Tappa D).
    confronto = _aggiorna_e_confronta(profilo, PERCORSO_CATEGORIE)
    return _arricchisci_profilo(profilo, confronto=confronto)


@app.get("/storico-profili")
def storico_profili():
    """
    SERIE TEMPORALE dell'evoluzione dei tassi d'errore nel tempo, per il grafico
    "Evoluzione nel tempo" (raffinamento del punto 4, sotto le carenze).

    PRINCIPIO ANTI-DILUIZIONE (Tappa D): ogni punto porta i tassi DEL PERIODO (le
    sole partite nuove di quello snapshot), NON i cumulativi: e' cosi' che si vede il
    miglioramento vero, senza la diluizione del totale storico. Include percio' SOLO
    gli snapshot che hanno i campi periodo_* (salta lo snapshot BASE, che non
    rappresenta un periodo nuovo). Ordina per timestamp.

    "ha_dati" e' True con >= 1 punto-periodo (cioe' >= 2 snapshot totali): sotto questa
    soglia il frontend mostra uno stato vuoto onesto invece di un grafico con un solo
    punto. SOLO lettura rispetto all'allenamento.
    """
    storico = _carica_storico()
    punti = []
    for snap in storico.get("snapshot", []):
        # Salto il base e ogni snapshot senza i tassi di periodo.
        if "periodo_tasso_su_mosse_per_tipo" not in snap:
            continue
        punti.append({
            "timestamp": snap.get("timestamp"),
            "periodo_partite": snap.get("periodo_partite", 0),
            "affidabile": snap.get("periodo_affidabile", False),
            "tasso_tipo": dict(snap.get("periodo_tasso_su_mosse_per_tipo", {})),
            "tasso_fase": dict(snap.get("periodo_tasso_errore_per_fase", {})),
        })
    punti.sort(key=lambda p: p["timestamp"] or "")
    return {"punti": punti, "ha_dati": len(punti) >= 1}


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
