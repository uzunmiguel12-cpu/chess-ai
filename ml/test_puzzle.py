"""
Test del modulo puzzle (generazione puzzle dalle partite).

Non richiede Stockfish: dati finti in cartella temporanea, puliti alla fine.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
import pytest
from puzzle import genera_puzzle, _parse_args

POS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _m(gravita, fase, tipo=None, best="e2e4"):
    return {"san": "x", "move_uci": "d2d4", "best_move_uci": best,
            "fen": POS, "centipawn_loss": 0,
            "gravita": gravita, "fase": fase, "tipo_tattico": tipo}


@pytest.fixture
def cartella():
    c = tempfile.mkdtemp()
    # Miguel (Bianco, pari): un blunder mediogioco con forchetta, un mistake
    # apertura senza tipo, una mossa buona (non puzzle), un errore SENZA soluzione.
    mosse = [
        _m("blunder", "mediogioco", "forchetta"),   # puzzle
        _m("best", "mediogioco"),                    # nero, ignorato
        _m("mistake", "apertura"),                   # puzzle
        _m("best", "apertura"),                      # nero, ignorato
        _m("good", "finale"),                        # non e' errore, niente puzzle
        _m("best", "finale"),
        _m("blunder", "finale", best=None),          # errore SENZA soluzione: scartato
        _m("best", "finale"),
    ]
    p = {"bianco": "Miguel", "nero": "Avv", "risultato": "1-0", "mosse": mosse}
    with open(os.path.join(c, "p_0001.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)
    yield c
    shutil.rmtree(c)


def test_genera_solo_errori(cartella):
    """Solo mistake/blunder con soluzione: 2 puzzle (il blunder senza best e' scartato)."""
    puzzle = genera_puzzle("Miguel", cartella)
    assert len(puzzle) == 2


def test_scarta_errori_senza_soluzione(cartella):
    """Nessun puzzle deve avere soluzione vuota."""
    for p in genera_puzzle("Miguel", cartella):
        assert p["soluzione"]


def test_filtro_fase(cartella):
    puzzle = genera_puzzle("Miguel", cartella, fase="mediogioco")
    assert len(puzzle) == 1
    assert puzzle[0]["fase"] == "mediogioco"


def test_filtro_tipo(cartella):
    puzzle = genera_puzzle("Miguel", cartella, tipo_tattico="forchetta")
    assert len(puzzle) == 1
    assert puzzle[0]["tipo_tattico"] == "forchetta"


def test_struttura_puzzle(cartella):
    p = genera_puzzle("Miguel", cartella)[0]
    for campo in ("fen", "soluzione", "tua_mossa", "gravita", "fase", "partita"):
        assert campo in p


def test_giocatore_inesistente(cartella):
    assert genera_puzzle("Nessuno", cartella) == []


def test_parse_args():
    nome, fase, tipo = _parse_args(["Miguel", "--fase", "mediogioco", "--tipo", "forchetta"])
    assert nome == "Miguel"
    assert fase == "mediogioco"
    assert tipo == "forchetta"
