"""
Modulo arricchimento (Fase 3) - aggiunge le categorie alle partite analizzate.

Legge i file di analisi grezza da data/analisi/, e per ogni mossa aggiunge:
- gravita e fase  (da categorizza)
- tipo_tattico    (da tattica: per ora "pezzo_in_presa", solo sugli errori veri)

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


def _aggiungi_tipo_tattico(mossa):
    """
    Se la mossa e' un errore vero, controlla se ha lasciato un pezzo in presa.
    Ricostruisce la posizione DOPO la mossa partendo da fen (prima) + move_uci,
    e guarda se chi ha mosso ha un pezzo catturabile.
    Modifica e restituisce la mossa.
    """
    if mossa.get("gravita") not in GRAVITA_DA_ANALIZZARE:
        mossa["tipo_tattico"] = None
        return mossa

    try:
        board = chess.Board(mossa["fen"])
        colore_che_muove = board.turn  # chi sta per muovere = chi fa la mossa
        board.push(chess.Move.from_uci(mossa["move_uci"]))
        fen_dopo = board.fen()
        mossa["tipo_tattico"] = rileva_tipo_tattico(fen_dopo, colore_che_muove)
    except Exception as e:
        logger.warning("Tipo tattico non calcolabile per una mossa: %s", e)
        mossa["tipo_tattico"] = None
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
        m_cat = _aggiungi_tipo_tattico(m_cat)  # eventualmente "pezzo_in_presa"
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
