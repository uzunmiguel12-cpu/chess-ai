"""
Modulo coda errori - SOLA LETTURA, NON usa Stockfish.

Scopo: trasformare i puzzle gia' validati in data/puzzle_errori.json nel formato
ESATTO che la coda del backend consuma (vedi api/server.py), salvando il
risultato in data/coda_errori.json. Da qui i puzzle-errore possono entrare nel
flusso di allenamento come qualunque altro puzzle.

FORMATO TARGET (un puzzle in coda, come in api/server.py): dizionario con i campi
  id, fen, moves, rating, themes, motivo_allenamento, fase_allenamento.

IL CAMPO "moves" (verificato in frontend/src/main.js, righe 128-136): il frontend
fa moves.split(' ') e gioca AUTOMATICAMENTE la PRIMA mossa (setup), poi la
soluzione che il giocatore deve trovare parte dalla SECONDA mossa. Quindi:
   - moves = "<mossa_setup_uci> <soluzione_uci>"
   - mossa_setup_uci = la mossa dell'avversario IMMEDIATAMENTE PRECEDENTE al mio
     errore, cioe' mosse[indice_mossa - 1]["move_uci"] nel file di analisi.
   - soluzione_uci = il campo soluzione_uci gia' presente nel puzzle validato.
   - fen = la posizione PRIMA della mossa di setup, cioe' mosse[indice_mossa - 1]
     ["fen"]. Cosi' quando il frontend gioca il setup si arriva esattamente alla
     posizione del mio errore (il vecchio "fen" del puzzle validato).

I dati della mossa precedente NON sono in puzzle_errori.json: vanno letti dal file
di analisi originale in data/analisi/<fonte_file>. Una VERIFICA DI COERENZA con
python-chess controlla che, applicando il setup al suo fen, si ottenga davvero il
fen del puzzle validato; in caso contrario il puzzle viene scartato (incoerente).

Uso:  python ml/coda_errori.py
"""

import os
import sys
import json
import logging

import chess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

PERCORSO_PUZZLE = os.path.join(
    os.path.dirname(__file__), "..", "data", "puzzle_errori.json"
)
CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)
PERCORSO_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "data", "coda_errori.json"
)

# --- Stima del rating (Elo IBRIDO, dichiaratamente APPROSSIMATIVO) ---------
# ATTENZIONE: questi numeri NON sono una misura reale di difficolta'. Sono una
# STIMA RUVIDA per dare ai puzzle-errore un Elo plausibile dentro la fascia di
# partenza, cosi' entrano nel flusso senza sballare le statistiche.
CENTRO_ELO = 1150          # punto medio della fascia di partenza
RATING_MIN = 1000          # clamp inferiore (CENTRO_ELO - 150)
RATING_MAX = 1300          # clamp superiore (CENTRO_ELO + 150)
# Mappatura del gap (centipawn) -> scostamento dal centro:
#   gap piccolo (~200)  => soluzione meno evidente => piu' DIFFICILE => rating ALTO
#   gap grande (>=600)  => soluzione lampante       => piu' FACILE   => rating BASSO
GAP_FACILE = 200           # estremo "difficile": +150 -> 1300
GAP_DIFFICILE = 600        # estremo "facile":    -150 -> 1000

# Campi costanti del formato coda per i puzzle-errore.
THEMES = "errore"
MOTIVO_ALLENAMENTO = "errore"   # serve alle statistiche-per-tema del flusso
FASE_ALLENAMENTO = None         # non inventiamo una fase: la deriveremo dopo


# --- Funzioni pure (testabili senza Stockfish) ---------------------------

def stima_rating(gap, era_matto):
    """
    STIMA RUVIDA (non una misura reale!) dell'Elo di un puzzle-errore.

    - Se era_matto: il matto e' riconoscibile => puzzle facile => rating basso,
      fissato a CENTRO_ELO - 150 = RATING_MIN.
    - Altrimenti mappatura LINEARE del gap: a GAP_FACILE (200) lo scostamento e'
      +150 (1300), a GAP_DIFFICILE (>=600) e' -150 (1000), interpolando in mezzo.
    Il risultato e' arrotondato a intero e clampato in [RATING_MIN, RATING_MAX].
    """
    if era_matto:
        return RATING_MIN

    # Interpolazione lineare: scostamento +150 a gap=200, -150 a gap=600.
    frazione = (gap - GAP_FACILE) / (GAP_DIFFICILE - GAP_FACILE)
    scostamento = 150 - 300 * frazione
    rating = CENTRO_ELO + scostamento
    rating = round(rating)
    # Clamp finale nella fascia ammessa.
    return max(RATING_MIN, min(RATING_MAX, rating))


def costruisci_moves(setup_uci, soluzione_uci):
    """
    Costruisce il campo "moves" del formato coda: la mossa di setup davanti e poi
    la soluzione, separate da uno spazio (il frontend gioca da solo la prima).
    """
    return f"{setup_uci} {soluzione_uci}"


def costruisci_id(fonte_file, indice_mossa):
    """
    ID univoco del puzzle-errore:
      "err_" + nome_file_senza_estensione + "_" + str(indice_mossa)
    es. fonte_file="mie_partite_0001.json", indice_mossa=16 -> "err_mie_partite_0001_16".
    """
    senza_estensione = os.path.splitext(fonte_file)[0]
    return f"err_{senza_estensione}_{indice_mossa}"


def recupera_setup(mosse, indice_mossa):
    """
    Recupera la mossa di setup (quella dell'avversario immediatamente precedente
    al mio errore) dalla lista di mosse del file di analisi di origine.

    Restituisce la coppia (setup_uci, fen_setup) presa da mosse[indice_mossa - 1],
    oppure None se l'indice precedente non esiste (es. errore alla prima mossa,
    senza nulla davanti da usare come setup).
    """
    indice_setup = indice_mossa - 1
    if indice_setup < 0 or indice_setup >= len(mosse):
        return None
    mossa = mosse[indice_setup]
    return mossa["move_uci"], mossa["fen"]


def verifica_coerenza(fen_setup, setup_uci, fen_atteso):
    """
    Coerenza con python-chess: applicando setup_uci a fen_setup si deve ottenere
    esattamente fen_atteso (la posizione del mio errore, cioe' il fen del puzzle
    validato). Restituisce True se coincide, False altrimenti (puzzle da scartare).
    Una mossa illegale o un FEN malformato contano come incoerenza (False).
    """
    try:
        board = chess.Board(fen_setup)
        mossa = chess.Move.from_uci(setup_uci)
        if mossa not in board.legal_moves:
            return False
        board.push(mossa)
    except ValueError:
        return False
    return board.fen() == fen_atteso


def trasforma_puzzle(puzzle, mosse_origine):
    """
    Trasforma un puzzle validato nel dizionario del formato coda, recuperando il
    setup dalle mosse del file di analisi di origine (mosse_origine).

    Restituisce la coppia (puzzle_coda, motivo_scarto):
      - se OK:        (dizionario_formato_coda, None)
      - se scartato:  (None, "<motivo>")  con motivo in {"setup_mancante", "incoerente"}
    """
    indice_mossa = puzzle["indice_mossa"]

    setup = recupera_setup(mosse_origine, indice_mossa)
    if setup is None:
        return None, "setup_mancante"
    setup_uci, fen_setup = setup

    # Il fen del puzzle validato e' la posizione del mio errore: deve risultare
    # applicando il setup al fen precedente, altrimenti il puzzle e' rotto.
    if not verifica_coerenza(fen_setup, setup_uci, puzzle["fen"]):
        return None, "incoerente"

    puzzle_coda = {
        "id": costruisci_id(puzzle["fonte_file"], indice_mossa),
        "fen": fen_setup,
        "moves": costruisci_moves(setup_uci, puzzle["soluzione_uci"]),
        "rating": stima_rating(puzzle["gap_centipawn"], puzzle["era_matto"]),
        "themes": THEMES,
        "motivo_allenamento": MOTIVO_ALLENAMENTO,
        "fase_allenamento": FASE_ALLENAMENTO,
    }
    return puzzle_coda, None


def istogramma_rating(ratings, larghezza_fascia=50):
    """
    Istogramma dei rating per fasce di larghezza_fascia (default 50). Restituisce
    una lista ordinata di triple (inizio_fascia, fine_fascia_esclusa, conteggio),
    solo per le fasce con almeno un puzzle.
    """
    if not ratings:
        return []
    conteggi = {}
    for r in ratings:
        fascia = (r // larghezza_fascia) * larghezza_fascia
        conteggi[fascia] = conteggi.get(fascia, 0) + 1
    return [(f, f + larghezza_fascia, conteggi[f]) for f in sorted(conteggi)]


# --- I/O e orchestrazione -------------------------------------------------

def carica_puzzle(percorso=PERCORSO_PUZZLE):
    """Carica i puzzle validati prodotti da valida_errori.py (--batch)."""
    with open(percorso, "r", encoding="utf-8") as f:
        return json.load(f)


def carica_mosse_origine(fonte_file, cache, cartella=CARTELLA_ANALISI):
    """
    Carica (con cache per nome file) la lista di mosse del file di analisi di
    origine. Restituisce la lista di mosse, oppure None se il file non esiste.
    La cache evita di rileggere lo stesso file di partita per piu' puzzle.
    """
    if fonte_file in cache:
        return cache[fonte_file]
    percorso = os.path.join(cartella, fonte_file)
    if not os.path.exists(percorso):
        cache[fonte_file] = None
        return None
    with open(percorso, "r", encoding="utf-8") as f:
        mosse = json.load(f).get("mosse", [])
    cache[fonte_file] = mosse
    return mosse


def costruisci_coda(puzzle_validati, cartella=CARTELLA_ANALISI):
    """
    Trasforma tutti i puzzle validati nel formato coda. Restituisce la coppia
    (coda, scarti) dove:
      - coda:   lista dei puzzle nel formato target;
      - scarti: dizionario {motivo: conteggio} dei puzzle scartati.
    """
    coda = []
    scarti = {"setup_mancante": 0, "incoerente": 0, "file_mancante": 0}
    cache = {}

    for puzzle in puzzle_validati:
        mosse_origine = carica_mosse_origine(puzzle["fonte_file"], cache, cartella)
        if mosse_origine is None:
            scarti["file_mancante"] += 1
            logger.warning("File di analisi mancante: %s (puzzle indice %s saltato)",
                           puzzle["fonte_file"], puzzle.get("indice_mossa"))
            continue

        puzzle_coda, motivo = trasforma_puzzle(puzzle, mosse_origine)
        if puzzle_coda is None:
            scarti[motivo] += 1
            continue
        coda.append(puzzle_coda)

    return coda, scarti


def salva_coda(coda, percorso=PERCORSO_OUTPUT):
    """Salva la coda nel formato target su file JSON."""
    os.makedirs(os.path.dirname(percorso), exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(coda, f, indent=2, ensure_ascii=False)


def _stampa_riepilogo(n_ingresso, coda, scarti, percorso):
    """Stampa a schermo conteggi, distribuzione dei rating e percorso del file."""
    ratings = [p["rating"] for p in coda]

    print()
    print("=== Coda errori: trasformazione nel formato del backend ===")
    print()
    print(f"  Puzzle in ingresso (validati)     : {n_ingresso}")
    print(f"  Trasformati con successo          : {len(coda)}")
    print(f"  Scartati per setup incoerente     : {scarti['incoerente']}")
    print(f"  Scartati per setup mancante (1a mossa) : {scarti['setup_mancante']}")
    print(f"  Scartati per file di analisi mancante  : {scarti['file_mancante']}")
    print()

    if ratings:
        media = sum(ratings) / len(ratings)
        print("  Distribuzione dei rating (STIMA ruvida):")
        print(f"    min={min(ratings)}  max={max(ratings)}  media={media:.1f}")
        print()
        print("    Istogramma per fasce di 50:")
        for inizio, fine, conteggio in istogramma_rating(ratings):
            barra = "#" * conteggio
            print(f"      {inizio:>4}-{fine - 1:<4} {conteggio:>4} {barra}")
        print()

    print(f"  Salvati {len(coda)} puzzle in {percorso}")
    print()


if __name__ == "__main__":
    logger.info("Carico i puzzle validati da: %s", PERCORSO_PUZZLE)
    if not os.path.exists(PERCORSO_PUZZLE):
        print(f"\nNessun file {PERCORSO_PUZZLE}: lancia prima la validazione batch.\n")
        sys.exit(1)

    puzzle_validati = carica_puzzle()
    logger.info("Caricati %d puzzle validati", len(puzzle_validati))

    coda, scarti = costruisci_coda(puzzle_validati)
    salva_coda(coda)
    logger.info("Salvati %d puzzle in coda su %s", len(coda), PERCORSO_OUTPUT)

    _stampa_riepilogo(len(puzzle_validati), coda, scarti, PERCORSO_OUTPUT)
