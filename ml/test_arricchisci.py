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
from arricchisci import arricchisci_partita, arricchisci_tutte, _aggiungi_tipo_tattico

POS_INIZIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Posizione (Bianco al tratto) in cui la MOSSA MIGLIORE Rd1 (d2d1) porta a una
# posizione in cui il Nero ha una forchetta di cavallo (Ng4-f2 su Re1 e Td1).
FEN_BEST_FORCHETTA = "4k3/8/8/8/6n1/8/3R4/7K w - - 0 1"
# Posizione (Bianco al tratto) in cui la mossa migliore (spinta di pedone e2e4)
# e' puramente posizionale: nessun pattern tattico.
FEN_BEST_POSIZIONALE = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"


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


def test_tipo_tattico_dalla_best_move_forchetta():
    """
    Un errore la cui MOSSA MIGLIORE crea una forchetta -> tipo_tattico
    'forchetta', anche se la mossa effettivamente giocata non era tattica.
    """
    mossa = {
        "fen": FEN_BEST_FORCHETTA,
        "move_uci": "h1g1",          # mossa giocata: spostamento di re, non tattico
        "best_move_uci": "d2d1",     # mossa migliore: porta alla forchetta
        "gravita": "blunder",
    }
    risultato = _aggiungi_tipo_tattico(mossa)
    assert risultato["tipo_tattico"] == "forchetta"


def test_tipo_tattico_best_move_posizionale_resta_none():
    """Best move puramente posizionale (nessun pattern) -> tipo_tattico None."""
    mossa = {
        "fen": FEN_BEST_POSIZIONALE,
        "move_uci": "e1d1",
        "best_move_uci": "e2e4",
        "gravita": "mistake",
    }
    risultato = _aggiungi_tipo_tattico(mossa)
    assert risultato["tipo_tattico"] is None


def test_tipo_tattico_best_move_mancante_o_illegale():
    """best_move_uci assente o illegale -> None senza crash."""
    mancante = _aggiungi_tipo_tattico({
        "fen": FEN_BEST_FORCHETTA,
        "move_uci": "h1g1",
        "gravita": "blunder",
    })
    assert mancante["tipo_tattico"] is None

    vuoto = _aggiungi_tipo_tattico({
        "fen": FEN_BEST_FORCHETTA,
        "move_uci": "h1g1",
        "best_move_uci": "",
        "gravita": "blunder",
    })
    assert vuoto["tipo_tattico"] is None

    illegale = _aggiungi_tipo_tattico({
        "fen": FEN_BEST_FORCHETTA,
        "move_uci": "h1g1",
        "best_move_uci": "a1a8",     # mossa illegale in questa posizione
        "gravita": "blunder",
    })
    assert illegale["tipo_tattico"] is None


def test_tipo_tattico_solo_sugli_errori():
    """
    Le mosse non-errore (gravita non analizzata) -> tipo_tattico None, anche se
    la best move sarebbe tattica.
    """
    mossa = {
        "fen": FEN_BEST_FORCHETTA,
        "move_uci": "h1g1",
        "best_move_uci": "d2d1",     # tattica, ma la mossa non e' un errore
        "gravita": "excellent",
    }
    risultato = _aggiungi_tipo_tattico(mossa)
    assert risultato["tipo_tattico"] is None


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
