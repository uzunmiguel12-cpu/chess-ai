"""
Test del modulo piano (collegamento profilo -> puzzle).

Non richiede Stockfish. Crea un profilo finto e un mini-database puzzle in
cartelle/file temporanei, e verifica che il piano si costruisca correttamente.

Esegui (dalla cartella rag, con ambiente attivo):
    pytest
"""

import os
import sys
import json
import sqlite3
import shutil
import tempfile
import pytest

_QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_QUI, "..", "ml"))

from piano import costruisci_piano, _combinazioni_per_frequenza

POS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _m(g, f, t):
    return {"san": "x", "centipawn_loss": 0, "fen": POS,
            "gravita": g, "fase": f, "tipo_tattico": t}


@pytest.fixture
def ambiente():
    """Crea cartella categorie con profilo finto + database puzzle finto."""
    cartella = tempfile.mkdtemp()
    db_path = os.path.join(cartella, "puzzle.db")

    # profilo: 8 pezzo_in_presa mediogioco, 5 forchetta mediogioco
    mosse = []
    for _ in range(8):
        mosse += [_m("blunder", "mediogioco", "pezzo_in_presa"), _m("best", "mediogioco", None)]
    for _ in range(5):
        mosse += [_m("blunder", "mediogioco", "forchetta"), _m("best", "mediogioco", None)]
    cat = os.path.join(cartella, "categorie")
    os.makedirs(cat)
    with open(os.path.join(cat, "p1.json"), "w", encoding="utf-8") as f:
        json.dump({"bianco": "Test", "nero": "Avv", "risultato": "1-0", "mosse": mosse}, f)

    # database: abbastanza puzzle per i due blocchi
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""CREATE TABLE puzzle (id TEXT PRIMARY KEY, fen TEXT, moves TEXT,
                 rating INTEGER, popularity INTEGER, nb_plays INTEGER,
                 themes TEXT, game_url TEXT)""")
    rows = []
    for i in range(20):
        rows.append((f"hp{i}", "f", "m", 1100 + i, 90, 100, "middlegame hangingPiece short", "u"))
    for i in range(15):
        rows.append((f"fk{i}", "f", "m", 1100 + i, 85, 100, "middlegame fork short", "u"))
    c.executemany("INSERT INTO puzzle VALUES (?,?,?,?,?,?,?,?)", rows)
    c.execute("CREATE INDEX idx_rating ON puzzle(rating)")
    c.execute("CREATE INDEX idx_themes ON puzzle(themes)")
    conn.commit()
    conn.close()

    yield {"categorie": cat, "db": db_path}
    shutil.rmtree(cartella)


def test_piano_si_costruisce(ambiente):
    piano = costruisci_piano("Test", ambiente["db"],
                             cartella_categorie=ambiente["categorie"],
                             elo_min=1050, elo_max=1250)
    assert piano is not None
    assert len(piano["blocchi"]) == 2


def test_blocchi_ordinati_per_frequenza(ambiente):
    """Il primo blocco deve essere il pezzo in presa (8 errori > 5 forchette)."""
    piano = costruisci_piano("Test", ambiente["db"],
                             cartella_categorie=ambiente["categorie"],
                             elo_min=1050, elo_max=1250)
    assert piano["blocchi"][0]["motivo"] == "pezzo_in_presa"
    assert piano["blocchi"][1]["motivo"] == "forchetta"
    assert piano["blocchi"][0]["conteggio_errori"] > piano["blocchi"][1]["conteggio_errori"]


def test_blocchi_hanno_puzzle(ambiente):
    piano = costruisci_piano("Test", ambiente["db"],
                             cartella_categorie=ambiente["categorie"],
                             elo_min=1050, elo_max=1250)
    for b in piano["blocchi"]:
        assert b["n_puzzle"] >= 5
        assert len(b["puzzle"]) == b["n_puzzle"]


def test_blocchi_puzzle_proporzionali_alla_frequenza(ambiente):
    """#7: il tema con piu' errori riceve PIU' puzzle di quello con meno errori."""
    piano = costruisci_piano("Test", ambiente["db"],
                             cartella_categorie=ambiente["categorie"],
                             elo_min=1050, elo_max=1250, puzzle_per_blocco=10)
    per_motivo = {b["motivo"]: b["n_puzzle"] for b in piano["blocchi"]}
    # pezzo_in_presa: 8 errori (dominante) -> puzzle_per_blocco; forchetta: 5 -> meno.
    assert per_motivo["pezzo_in_presa"] > per_motivo["forchetta"]
    assert per_motivo["forchetta"] >= 5   # ma mai sotto il minimo


def test_combinazioni_ordinamento():
    profilo_finto = {
        "tattico_per_fase": {
            "pezzo_in_presa": {"mediogioco": 8, "apertura": 2},
            "forchetta": {"mediogioco": 5},
        }
    }
    comb = _combinazioni_per_frequenza(profilo_finto)
    # la combinazione piu' frequente (8) deve essere prima
    assert comb[0] == ("pezzo_in_presa", "mediogioco", 8)


def test_giocatore_inesistente(ambiente):
    piano = costruisci_piano("Nessuno", ambiente["db"],
                             cartella_categorie=ambiente["categorie"])
    assert piano is None
