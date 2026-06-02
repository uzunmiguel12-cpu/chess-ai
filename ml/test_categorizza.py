"""
Test del modulo categorizza (gravita' + fase).

Non richiede Stockfish: sono regole pure sui dati, quindi i test girano
ovunque, CI inclusa.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

from categorizza import (
    classifica_gravita,
    classifica_fase,
    categorizza_mossa,
)

POS_INIZIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
POS_FINALE = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"  # solo re + un pedone


# --- Gravita' ---

def test_gravita_mossa_buona():
    assert classifica_gravita(0) == "ok"
    assert classifica_gravita(49) == "ok"


def test_gravita_imprecisione():
    assert classifica_gravita(50) == "imprecisione"
    assert classifica_gravita(99) == "imprecisione"


def test_gravita_errore():
    assert classifica_gravita(100) == "errore"
    assert classifica_gravita(299) == "errore"


def test_gravita_blunder():
    assert classifica_gravita(300) == "blunder"
    assert classifica_gravita(1500) == "blunder"


# --- Fase ---

def test_fase_apertura():
    """Nella posizione iniziale tutti i pezzi sono presenti: apertura."""
    assert classifica_fase(POS_INIZIALE) == "apertura"


def test_fase_finale():
    """Con solo i re e un pedone siamo in un finale."""
    assert classifica_fase(POS_FINALE) == "finale"


# --- Categorizzazione completa ---

def test_categorizza_aggiunge_tutti_i_campi():
    mossa = {"fen": POS_INIZIALE, "centipawn_loss": 10, "san": "e4"}
    c = categorizza_mossa(mossa)
    assert c["gravita"] == "ok"
    assert c["fase"] == "apertura"
    assert "tipo_tattico" in c
    assert c["tipo_tattico"] is None


def test_categorizza_non_modifica_originale():
    """La funzione deve restituire una copia, non alterare il dizionario dato."""
    mossa = {"fen": POS_INIZIALE, "centipawn_loss": 10, "san": "e4"}
    categorizza_mossa(mossa)
    assert "gravita" not in mossa  # l'originale resta intatto
