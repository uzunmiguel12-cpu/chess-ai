"""
Test del modulo categorizza (scala stile Chess.com + fase).

Non richiede Stockfish: regole pure sui dati, girano ovunque (CI inclusa).

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

from categorizza import (
    classifica_gravita,
    classifica_fase,
    categorizza_mossa,
)

POS_INIZIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
POS_FINALE = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"


# --- Gravita' (scala stile Chess.com) ---

def test_best():
    assert classifica_gravita(0) == "best"


def test_excellent():
    assert classifica_gravita(1) == "excellent"
    assert classifica_gravita(20) == "excellent"


def test_good():
    assert classifica_gravita(21) == "good"
    assert classifica_gravita(60) == "good"


def test_inaccuracy():
    assert classifica_gravita(61) == "inaccuracy"
    assert classifica_gravita(100) == "inaccuracy"


def test_mistake():
    assert classifica_gravita(101) == "mistake"
    assert classifica_gravita(200) == "mistake"


def test_blunder():
    assert classifica_gravita(201) == "blunder"
    assert classifica_gravita(1500) == "blunder"


# --- Fase ---

def test_fase_apertura():
    assert classifica_fase(POS_INIZIALE) == "apertura"


def test_fase_finale():
    assert classifica_fase(POS_FINALE) == "finale"


# --- Categorizzazione completa ---

def test_categorizza_aggiunge_tutti_i_campi():
    mossa = {"fen": POS_INIZIALE, "centipawn_loss": 0, "san": "e4"}
    c = categorizza_mossa(mossa)
    assert c["gravita"] == "best"
    assert c["fase"] == "apertura"
    assert c["tipo_tattico"] is None


def test_categorizza_non_modifica_originale():
    mossa = {"fen": POS_INIZIALE, "centipawn_loss": 0, "san": "e4"}
    categorizza_mossa(mossa)
    assert "gravita" not in mossa
