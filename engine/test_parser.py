"""
Test del parser PGN.

Esegui (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
from parser import estrai_dati_partita, estrai_mosse

CARTELLA_TEST = os.path.dirname(__file__)
PARTITA = os.path.join(CARTELLA_TEST, "partita_esempio.pgn")


# --- Test sui metadati ---

def test_estrae_i_giocatori_giusti():
    dati = estrai_dati_partita(PARTITA)
    assert dati["bianco"] == "Donald Byrne"
    assert dati["nero"] == "Robert Fischer"


def test_estrae_il_risultato_giusto():
    dati = estrai_dati_partita(PARTITA)
    assert dati["risultato"] == "0-1"


def test_conta_le_mosse():
    dati = estrai_dati_partita(PARTITA)
    assert dati["numero_mosse"] > 0


# --- Test sull'estrazione delle mosse ---

def test_estrae_una_lista_di_mosse():
    """La funzione deve restituire una lista non vuota."""
    mosse = estrai_mosse(PARTITA)
    assert isinstance(mosse, list)
    assert len(mosse) > 0


def test_ogni_mossa_rispetta_il_contratto():
    """Ogni mossa deve avere i tre campi del contratto Mossa."""
    mosse = estrai_mosse(PARTITA)
    for m in mosse:
        assert "uci" in m
        assert "san" in m
        assert "fen_before" in m


def test_la_prima_mossa_e_corretta():
    """
    Nella partita di esempio la prima mossa del Bianco e' Nf3.
    In notazione UCI e' g1f3 (cavallo da g1 a f3).
    """
    mosse = estrai_mosse(PARTITA)
    assert mosse[0]["san"] == "Nf3"
    assert mosse[0]["uci"] == "g1f3"


def test_il_numero_di_mosse_coincide():
    """estrai_mosse e estrai_dati_partita devono contare lo stesso numero."""
    dati = estrai_dati_partita(PARTITA)
    mosse = estrai_mosse(PARTITA)
    assert len(mosse) == dati["numero_mosse"]
