"""
Test del modulo profilo giocatore.

Non richiede Stockfish: lavora su dati arricchiti finti, creati in una cartella
temporanea e puliti alla fine.

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
    """Crea una cartella temporanea con partite finte e la pulisce dopo."""
    cartella = tempfile.mkdtemp()
    # Miguel col Bianco: 1 blunder in finale (mosse pari = Bianco).
    p1 = {"bianco": "Miguel", "nero": "Avv", "risultato": "0-1", "mosse": [
        _m("ok", "apertura"), _m("ok", "apertura"),
        _m("blunder", "finale"), _m("ok", "finale"),
    ]}
    # Miguel col Nero (nome con maiuscole/spazi diversi): 1 errore in finale.
    p2 = {"bianco": "Avv2", "nero": "miguel ", "risultato": "1-0", "mosse": [
        _m("ok", "apertura"), _m("errore", "finale"),
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
    """Miguel ha giocato 2 partite delle 3 presenti."""
    p = costruisci_profilo("Miguel", cartella_con_partite)
    assert p is not None
    assert p["partite_analizzate"] == 2


def test_riconosce_la_debolezza(cartella_con_partite):
    """Tutti gli errori gravi di Miguel sono in finale."""
    p = costruisci_profilo("Miguel", cartella_con_partite)
    assert p["debolezza_principale"] == "finale"
    assert p["errori_per_fase"].get("finale") == 2


def test_non_mescola_giocatori(cartella_con_partite):
    """Il blunder di Tizio (in apertura) non deve entrare nel profilo di Miguel."""
    p = costruisci_profilo("Miguel", cartella_con_partite)
    assert p["errori_per_fase"].get("apertura", 0) == 0


def test_giocatore_inesistente(cartella_con_partite):
    """Un nome che non ha giocato restituisce None."""
    p = costruisci_profilo("Nessuno", cartella_con_partite)
    assert p is None
