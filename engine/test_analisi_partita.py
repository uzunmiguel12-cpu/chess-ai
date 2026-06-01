"""
Test del modulo analisi_partita (centipawn loss).

Richiede Stockfish in engine/bin/stockfish.exe; altrimenti i test sono saltati.
Usa profondita' bassa (8) per essere veloce nei test.

Esegui (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
import pytest
from analisi_partita import analizza_partita, PERCORSO_STOCKFISH

stockfish_assente = not os.path.exists(PERCORSO_STOCKFISH)
motivo = "Stockfish non presente in engine/bin/stockfish.exe"

CARTELLA_TEST = os.path.dirname(__file__)
PARTITA = os.path.join(CARTELLA_TEST, "partita_esempio.pgn")


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_analizza_tutte_le_mosse():
    """Deve restituire un risultato per ogni mossa della partita."""
    risultati = analizza_partita(PARTITA, profondita=8)
    assert risultati is not None
    assert len(risultati) > 0


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_ogni_risultato_ha_i_campi_attesi():
    """Ogni mossa analizzata deve avere tutti i campi previsti."""
    risultati = analizza_partita(PARTITA, profondita=8)
    for r in risultati:
        assert "fen" in r
        assert "move_uci" in r
        assert "san" in r
        assert "centipawn_loss" in r


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_centipawn_loss_mai_negativo():
    """Il centipawn loss non deve mai essere negativo (lo portiamo a 0)."""
    risultati = analizza_partita(PARTITA, profondita=8)
    for r in risultati:
        assert r["centipawn_loss"] >= 0


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_partita_ben_giocata_ha_loss_contenuti():
    """
    Nella 'Partita del secolo' (mosse di alta qualita') il loss medio deve
    essere contenuto: nessuna mossa con errore enorme (sopra 1000 cp).
    """
    risultati = analizza_partita(PARTITA, profondita=8)
    loss_massimo = max(r["centipawn_loss"] for r in risultati)
    assert loss_massimo < 1000
