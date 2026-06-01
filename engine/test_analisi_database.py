"""
Test del modulo analisi_database (analisi multi-partita, un file per partita).

Richiede Stockfish in engine/bin/stockfish.exe; altrimenti i test sono saltati.
Profondita' bassa (8) per velocita'.

Esegui (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
import glob
import pytest
from analisi_database import analizza_database, CARTELLA_ANALISI, PERCORSO_STOCKFISH

stockfish_assente = not os.path.exists(PERCORSO_STOCKFISH)
motivo = "Stockfish non presente in engine/bin/stockfish.exe"

CARTELLA_TEST = os.path.dirname(__file__)
MULTIPLE = os.path.join(CARTELLA_TEST, "partite_multiple.pgn")


def _pulisci_file_di_test():
    """Rimuove eventuali file di analisi di partite_multiple dai test precedenti."""
    for f in glob.glob(os.path.join(CARTELLA_ANALISI, "partite_multiple_*.json")):
        os.remove(f)


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_analizza_tutte_le_partite():
    """Deve produrre un file per ognuna delle 3 partite del file di prova."""
    _pulisci_file_di_test()
    n = analizza_database(MULTIPLE, profondita=8)
    assert n == 3
    prodotti = glob.glob(os.path.join(CARTELLA_ANALISI, "partite_multiple_*.json"))
    assert len(prodotti) == 3
    _pulisci_file_di_test()


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_non_rifa_lavoro_gia_fatto():
    """Alla seconda esecuzione deve saltare tutto (0 partite nuove analizzate)."""
    _pulisci_file_di_test()
    analizza_database(MULTIPLE, profondita=8)   # prima volta: analizza
    n = analizza_database(MULTIPLE, profondita=8)  # seconda: deve saltare
    assert n == 0
    _pulisci_file_di_test()
