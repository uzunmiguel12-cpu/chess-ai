"""
Test del modulo motore (Stockfish).

Questi test richiedono che Stockfish sia presente in engine/bin/stockfish.exe.
Se non c'e', i test vengono saltati automaticamente (skip), cosi' la suite
non fallisce su una macchina senza Stockfish.

Esegui (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
import pytest
from motore import saluta_stockfish, analizza_posizione, PERCORSO_STOCKFISH

# Se Stockfish non e' installato, saltiamo i test di questo file.
stockfish_assente = not os.path.exists(PERCORSO_STOCKFISH)
motivo = "Stockfish non presente in engine/bin/stockfish.exe"

FEN_INIZIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_stockfish_risponde():
    """Il motore deve rispondere con un nome che contiene 'Stockfish'."""
    info = saluta_stockfish()
    assert info is not None
    assert "Stockfish" in info["nome"]


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_analisi_restituisce_i_campi_del_contratto():
    """L'analisi deve restituire eval_cp e best_move_uci."""
    a = analizza_posizione(FEN_INIZIALE, profondita=10)
    assert a is not None
    assert "eval_cp" in a
    assert "best_move_uci" in a


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_valutazione_iniziale_e_equilibrata():
    """
    Nella posizione iniziale la valutazione deve essere vicina a zero
    (partita equilibrata): un piccolo vantaggio al Bianco, mai estremo.
    """
    a = analizza_posizione(FEN_INIZIALE, profondita=10)
    assert -100 < a["eval_cp"] < 100


@pytest.mark.skipif(stockfish_assente, reason=motivo)
def test_mossa_migliore_e_legale():
    """La mossa migliore restituita deve essere una mossa valida (4-5 caratteri UCI)."""
    a = analizza_posizione(FEN_INIZIALE, profondita=10)
    assert a["best_move_uci"] is not None
    assert len(a["best_move_uci"]) in (4, 5)
