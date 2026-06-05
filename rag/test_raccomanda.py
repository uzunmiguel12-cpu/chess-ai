"""
Test del modulo raccomanda (pesca puzzle dal database per fase/motivo/Elo).

Non richiede Stockfish ne' il vero database. Crea un mini-database puzzle in un
file temporaneo e verifica i filtri, l'esclusione dei visti e i casi limite.

Esegui (dalla cartella rag, con ambiente attivo):
    pytest
"""

import os
import sqlite3
import tempfile
import pytest

from raccomanda import raccomanda


def _crea_db(percorso):
    """Mini-database: 20 hangingPiece middlegame, 15 fork opening, vari Elo."""
    conn = sqlite3.connect(percorso)
    c = conn.cursor()
    c.execute("""CREATE TABLE puzzle (id TEXT PRIMARY KEY, fen TEXT, moves TEXT,
                 rating INTEGER, popularity INTEGER, nb_plays INTEGER,
                 themes TEXT, game_url TEXT)""")
    rows = []
    for i in range(20):
        rows.append((f"hp{i}", "f", "m", 1100 + i, 90, 100,
                     "middlegame hangingPiece short", "u"))
    for i in range(15):
        rows.append((f"fk{i}", "f", "m", 1100 + i, 85, 100,
                     "opening fork short", "u"))
    # qualche puzzle fuori fascia per testare il filtro Elo
    for i in range(5):
        rows.append((f"hi{i}", "f", "m", 2000 + i, 80, 100,
                     "middlegame hangingPiece short", "u"))
    c.executemany("INSERT INTO puzzle VALUES (?,?,?,?,?,?,?,?)", rows)
    c.execute("CREATE INDEX idx_rating ON puzzle(rating)")
    c.execute("CREATE INDEX idx_themes ON puzzle(themes)")
    conn.commit()
    conn.close()


@pytest.fixture
def db():
    cartella = tempfile.mkdtemp()
    percorso = os.path.join(cartella, "puzzle.db")
    _crea_db(percorso)
    yield percorso
    # cleanup: chiudere ogni handle e rimuovere
    try:
        os.remove(percorso)
        os.rmdir(cartella)
    except OSError:
        pass


def test_filtra_per_fase(db):
    """Chiedendo middlegame devono tornare solo puzzle hangingPiece (nostri)."""
    puzzle = raccomanda(db, fase="mediogioco", elo_min=1050, elo_max=1250, quanti=50)
    assert len(puzzle) == 20
    assert all("middlegame" in p["themes"] for p in puzzle)


def test_filtra_per_motivo(db):
    """Chiedendo la forchetta devono tornare solo i 15 puzzle fork."""
    puzzle = raccomanda(db, motivo="forchetta", elo_min=1050, elo_max=1250, quanti=50)
    assert len(puzzle) == 15
    assert all("fork" in p["themes"] for p in puzzle)


def test_filtra_per_fase_e_motivo(db):
    """Fase + motivo si combinano: opening AND fork = i 15 puzzle fork."""
    puzzle = raccomanda(db, fase="apertura", motivo="forchetta",
                        elo_min=1050, elo_max=1250, quanti=50)
    assert len(puzzle) == 15
    # nessun puzzle hangingPiece (che e' middlegame) deve passare
    assert all("fork" in p["themes"] for p in puzzle)


def test_filtra_per_elo(db):
    """I puzzle a Elo 2000+ restano fuori dalla fascia 1050-1250."""
    puzzle = raccomanda(db, fase="mediogioco", elo_min=1050, elo_max=1250, quanti=50)
    assert all(1050 <= p["rating"] <= 1250 for p in puzzle)


def test_rispetta_quanti(db):
    puzzle = raccomanda(db, fase="mediogioco", elo_min=1050, elo_max=1250, quanti=5)
    assert len(puzzle) == 5


def test_esclude_visti(db):
    """Gli ID passati in escludi_id non devono ricomparire."""
    primi = raccomanda(db, fase="mediogioco", elo_min=1050, elo_max=1250, quanti=50)
    visti = [p["id"] for p in primi[:10]]
    secondi = raccomanda(db, fase="mediogioco", elo_min=1050, elo_max=1250,
                         quanti=50, escludi_id=visti)
    assert len(secondi) == 10  # 20 totali - 10 esclusi
    assert all(p["id"] not in visti for p in secondi)


def test_fase_sconosciuta(db):
    assert raccomanda(db, fase="non_esiste") == []


def test_motivo_sconosciuto(db):
    assert raccomanda(db, motivo="non_esiste") == []


def test_db_mancante():
    assert raccomanda("percorso/che/non/esiste.db", fase="mediogioco") == []


def test_struttura_puzzle(db):
    """Ogni puzzle ha le chiavi attese."""
    puzzle = raccomanda(db, fase="mediogioco", elo_min=1050, elo_max=1250, quanti=1)
    assert len(puzzle) == 1
    p = puzzle[0]
    assert set(p.keys()) == {"id", "fen", "moves", "rating", "themes"}
