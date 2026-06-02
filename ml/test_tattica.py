"""
Test del modulo tattica (riconoscimento pezzo in presa via SEE).

Non richiede Stockfish: ragiona solo sulle posizioni. Gira ovunque.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import chess
from tattica import (
    _guadagno_cattura,
    trova_pezzo_in_presa,
    rileva_tipo_tattico,
)


# --- SEE di base ---

def test_torre_indifesa_e_in_presa():
    """Torre bianca d5 attaccata da torre nera, non difesa: catturabile."""
    b = chess.Board("3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1")
    assert _guadagno_cattura(b, chess.D5, chess.BLACK) > 0


def test_torre_difesa_da_pari_non_conviene():
    """Torre d5 difesa da un'altra torre: lo scambio e' pari, guadagno 0."""
    b = chess.Board("3rk3/8/8/3R4/8/8/8/3R1K2 b - - 0 1")
    assert _guadagno_cattura(b, chess.D5, chess.BLACK) == 0


def test_donna_indifesa_e_in_presa():
    """Donna bianca d5 attaccata da pedone c6, non difesa: catturabile."""
    b = chess.Board("4k3/8/2p5/3Q4/8/8/8/4K3 b - - 0 1")
    assert _guadagno_cattura(b, chess.D5, chess.BLACK) > 0


# --- trova_pezzo_in_presa ---

def test_trova_il_pezzo_in_presa():
    b = chess.Board("3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1")
    casa = trova_pezzo_in_presa(b, chess.WHITE)
    assert casa == chess.D5


def test_nessun_pezzo_in_presa_iniziale():
    b = chess.Board()
    assert trova_pezzo_in_presa(b, chess.WHITE) is None


def test_sceglie_il_pezzo_piu_prezioso():
    """Con torre E donna entrambe in presa, segnala la donna (piu' grave)."""
    # Donna bianca a5 e torre bianca h5, entrambe attaccate da torri nere indifese.
    b = chess.Board("r6r/8/8/Q6R/8/8/8/4K1k1 b - - 0 1")
    casa = trova_pezzo_in_presa(b, chess.WHITE)
    assert casa == chess.A5  # la donna


# --- rileva_tipo_tattico ---

def test_rileva_pezzo_in_presa():
    fen = "3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1"
    assert rileva_tipo_tattico(fen, chess.WHITE) == "pezzo_in_presa"


def test_rileva_niente_se_sicuro():
    fen = "3rk3/8/8/3R4/8/8/8/3R1K2 b - - 0 1"
    assert rileva_tipo_tattico(fen, chess.WHITE) is None
