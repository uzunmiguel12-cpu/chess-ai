"""
Test del modulo profilo giocatore (con tasso di errore per fase).

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
def cartella_tasso():
    """
    Miguel (Bianco, mosse pari): 4 errori su 20 mosse in apertura (20%),
    3 errori su 4 mosse in finale (75%). Piu' errori assoluti in apertura,
    ma tasso piu' alto in finale.
    """
    cartella = tempfile.mkdtemp()
    mosse = []

    def agg(grav, fase):
        mosse.append(_m(grav, fase))   # Bianco
        mosse.append(_m("best", fase))  # Nero

    for i in range(20):
        agg("blunder" if i < 4 else "best", "apertura")
    for i in range(4):
        agg("blunder" if i < 3 else "best", "finale")

    p = {"bianco": "Miguel", "nero": "Avv", "risultato": "1-0", "mosse": mosse}
    with open(os.path.join(cartella, "p_0001.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)
    yield cartella
    shutil.rmtree(cartella)


def test_normalizza_nomi():
    assert _normalizza("Miguel") == _normalizza("miguel ")


def test_calcola_il_tasso(cartella_tasso):
    p = costruisci_profilo("Miguel", cartella_tasso)
    assert p["tasso_errore_per_fase"]["apertura"] == 20.0
    assert p["tasso_errore_per_fase"]["finale"] == 75.0


def test_debolezza_per_tasso_non_per_conteggio(cartella_tasso):
    """
    Apertura ha PIU' errori assoluti (4 vs 3), ma il finale ha tasso piu' alto.
    La debolezza deve essere il FINALE.
    """
    p = costruisci_profilo("Miguel", cartella_tasso)
    assert p["errori_per_fase"]["apertura"] == 4
    assert p["errori_per_fase"]["finale"] == 3
    assert p["debolezza_principale"] == "finale"


def test_mosse_per_fase_corrette(cartella_tasso):
    p = costruisci_profilo("Miguel", cartella_tasso)
    assert p["mosse_per_fase"]["apertura"] == 20
    assert p["mosse_per_fase"]["finale"] == 4


def test_giocatore_inesistente(cartella_tasso):
    assert costruisci_profilo("Nessuno", cartella_tasso) is None
