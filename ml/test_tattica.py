"""
Test del modulo tattica (pezzo in presa + forchetta).

Non richiede Stockfish: ragiona solo sulle posizioni. Gira ovunque.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import chess
from tattica import (
    _guadagno_cattura,
    trova_pezzo_in_presa,
    trova_forchetta,
    rileva_tipo_tattico,
)


# --- SEE / pezzo in presa ---

def test_torre_indifesa_e_in_presa():
    b = chess.Board("3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1")
    assert _guadagno_cattura(b, chess.D5, chess.BLACK) > 0


def test_torre_difesa_da_pari_non_conviene():
    b = chess.Board("3rk3/8/8/3R4/8/8/8/3R1K2 b - - 0 1")
    assert _guadagno_cattura(b, chess.D5, chess.BLACK) == 0


def test_trova_il_pezzo_in_presa():
    b = chess.Board("3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1")
    assert trova_pezzo_in_presa(b, chess.WHITE) == chess.D5


def test_nessun_pezzo_in_presa_iniziale():
    assert trova_pezzo_in_presa(chess.Board(), chess.WHITE) is None


# --- Forchetta ---

def test_trova_forchetta_cavallo():
    """Cavallo nero a6 puo' saltare in c7 e forchettare donna a8 e torre e8."""
    b = chess.Board("Q3R3/8/n6k/8/8/8/8/7K b - - 0 1")
    assert trova_forchetta(b, chess.WHITE) is True


def test_nessuna_forchetta_iniziale():
    assert trova_forchetta(chess.Board(), chess.WHITE) is False


def test_forchetta_non_valida_se_pezzo_catturabile():
    """
    Se il pezzo che forchetterebbe finisce in una casa difesa e viene perso,
    non e' una forchetta vantaggiosa.
    """
    # Cavallo nero forchetterebbe da c7, ma c7 e' difeso dall'alfiere bianco a5.
    b = chess.Board("Q3R3/8/n6k/B7/8/8/8/7K b - - 0 1")
    assert trova_forchetta(b, chess.WHITE) is False


# --- Etichette finali ---

def test_etichetta_pezzo_in_presa():
    fen = "3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1"
    assert rileva_tipo_tattico(fen, chess.WHITE) == "pezzo_in_presa"


def test_etichetta_forchetta():
    fen = "Q3R3/8/n6k/8/8/8/8/7K b - - 0 1"
    assert rileva_tipo_tattico(fen, chess.WHITE) == "forchetta"


def test_etichetta_niente():
    assert rileva_tipo_tattico(chess.STARTING_FEN, chess.WHITE) is None
