"""
Test del modulo profilo giocatore (scala stile Chess.com).

Non richiede Stockfish: dati finti in cartella temporanea, puliti alla fine.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
import pytest
from profilo import costruisci_profilo, _normalizza

POS_AP = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
POS_FIN = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"


def _m(gravita, fase):
    return {"san": "x", "centipawn_loss": 0,
            "fen": POS_AP if fase == "apertura" else POS_FIN,
            "gravita": gravita, "fase": fase, "tipo_tattico": None}


@pytest.fixture
def cartella_con_partite():
    cartella = tempfile.mkdtemp()
    # Miguel col Bianco: 1 blunder in finale (mosse pari = Bianco).
    p1 = {"bianco": "Miguel", "nero": "Avv", "risultato": "0-1", "mosse": [
        _m("best", "apertura"), _m("good", "apertura"),
        _m("blunder", "finale"), _m("excellent", "finale"),
    ]}
    # Miguel col Nero (nome con maiuscole/spazi diversi): 1 mistake in finale.
    p2 = {"bianco": "Avv2", "nero": "miguel ", "risultato": "1-0", "mosse": [
        _m("good", "apertura"), _m("mistake", "finale"),
    ]}
    # Altro giocatore: non deve entrare nel profilo di Miguel.
    p3 = {"bianco": "Tizio", "nero": "Caio", "risultato": "1-0", "mosse": [
        _m("blunder", "apertura"),
    ]}
    for i, p in enumerate([p1, p2, p3], 1):
        with open(os.path.join(cartella, f"p_{i:04d}.json"), "w", encoding="utf-8") as f:
            json.dump(p, f)
    yield cartella
    shutil.rmtree(cartella)


def test_normalizza_nomi():
    assert _normalizza("Miguel") == _normalizza("miguel ")
    assert _normalizza("  ANNA ") == "anna"


def test_trova_le_partite_giuste(cartella_con_partite):
    p = costruisci_profilo("Miguel", cartella_con_partite)
    assert p is not None
    assert p["partite_analizzate"] == 2


def test_riconosce_la_debolezza(cartella_con_partite):
    """Gli errori gravi (1 blunder + 1 mistake) di Miguel sono in finale."""
    p = costruisci_profilo("Miguel", cartella_con_partite)
    assert p["debolezza_principale"] == "finale"
    assert p["errori_per_fase"].get("finale") == 2


def test_conta_le_gravita(cartella_con_partite):
    """Verifica che le etichette stile Chess.com siano contate."""
    p = costruisci_profilo("Miguel", cartella_con_partite)
    # Miguel ha: best, good (p1) + good (p2) ... e blunder + mistake
    assert p["conteggio_gravita"].get("blunder") == 1
    assert p["conteggio_gravita"].get("mistake") == 1


def test_non_mescola_giocatori(cartella_con_partite):
    p = costruisci_profilo("Miguel", cartella_con_partite)
    assert p["errori_per_fase"].get("apertura", 0) == 0


def test_giocatore_inesistente(cartella_con_partite):
    p = costruisci_profilo("Nessuno", cartella_con_partite)
    assert p is None
