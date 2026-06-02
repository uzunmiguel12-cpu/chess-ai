"""
Test del modulo arricchisci (collegamento categorie <- analisi).

Non richiede Stockfish. Usa file temporanei.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
from arricchisci import arricchisci_partita, arricchisci_tutte

POS_INIZIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _partita_finta():
    return {
        "bianco": "Tizio",
        "nero": "Caio",
        "risultato": "1-0",
        "mosse": [
            {"fen": POS_INIZIALE, "move_uci": "e2e4", "san": "e4", "centipawn_loss": 10},
            {"fen": POS_INIZIALE, "move_uci": "d2d4", "san": "d4", "centipawn_loss": 350},
        ],
    }


def test_arricchisce_le_mosse():
    risultato = arricchisci_partita(_partita_finta())
    for m in risultato["mosse"]:
        assert "gravita" in m
        assert "fase" in m
        assert "tipo_tattico" in m


def test_mantiene_i_metadati():
    risultato = arricchisci_partita(_partita_finta())
    assert risultato["bianco"] == "Tizio"
    assert risultato["nero"] == "Caio"
    assert risultato["risultato"] == "1-0"


def test_gravita_corretta_per_mossa():
    """Scala stile Chess.com: loss 10 = excellent, loss 350 = blunder."""
    risultato = arricchisci_partita(_partita_finta())
    assert risultato["mosse"][0]["gravita"] == "excellent"
    assert risultato["mosse"][1]["gravita"] == "blunder"


def test_arricchisci_tutte_su_cartelle_temporanee():
    cartella_in = tempfile.mkdtemp()
    cartella_out = tempfile.mkdtemp()
    try:
        with open(os.path.join(cartella_in, "prova_0001.json"), "w", encoding="utf-8") as f:
            json.dump(_partita_finta(), f)
        n = arricchisci_tutte(cartella_in, cartella_out)
        assert n == 1
        out = os.path.join(cartella_out, "prova_0001.json")
        assert os.path.exists(out)
        with open(out, "r", encoding="utf-8") as f:
            dato = json.load(f)
        assert "gravita" in dato["mosse"][0]
    finally:
        shutil.rmtree(cartella_in)
        shutil.rmtree(cartella_out)
