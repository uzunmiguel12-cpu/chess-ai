"""
Test del modulo arricchisci (collegamento categorie <- analisi).

Non richiede Stockfish: lavora su dati gia' prodotti. Crea file temporanei
in cartelle di prova e li pulisce alla fine.

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
    """Ogni mossa arricchita deve avere gravita, fase e tipo_tattico."""
    risultato = arricchisci_partita(_partita_finta())
    for m in risultato["mosse"]:
        assert "gravita" in m
        assert "fase" in m
        assert "tipo_tattico" in m


def test_mantiene_i_metadati():
    """I metadati della partita (giocatori, risultato) devono restare."""
    risultato = arricchisci_partita(_partita_finta())
    assert risultato["bianco"] == "Tizio"
    assert risultato["nero"] == "Caio"
    assert risultato["risultato"] == "1-0"


def test_gravita_corretta_per_mossa():
    """La seconda mossa (loss 350) deve essere un blunder."""
    risultato = arricchisci_partita(_partita_finta())
    assert risultato["mosse"][0]["gravita"] == "ok"
    assert risultato["mosse"][1]["gravita"] == "blunder"


def test_arricchisci_tutte_su_cartelle_temporanee():
    """
    Prova il flusso completo su cartelle temporanee: crea un file di analisi
    finto, lo arricchisce, verifica che il file di output esista e sia valido.
    """
    cartella_in = tempfile.mkdtemp()
    cartella_out = tempfile.mkdtemp()
    try:
        # Creiamo un file di analisi finto in entrata.
        with open(os.path.join(cartella_in, "prova_0001.json"), "w", encoding="utf-8") as f:
            json.dump(_partita_finta(), f)

        n = arricchisci_tutte(cartella_in, cartella_out)
        assert n == 1

        # Il file arricchito deve esistere ed essere valido.
        out = os.path.join(cartella_out, "prova_0001.json")
        assert os.path.exists(out)
        with open(out, "r", encoding="utf-8") as f:
            dato = json.load(f)
        assert "gravita" in dato["mosse"][0]
    finally:
        shutil.rmtree(cartella_in)
        shutil.rmtree(cartella_out)
