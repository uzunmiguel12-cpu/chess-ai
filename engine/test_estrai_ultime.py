"""
Test dell'utility estrai_ultime.

Non richiede Stockfish. Crea PGN temporanei e li pulisce.

Esegui (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
import tempfile
import chess.pgn
from estrai_ultime import estrai_ultime


def _crea_pgn(percorso, n):
    """Crea un PGN con n partite numerate."""
    blocchi = []
    for i in range(1, n + 1):
        blocchi.append(
            f'[Event "Partita {i}"]\n[White "A"]\n[Black "B"]\n[Result "1-0"]\n\n'
            f'1. e4 e5 1-0'
        )
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocchi) + "\n")


def test_estrae_il_numero_giusto():
    d = tempfile.mkdtemp()
    try:
        ing = os.path.join(d, "in.pgn")
        out = os.path.join(d, "out.pgn")
        _crea_pgn(ing, 10)
        scritte = estrai_ultime(ing, 3, out)
        assert scritte == 3
    finally:
        import shutil
        shutil.rmtree(d)


def test_prende_le_ultime():
    """Estraendo le ultime 2 da 5 partite, devono essere la 4 e la 5."""
    d = tempfile.mkdtemp()
    try:
        ing = os.path.join(d, "in.pgn")
        out = os.path.join(d, "out.pgn")
        _crea_pgn(ing, 5)
        estrai_ultime(ing, 2, out)
        # rileggiamo il file prodotto e controlliamo gli Event
        eventi = []
        with open(out, "r", encoding="utf-8") as f:
            while True:
                g = chess.pgn.read_game(f)
                if g is None:
                    break
                eventi.append(g.headers.get("Event"))
        assert eventi == ["Partita 4", "Partita 5"]
    finally:
        import shutil
        shutil.rmtree(d)


def test_n_maggiore_del_totale():
    """Se chiedo piu' partite di quante ce ne sono, le prende tutte."""
    d = tempfile.mkdtemp()
    try:
        ing = os.path.join(d, "in.pgn")
        out = os.path.join(d, "out.pgn")
        _crea_pgn(ing, 3)
        scritte = estrai_ultime(ing, 100, out)
        assert scritte == 3
    finally:
        import shutil
        shutil.rmtree(d)
