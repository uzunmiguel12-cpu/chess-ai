"""
Modulo arricchimento (Fase 3) - aggiunge le categorie alle partite analizzate.

Legge i file di analisi grezza da data/analisi/, e per ogni mossa aggiunge:
- gravita e fase  (da categorizza)
- tipo_tattico    (da tattica: la tattica della MOSSA MIGLIORE = tattica mancata,
                   solo sugli errori veri)

Salva i risultati in data/categorie/. Tiene separati i due stadi: l'analisi
grezza (costosa, Stockfish) e le categorie (rigenerabili in fretta).

Uso:  python arricchisci.py
"""

import os
import json
import glob
import logging
import chess

from categorizza import categorizza_mossa
from tattica import rileva_tipo_tattico

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)
CARTELLA_CATEGORIE = os.path.join(
    os.path.dirname(__file__), "..", "data", "categorie"
)

# Cerchiamo il tipo tattico solo sugli errori veri (risparmio di lavoro).
GRAVITA_DA_ANALIZZARE = {"mistake", "blunder"}


def _tattica_della_best(mossa):
    """
    Restituisce la tattica della MOSSA MIGLIORE in questa posizione (o None). Ricostruisce
    la posizione DOPO la best move partendo da fen (prima) + best_move_uci, col colore di
    chi DOVEVA muovere (= io, board.turn della posizione di partenza), e chiede a
    rileva_tipo_tattico quale pattern crea. Puro, niente Stockfish.

    None se: best_move_uci mancante/illegale, o se la best non crea alcun pattern noto
    (errore POSIZIONALE vero / mossa tranquilla).
    """
    best_move_uci = mossa.get("best_move_uci")
    if not best_move_uci:
        return None
    try:
        board = chess.Board(mossa["fen"])
        colore_che_muove = board.turn  # chi DOVEVA giocare la best move = io
        fen_prima = mossa["fen"]
        board.push(chess.Move.from_uci(best_move_uci))
        return rileva_tipo_tattico(fen_prima, board.fen(), colore_che_muove, best_move_uci)
    except Exception as e:
        logger.warning("Tattica della best non calcolabile per una mossa: %s", e)
        return None


def _aggiungi_tipo_tattico(mossa):
    """
    Aggiunge DUE campi, entrambi dalla tattica della MOSSA MIGLIORE (un errore e' una
    tattica MANCATA):

    - `occasione_tattica`: la tattica della best su OGNI mossa (#3). E' l'"occasione":
      la posizione CHIEDEVA quella tattica, che io l'abbia trovata o no. E' il DENOMINATORE
      del tasso-su-occasioni (errori-di-T / occasioni-di-T = "quando T era giusta, quanto
      spesso l'ho mancata").
    - `tipo_tattico`: la tattica mancata, definita SOLO sugli errori veri (retrocompat: il
      profilo conta i tipi tattici sugli errori). Per un errore coincide con occasione_tattica.
    """
    occ = _tattica_della_best(mossa)
    mossa["occasione_tattica"] = occ
    mossa["tipo_tattico"] = occ if mossa.get("gravita") in GRAVITA_DA_ANALIZZARE else None
    return mossa


def arricchisci_partita(dato_partita):
    """
    Arricchisce ogni mossa con gravita, fase (da categorizza) e poi tipo_tattico.
    Mantiene i metadati (bianco, nero, risultato).
    """
    arricchito = dict(dato_partita)
    mosse_arricchite = []
    for m in dato_partita["mosse"]:
        m_cat = categorizza_mossa(m)        # gravita + fase (+ tipo_tattico=None)
        m_cat = _aggiungi_tipo_tattico(m_cat)  # tattica mancata (dalla best move)
        mosse_arricchite.append(m_cat)
    arricchito["mosse"] = mosse_arricchite
    return arricchito


def arricchisci_tutte(cartella_in=CARTELLA_ANALISI, cartella_out=CARTELLA_CATEGORIE):
    """Legge data/analisi/, arricchisce, salva in data/categorie/. Conta i file."""
    if not os.path.isdir(cartella_in):
        logger.error("Cartella analisi non trovata: %s", cartella_in)
        return 0
    os.makedirs(cartella_out, exist_ok=True)

    file_analisi = sorted(glob.glob(os.path.join(cartella_in, "*.json")))
    logger.info("Trovati %d file da arricchire", len(file_analisi))

    arricchiti = 0
    for percorso_in in file_analisi:
        nome = os.path.basename(percorso_in)
        with open(percorso_in, "r", encoding="utf-8") as f:
            dato = json.load(f)
        dato_arricchito = arricchisci_partita(dato)
        with open(os.path.join(cartella_out, nome), "w", encoding="utf-8") as f:
            json.dump(dato_arricchito, f, indent=2, ensure_ascii=False)
        arricchiti += 1

    logger.info("Fatto. File arricchiti: %d", arricchiti)
    return arricchiti


if __name__ == "__main__":
    n = arricchisci_tutte()
    print()
    print(f"Partite arricchite con le categorie: {n}")
    print(f"Risultati in: data/categorie/")
    print()
