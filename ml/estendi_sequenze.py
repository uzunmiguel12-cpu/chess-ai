"""
Modulo estensione sequenze - USA Stockfish (come valida_errori.py).

A differenza di estrai_errori.py / coda_errori.py (sola lettura), questo modulo
apre il motore.

Scopo: prendere i puzzle-errore gia' in coda (data/coda_errori.json, formato del
backend) ed ESTENDERLI da 1 sola mossa a SEQUENZE FORZATE multi-mossa. Si allunga
ogni puzzle finche' la continuazione resta forzata su ENTRAMBI i lati (avversario
e mio); alcuni puzzle resteranno da 1 mossa (giusto cosi'), altri diventeranno da
2 o 3 mosse mie.

FORMATO DEL PUZZLE IN INGRESSO (data/coda_errori.json):
  - "moves" = "<setup> <soluzione>": 2 mosse UCI. La prima e' il setup giocato
    dall'avversario, la seconda e' la mia mossa-soluzione gia' validata.
  - "fen" = la posizione PRIMA del setup. La posizione DEL PUZZLE (dove devo
    trovare la mossa) si ottiene applicando il setup al fen.

ESTENSIONE (a partire dalla posizione del puzzle, dopo il setup):
  - la sequenza-soluzione parte con la mia mossa gia' validata (la 2a di "moves");
  - poi alterna: risposta avversario -> mia mossa -> ... fino al TETTO di 3 MOSSE
    MIE in totale (al massimo ~5 semimosse di soluzione: mia, avv, mia, avv, mia);
  - profondita' di analisi 18 (come la Tappa 2), MultiPV=2;
  - soglia di forzatura ASIMMETRICA: gap >= 200 cp per le MIE mosse (--gap-mio)
    e gap >= 100 cp per le RISPOSTE dell'avversario (--gap-avv). Il vecchio --gap
    unico resta accettato (retrocompat): se passato, vale per ENTRAMBE le soglie.

REGOLA DI FORZATURA (vedi passo_avversario / passo_mio):
  - turno AVVERSARIO: analizzo dal suo punto di vista. Se la sua mossa migliore e'
    nettamente forzata (gap >= soglia) OPPURE e' costretto (una sola mossa legale /
    matto inevitabile), GIOCO quella mossa e continuo; altrimenti FERMO (ha scelta).
  - turno MIO: analizzo dal mio punto di vista. Se ho una mossa nettamente migliore
    (gap >= soglia, o matto vincente, o unica), la AGGIUNGO e continuo; altrimenti
    FERMO (avrei scelta -> niente "indovina quale").
  - Una risposta dell'avversario viene tenuta SOLO se e' seguita da una mia mossa
    forzata: la soluzione finisce sempre su una MIA mossa, mai su quella avversaria.

CASI DI STOP aggiuntivi:
  - Matto forzato: includo le mosse fino al matto, poi stop.
  - Posizione gia' decisa: se la mia valutazione supera +800 cp E non c'e' una
    continuazione di matto chiara, mi fermo (no accanimento su posizione vinta).
  - Raggiunto il tetto di 3 mosse mie / nessuna mossa legale: stop.

Due modalita' (come valida_errori.py):
  - CAMPIONE (default): processa N puzzle (mescolati con seed fisso), NON salva e
    stampa una tabella di taratura (distribuzione delle lunghezze, tempi, stima).
        python ml/estendi_sequenze.py --campione 100 --profondita 18
  - BATCH (--batch): processa TUTTI i puzzle, salva data/coda_errori_estesa.json
    con salvataggio incrementale e ripartenza (sidecar di progresso).
        python ml/estendi_sequenze.py --batch --profondita 18 --gap-mio 200 --gap-avv 100
"""

import os
import sys
import json
import time
import random
import logging
import argparse

import chess
import chess.engine

# Aggiungiamo engine/ e ml/ al percorso per riusare la configurazione del motore
# e le utility del modulo fratello valida_errori.
CARTELLA_ENGINE = os.path.join(os.path.dirname(__file__), "..", "engine")
CARTELLA_ML = os.path.dirname(__file__)
for _cartella in (CARTELLA_ENGINE, CARTELLA_ML):
    if _cartella not in sys.path:
        sys.path.insert(0, _cartella)

# Riusiamo la costante del motore e, da valida_errori, le utility gia' scritte per
# l'analisi MultiPV e il calcolo del gap (turno dal FEN, eval dal lato di chi
# muove, estrazione di una linea, gap, formattazione dei tempi).
from analisi_database import PERCORSO_STOCKFISH  # noqa: E402
from valida_errori import (  # noqa: E402
    turno_da_fen,
    eval_lato_mossa,
    estrai_linea,
    calcola_gap,
    formatta_durata,
    stima_tempo_totale,
    SOGLIA_MATTO,
    GAP_MATTO,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

PERCORSO_CODA = os.path.join(
    os.path.dirname(__file__), "..", "data", "coda_errori.json"
)
# File del batch: la coda estesa e il sidecar di progresso per la ripartenza.
PERCORSO_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "data", "coda_errori_estesa.json"
)
PERCORSO_PROGRESSO = os.path.join(
    os.path.dirname(__file__), "..", "data", "coda_errori_estesa.progress.json"
)

# Parametri di default dell'estensione.
PROFONDITA_DEFAULT = 18         # come la Tappa 2
# Soglie di forzatura ASIMMETRICHE (centipawn): l'avversario, dovendo solo
# difendersi, e' piu' facilmente "costretto", quindi gli si chiede meno gap.
GAP_MIO_DEFAULT = 200           # soglia per le MIE mosse (passo_mio)
GAP_AVV_DEFAULT = 100           # soglia per le RISPOSTE avversarie (passo_avversario)
# Oltre questa valutazione (cp, dal mio lato) la posizione e' gia' decisa: senza
# una continuazione di matto chiara non insisto (no accanimento su posizione vinta).
SOGLIA_DECISA = 800
# Tetto: al massimo 3 MIE mosse nella soluzione (mia, avv, mia, avv, mia).
MAX_MOSSE_MIE = 3

# Cadenza del salvataggio incrementale nel batch (ripartenza sicura).
SALVA_OGNI = 50

# Default e seed della modalita' campione (riproducibile, NON i primi N del file).
CAMPIONE_DEFAULT = 100
SEED = 42


# --- Funzioni pure (testabili senza Stockfish) ---------------------------

def risolvi_soglie(gap, gap_mio, gap_avv):
    """
    Retrocompatibilita': se il vecchio parametro unico `gap` e' stato passato (non
    None), vale per ENTRAMBE le soglie; altrimenti valgono le due soglie separate.
    Restituisce la coppia (gap_mio, gap_avv) effettiva.
    """
    if gap is not None:
        return gap, gap
    return gap_mio, gap_avv


def turno_scacchiera(board):
    """Turno della scacchiera nel formato del FEN: 'w' al Bianco, 'b' al Nero."""
    return "w" if board.turn == chess.WHITE else "b"


def eval_e_mossa(info, turno):
    """
    Dalla 1a linea MultiPV ricava la quadrupla
      (eval_lato, e_matto_vincente, e_matto_subito, mossa_uci)
    tutte dal punto di vista di CHI MUOVE (turno). e_matto_vincente: chi muove da'
    matto; e_matto_subito: chi muove lo subisce (matto inevitabile contro di lui).
    """
    eval1_bianco, _, mossa1 = estrai_linea(info[0])
    eval1_lato = eval_lato_mossa(eval1_bianco, turno)
    vincente = eval1_lato >= SOGLIA_MATTO
    subito = eval1_lato <= -SOGLIA_MATTO
    return eval1_lato, vincente, subito, mossa1


def gap_multipv(info, turno):
    """
    Gap (centipawn) tra la 1a e la 2a linea MultiPV, ENTRAMBE dal lato di chi
    muove. Con una sola linea (nessuna alternativa) il gap e' "infinito".
    """
    eval1_lato, _, _, _ = eval_e_mossa(info, turno)
    if len(info) < 2:
        return GAP_MATTO
    eval2_bianco, _, _ = estrai_linea(info[1])
    eval2_lato = eval_lato_mossa(eval2_bianco, turno)
    return calcola_gap(eval1_lato, eval2_lato)


def passo_avversario(info, turno, soglia, soglia_decisa=SOGLIA_DECISA):
    """
    Decide la risposta dell'avversario (chi muove ora) a partire dal suo MultiPV.

    Restituisce la coppia (azione, mossa_uci) con azione in:
      - "continua"    : la sua mossa e' forzata, va giocata (mossa_uci valorizzata);
      - "stop_scelta" : ha una scelta reale -> fermo la sequenza (puzzle ambiguo oltre);
      - "stop_decisa" : la mia posizione e' gia' decisa (+800) senza matto -> fermo.

    La mia valutazione e' l'opposto di quella dell'avversario (eval_mia = -eval_avv):
      - se sto dando matto inevitabile (eval_mia matto): continuo verso il matto;
      - se eval_mia supera la soglia "decisa" senza matto: stop (no accanimento);
      - altrimenti l'avversario e' forzato se ha una sola mossa, e' costretto al
        matto (subito) o il gap >= soglia.
    """
    eval_avv, _, subito, mossa = eval_e_mossa(info, turno)
    eval_mia = -eval_avv

    # Matto inevitabile a mio favore: l'avversario e' costretto, proseguo.
    if eval_mia >= SOGLIA_MATTO:
        return "continua", mossa
    # Posizione gia' vinta ma senza una continuazione di matto: non insisto.
    if eval_mia > soglia_decisa:
        return "stop_decisa", None

    gap = gap_multipv(info, turno)
    forzata = (len(info) < 2) or subito or (gap >= soglia)
    if forzata:
        return "continua", mossa
    return "stop_scelta", None


def passo_mio(info, turno, soglia):
    """
    Decide la mia prossima mossa-soluzione dal mio MultiPV.

    Restituisce la quadrupla (azione, mossa_uci, eval_lato, vincente_matto) con
    azione in {"continua", "stop_scelta"}: continuo se ho una mossa nettamente
    migliore (gap >= soglia), un matto vincente o un'unica mossa; altrimenti fermo
    (avrei scelta -> niente "indovina quale").
    """
    eval_lato, vincente, _, mossa = eval_e_mossa(info, turno)
    gap = gap_multipv(info, turno)
    forzata = (len(info) < 2) or vincente or (gap >= soglia)
    if forzata:
        return "continua", mossa, eval_lato, vincente
    return "stop_scelta", None, eval_lato, vincente


def costruisci_esteso(puzzle, sequenza, n_mie):
    """
    Costruisce il puzzle esteso da salvare: copia il puzzle in ingresso (ordine e
    campi invariati: id, fen, rating, themes, origine, motivo_allenamento,
    fase_allenamento), aggiorna "moves" alla sequenza estesa e aggiunge
    "lunghezza_soluzione" = numero di MIE mosse (1, 2 o 3).
    """
    esteso = dict(puzzle)
    esteso["moves"] = " ".join(sequenza)
    esteso["lunghezza_soluzione"] = n_mie
    return esteso


# --- Estensione con Stockfish --------------------------------------------

def analizza_posizione(board, motore, profondita):
    """Analisi MultiPV=2 della posizione alla profondita' richiesta."""
    return motore.analyse(board, chess.engine.Limit(depth=profondita), multipv=2)


def estendi_puzzle(puzzle, motore, profondita, gap=None,
                   gap_mio=GAP_MIO_DEFAULT, gap_avv=GAP_AVV_DEFAULT,
                   soglia_decisa=SOGLIA_DECISA, max_mosse=MAX_MOSSE_MIE):
    """
    Estende un singolo puzzle finche' la continuazione resta forzata su entrambi i
    lati. Restituisce la coppia (puzzle_esteso, dettaglio) dove dettaglio contiene
    id, lunghezza (mosse mie), a_matto e motivo_stop.

    Soglie asimmetriche: gap_mio per le mie mosse, gap_avv per le risposte
    avversarie. Il vecchio `gap` unico, se passato, vale per entrambe (retrocompat).

    Una risposta forzata dell'avversario viene tenuta SOLO se seguita da una mia
    mossa forzata (la soluzione termina sempre su una mia mossa).
    """
    gap_mio, gap_avv = risolvi_soglie(gap, gap_mio, gap_avv)

    parti = puzzle["moves"].split()
    setup, mia1 = parti[0], parti[1]

    board = chess.Board(puzzle["fen"])
    board.push(chess.Move.from_uci(setup))
    board.push(chess.Move.from_uci(mia1))

    sequenza = [setup, mia1]   # tutte le semimosse dopo il setup, in ordine
    mie = [mia1]               # solo le MIE mosse
    a_matto = board.is_checkmate()
    motivo_stop = None

    while len(mie) < max_mosse:
        # Fine partita dopo la mia mossa (matto / stallo): stop.
        if board.is_game_over():
            a_matto = board.is_checkmate()
            motivo_stop = "matto" if a_matto else "fine"
            break

        # --- turno dell'avversario ---
        info = analizza_posizione(board, motore, profondita)
        azione, mossa_avv = passo_avversario(
            info, turno_scacchiera(board), gap_avv, soglia_decisa)
        if azione != "continua":
            motivo_stop = azione
            break

        # Gioco provvisoriamente la sua risposta forzata per valutare il mio turno.
        board.push(chess.Move.from_uci(mossa_avv))
        if board.is_game_over():
            # La sua mossa chiude la partita: non ho una mia mossa da aggiungere,
            # quindi NON tengo nemmeno la sua (la soluzione resta sulla mia mossa
            # precedente). Annullo e mi fermo.
            board.pop()
            motivo_stop = "fine"
            break

        # --- mio turno dopo la risposta forzata ---
        info = analizza_posizione(board, motore, profondita)
        azione, mossa_mia, _, _ = passo_mio(info, turno_scacchiera(board), gap_mio)
        if azione != "continua":
            # La mia mossa non e' univoca: scarto anche la risposta avversaria.
            board.pop()
            motivo_stop = "stop_scelta"
            break

        # Coppia confermata: tengo risposta avversaria + mia mossa.
        sequenza.append(mossa_avv)
        sequenza.append(mossa_mia)
        mie.append(mossa_mia)
        board.push(chess.Move.from_uci(mossa_mia))
        if board.is_checkmate():
            a_matto = True
            motivo_stop = "matto"
            break
    else:
        # Uscita per il tetto di mosse mie (nessun break).
        motivo_stop = "tetto"

    esteso = costruisci_esteso(puzzle, sequenza, len(mie))
    dettaglio = {
        "id": puzzle.get("id"),
        "lunghezza": len(mie),
        "a_matto": a_matto,
        "motivo_stop": motivo_stop,
    }
    return esteso, dettaglio


# --- Selezione campione / batch ------------------------------------------

def carica_coda(percorso=PERCORSO_CODA):
    """Carica i puzzle-errore gia' in coda (formato del backend)."""
    with open(percorso, "r", encoding="utf-8") as f:
        return json.load(f)


def seleziona_campione(puzzle, n, seed=SEED):
    """
    Mescola i puzzle con seed fisso (campione rappresentativo, NON i primi N in
    ordine di file) e ne restituisce i primi n, insieme al totale.
    """
    mescolati = list(puzzle)
    random.Random(seed).shuffle(mescolati)
    return mescolati[:n], len(puzzle)


def chiave_puzzle(puzzle):
    """Chiave univoca per la ripartenza: l'id del puzzle in coda."""
    return puzzle["id"]


def filtra_da_processare(puzzle, processati):
    """Tiene solo i puzzle il cui id NON e' fra i gia'-processati (ripartenza)."""
    processati = set(processati)
    return [p for p in puzzle if chiave_puzzle(p) not in processati]


# --- Contatori e distribuzione delle lunghezze ---------------------------

def _stato_iniziale():
    """Contatori cumulativi (azzerati a una corsa da zero)."""
    return {"totali": 0, "lung1": 0, "lung2": 0, "lung3": 0, "matti": 0}


def aggiorna_contatori(contatori, dettaglio):
    """Aggiorna i contatori con l'esito di un puzzle (lunghezza e matto)."""
    contatori["totali"] += 1
    contatori["lung%d" % dettaglio["lunghezza"]] += 1
    if dettaglio["a_matto"]:
        contatori["matti"] += 1


# --- Batch: salvataggio incrementale e ripartenza sicura -----------------

def componi_stato(processati, contatori, gap=None, profondita=None,
                  gap_mio=GAP_MIO_DEFAULT, gap_avv=GAP_AVV_DEFAULT):
    """
    Compone l'oggetto di stato da serializzare nel sidecar di progresso: parametri
    della corsa, id gia' processati (ordinati) e contatori cumulativi. Funzione
    pura, testabile senza disco. Il vecchio `gap` unico, se passato, vale per
    entrambe le soglie (retrocompat).
    """
    gap_mio, gap_avv = risolvi_soglie(gap, gap_mio, gap_avv)
    stato = {"gap_mio": gap_mio, "gap_avv": gap_avv, "profondita": profondita,
             "processati": sorted(processati)}
    stato.update(contatori)
    return stato


def salva_progresso(estesi, stato, percorso_output=PERCORSO_OUTPUT,
                    percorso_progresso=PERCORSO_PROGRESSO):
    """Salvataggio incrementale: scrive la coda estesa e, accanto, lo stato."""
    os.makedirs(os.path.dirname(percorso_output), exist_ok=True)
    with open(percorso_output, "w", encoding="utf-8") as f:
        json.dump(estesi, f, indent=2, ensure_ascii=False)
    with open(percorso_progresso, "w", encoding="utf-8") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)


def carica_progresso(percorso_output=PERCORSO_OUTPUT,
                     percorso_progresso=PERCORSO_PROGRESSO):
    """
    Ricarica una corsa batch in corso: (estesi, stato) se esistono SIA il file di
    output SIA il sidecar, altrimenti None (si parte da zero).
    """
    if not (os.path.exists(percorso_output) and os.path.exists(percorso_progresso)):
        return None
    with open(percorso_output, "r", encoding="utf-8") as f:
        estesi = json.load(f)
    with open(percorso_progresso, "r", encoding="utf-8") as f:
        stato = json.load(f)
    return estesi, stato


def estendi_campione(puzzle, n, profondita, gap=None,
                     gap_mio=GAP_MIO_DEFAULT, gap_avv=GAP_AVV_DEFAULT,
                     percorso_motore=PERCORSO_STOCKFISH):
    """
    Apre Stockfish ed estende un campione di n puzzle (mescolati con seed fisso).
    NON salva nulla. Restituisce (dettagli, totale) oppure None se manca il motore;
    ogni dettaglio e' arricchito col tempo impiegato (secondi). Soglie asimmetriche
    (gap_mio / gap_avv); il vecchio `gap` unico vale per entrambe (retrocompat).
    """
    gap_mio, gap_avv = risolvi_soglie(gap, gap_mio, gap_avv)

    if not os.path.exists(percorso_motore):
        logger.error("Stockfish non trovato in: %s", percorso_motore)
        return None

    campione, totale = seleziona_campione(puzzle, n)
    logger.info("Campione: %d puzzle (su %d in coda), profondita %d, "
                "gap_mio %d, gap_avv %d",
                len(campione), totale, profondita, gap_mio, gap_avv)

    motore = chess.engine.SimpleEngine.popen_uci(percorso_motore)
    dettagli = []
    try:
        for indice, p in enumerate(campione, start=1):
            inizio = time.perf_counter()
            _, dettaglio = estendi_puzzle(p, motore, profondita,
                                          gap_mio=gap_mio, gap_avv=gap_avv)
            dettaglio["tempo_secondi"] = time.perf_counter() - inizio
            dettagli.append(dettaglio)
            logger.info(
                "Esteso %d/%d | %s | lunghezza=%d | matto=%s | %.2fs",
                indice, len(campione), dettaglio["id"], dettaglio["lunghezza"],
                dettaglio["a_matto"], dettaglio["tempo_secondi"],
            )
    finally:
        motore.quit()

    return dettagli, totale


def estendi_batch(puzzle, profondita, gap=None, ricomincia=False,
                  gap_mio=GAP_MIO_DEFAULT, gap_avv=GAP_AVV_DEFAULT,
                  percorso_motore=PERCORSO_STOCKFISH,
                  percorso_output=PERCORSO_OUTPUT,
                  percorso_progresso=PERCORSO_PROGRESSO):
    """
    Estende con Stockfish TUTTI i puzzle e salva la coda estesa in percorso_output,
    nello stesso ordine del file di ingresso. Salvataggio incrementale +
    ripartenza dalla corsa precedente (a meno di ricomincia=True). Restituisce un
    riepilogo (dict) o None se manca il motore. Soglie asimmetriche (gap_mio /
    gap_avv); il vecchio `gap` unico vale per entrambe (retrocompat).
    """
    gap_mio, gap_avv = risolvi_soglie(gap, gap_mio, gap_avv)

    if not os.path.exists(percorso_motore):
        logger.error("Stockfish non trovato in: %s", percorso_motore)
        return None

    totale = len(puzzle)

    # Ripartenza: riprendo gli estesi, gli id gia' processati e i contatori.
    estesi = []
    processati = set()
    contatori = _stato_iniziale()
    if not ricomincia:
        precedente = carica_progresso(percorso_output, percorso_progresso)
        if precedente is not None:
            estesi, stato = precedente
            processati = set(stato.get("processati", []))
            contatori = {k: stato.get(k, 0) for k in contatori}
            logger.info("Ripartenza: %d puzzle gia' estesi", len(processati))

    da_processare = filtra_da_processare(puzzle, processati)
    logger.info("Batch: %d puzzle (%d da processare), profondita %d, "
                "gap_mio %d, gap_avv %d",
                totale, len(da_processare), profondita, gap_mio, gap_avv)

    motore = chess.engine.SimpleEngine.popen_uci(percorso_motore)
    inizio = time.perf_counter()
    da_ultimo_salvataggio = 0
    try:
        for p in da_processare:
            esteso, dettaglio = estendi_puzzle(p, motore, profondita,
                                               gap_mio=gap_mio, gap_avv=gap_avv)
            estesi.append(esteso)
            aggiorna_contatori(contatori, dettaglio)
            processati.add(chiave_puzzle(p))
            da_ultimo_salvataggio += 1

            if da_ultimo_salvataggio >= SALVA_OGNI:
                stato = componi_stato(processati, contatori, profondita=profondita,
                                      gap_mio=gap_mio, gap_avv=gap_avv)
                salva_progresso(estesi, stato, percorso_output, percorso_progresso)
                da_ultimo_salvataggio = 0
                logger.info(
                    "estesi %d / %d puzzle, trascorso %s",
                    contatori["totali"], totale,
                    formatta_durata(time.perf_counter() - inizio),
                )
    finally:
        motore.quit()

    # Salvataggio finale.
    stato = componi_stato(processati, contatori, profondita=profondita,
                          gap_mio=gap_mio, gap_avv=gap_avv)
    salva_progresso(estesi, stato, percorso_output, percorso_progresso)

    riepilogo = dict(contatori)
    riepilogo.update({
        "totale": totale,
        "tempo_corsa": time.perf_counter() - inizio,
        "n_file": len(estesi),
        "percorso_output": percorso_output,
    })
    return riepilogo


# --- Stampe --------------------------------------------------------------

def _stampa_tabella(dettagli, totale, profondita, gap_mio, gap_avv):
    """Tabella di taratura: distribuzione delle lunghezze, tempi e stima batch."""
    n = len(dettagli)
    conta = {1: 0, 2: 0, 3: 0}
    for d in dettagli:
        conta[d["lunghezza"]] += 1
    n_matti = sum(1 for d in dettagli if d["a_matto"])

    tempi = [d["tempo_secondi"] for d in dettagli]
    tempo_totale = sum(tempi)
    tempo_medio = (tempo_totale / n) if n else 0.0
    stima = stima_tempo_totale(tempo_medio, totale)

    print()
    print("=== TARATURA estensione sequenze "
          "(profondita %d, gap_mio %d, gap_avv %d) ==="
          % (profondita, gap_mio, gap_avv))
    print()
    print(f"  Puzzle nel campione estesi   : {n}")
    print(f"  Totale puzzle in coda        : {totale}")
    print(f"  Arrivati a matto             : {n_matti}")
    print()
    print("  Distribuzione lunghezza soluzione (mie mosse):")
    print(f"    {'Lunghezza':<12} {'Puzzle':>8} {'%':>8}")
    print(f"    {'-' * 12} {'-' * 8:>8} {'-' * 8:>8}")
    for lung in (1, 2, 3):
        q = conta[lung]
        perc = (100.0 * q / n) if n else 0.0
        etichetta = "1 mossa" if lung == 1 else f"{lung} mosse"
        print(f"    {etichetta:<12} {q:>8} {perc:>7.1f}%")
    print()
    print(f"  Tempo medio per puzzle    : {tempo_medio:.2f}s")
    print(f"  Tempo totale del campione : {formatta_durata(tempo_totale)} "
          f"({tempo_totale:.1f}s)")
    print(f"  STIMA batch completo      : {formatta_durata(stima)} "
          f"(~{totale} puzzle)")
    print()


def _stampa_riepilogo_batch(riepilogo, profondita, gap_mio, gap_avv):
    """Riepilogo finale del batch completo."""
    n = riepilogo["totali"]
    print()
    print("=== BATCH estensione sequenze "
          "(profondita %d, gap_mio %d, gap_avv %d) ==="
          % (profondita, gap_mio, gap_avv))
    print()
    print(f"  Totale puzzle in coda    : {riepilogo['totale']}")
    print(f"  Puzzle estesi            : {n}")
    print(f"  Arrivati a matto         : {riepilogo['matti']}")
    print()
    print("  Distribuzione lunghezza soluzione (mie mosse):")
    for lung in (1, 2, 3):
        q = riepilogo["lung%d" % lung]
        perc = (100.0 * q / n) if n else 0.0
        etichetta = "1 mossa" if lung == 1 else f"{lung} mosse"
        print(f"    {etichetta:<8} : {q:>6} ({perc:>5.1f}%)")
    print()
    print(f"  Tempo di questa corsa    : "
          f"{formatta_durata(riepilogo['tempo_corsa'])} "
          f"({riepilogo['tempo_corsa']:.1f}s)")
    print(f"  Salvati {riepilogo['n_file']} puzzle in {riepilogo['percorso_output']}")
    print()


def _argomenti(argv=None):
    parser = argparse.ArgumentParser(
        description="Estensione dei puzzle-errore in sequenze forzate multi-mossa "
                    "(usa Stockfish): taratura su campione (default) oppure batch "
                    "completo con --batch."
    )
    parser.add_argument("--campione", type=int, default=CAMPIONE_DEFAULT,
                        help="taratura: quanti puzzle estendere (default %d, "
                             "ignorato con --batch)" % CAMPIONE_DEFAULT)
    parser.add_argument("--profondita", type=int, default=PROFONDITA_DEFAULT,
                        help="profondita' Stockfish (default %d)"
                             % PROFONDITA_DEFAULT)
    parser.add_argument("--gap-mio", type=int, default=GAP_MIO_DEFAULT,
                        help="soglia di forzatura per le MIE mosse, in centipawn "
                             "(default %d)" % GAP_MIO_DEFAULT)
    parser.add_argument("--gap-avv", type=int, default=GAP_AVV_DEFAULT,
                        help="soglia di forzatura per le RISPOSTE dell'avversario, "
                             "in centipawn (default %d)" % GAP_AVV_DEFAULT)
    parser.add_argument("--gap", type=int, default=None,
                        help="(retrocompat) soglia unica: se data, vale per "
                             "ENTRAMBE le soglie e ignora --gap-mio/--gap-avv")
    parser.add_argument("--batch", action="store_true",
                        help="estende TUTTI i puzzle e salva la coda estesa in "
                             "data/coda_errori_estesa.json")
    parser.add_argument("--ricomincia", action="store_true",
                        help="batch: ignora il progresso salvato e rifa' tutto da zero")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _argomenti()

    logger.info("Carico la coda da: %s", PERCORSO_CODA)
    if not os.path.exists(PERCORSO_CODA):
        print(f"\nNessun file {PERCORSO_CODA}: genera prima la coda errori.\n")
        sys.exit(1)
    puzzle = carica_coda()
    logger.info("Caricati %d puzzle in coda", len(puzzle))

    # Retrocompat: il vecchio --gap unico, se passato, vale per entrambe le soglie.
    gap_mio, gap_avv = risolvi_soglie(args.gap, args.gap_mio, args.gap_avv)

    if args.batch:
        riepilogo = estendi_batch(puzzle, args.profondita,
                                  gap_mio=gap_mio, gap_avv=gap_avv,
                                  ricomincia=args.ricomincia)
        if riepilogo is None:
            print("\nEstensione non riuscita (Stockfish presente in engine/bin/?).\n")
            sys.exit(1)
        _stampa_riepilogo_batch(riepilogo, args.profondita, gap_mio, gap_avv)
        sys.exit(0)

    esito = estendi_campione(puzzle, args.campione, args.profondita,
                             gap_mio=gap_mio, gap_avv=gap_avv)
    if esito is None:
        print("\nEstensione non riuscita (Stockfish presente in engine/bin/?).\n")
        sys.exit(1)

    dettagli, totale = esito
    _stampa_tabella(dettagli, totale, args.profondita, gap_mio, gap_avv)
    print("Tappa di TARATURA: nessun file salvato. Scegli i parametri e poi "
          "lancia --batch per la coda estesa completa.")
    print()
