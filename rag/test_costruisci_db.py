"""
Test del modulo costruisci_db (CSV Lichess -> database SQLite).

Crea un mini-CSV finto in un file temporaneo e verifica che il database venga
costruito correttamente: righe caricate, indici creati, righe malformate saltate.

Esegui (dalla cartella rag, con ambiente attivo):
    pytest
"""

import os
import sqlite3
import tempfile
import pytest

from costruisci_db import costruisci

INTESTAZIONE = "PuzzleId,FEN,Moves,Rating,Popularity,NbPlays,Themes,GameUrl\n"


def _scrivi_csv(percorso, righe):
    with open(percorso, "w", encoding="utf-8", newline="") as f:
        f.write(INTESTAZIONE)
        for r in righe:
            f.write(",".join(r) + "\n")


@pytest.fixture
def cartella():
    c = tempfile.mkdtemp()
    yield c
    for nome in os.listdir(c):
        try:
            os.remove(os.path.join(c, nome))
        except OSError:
            pass
    try:
        os.rmdir(c)
    except OSError:
        pass


def test_costruisce_e_conta(cartella):
    csv_path = os.path.join(cartella, "p.csv")
    db_path = os.path.join(cartella, "p.db")
    _scrivi_csv(csv_path, [
        ("p1", "fen1", "e2e4", "1100", "90", "100", "fork", "url1"),
        ("p2", "fen2", "d2d4", "1200", "80", "50", "pin", "url2"),
        ("p3", "fen3", "g1f3", "1300", "70", "30", "skewer", "url3"),
    ])
    n = costruisci(csv_path, db_path)
    assert n == 3

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM puzzle").fetchone()[0] == 3
    riga = conn.execute("SELECT fen, rating, themes FROM puzzle WHERE id='p1'").fetchone()
    assert riga == ("fen1", 1100, "fork")
    conn.close()


def test_indici_creati(cartella):
    csv_path = os.path.join(cartella, "p.csv")
    db_path = os.path.join(cartella, "p.db")
    _scrivi_csv(csv_path, [("p1", "fen1", "e2e4", "1100", "90", "100", "fork", "url1")])
    costruisci(csv_path, db_path)

    conn = sqlite3.connect(db_path)
    indici = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    conn.close()
    assert "idx_rating" in indici
    assert "idx_themes" in indici


def test_righe_malformate_saltate(cartella):
    """Una riga con Rating non numerico viene saltata, le altre passano."""
    csv_path = os.path.join(cartella, "p.csv")
    db_path = os.path.join(cartella, "p.db")
    _scrivi_csv(csv_path, [
        ("p1", "fen1", "e2e4", "1100", "90", "100", "fork", "url1"),
        ("p2", "fen2", "d2d4", "abc", "80", "50", "pin", "url2"),   # Rating invalido
        ("p3", "fen3", "g1f3", "1300", "70", "30", "skewer", "url3"),
    ])
    n = costruisci(csv_path, db_path)
    assert n == 2

    conn = sqlite3.connect(db_path)
    ids = {r[0] for r in conn.execute("SELECT id FROM puzzle").fetchall()}
    conn.close()
    assert ids == {"p1", "p3"}


def test_ricrea_db_esistente(cartella):
    """Se il db esiste gia', viene ricreato pulito (niente accumulo)."""
    csv_path = os.path.join(cartella, "p.csv")
    db_path = os.path.join(cartella, "p.db")
    _scrivi_csv(csv_path, [("p1", "fen1", "e2e4", "1100", "90", "100", "fork", "url1")])
    costruisci(csv_path, db_path)
    # secondo CSV con un puzzle diverso
    _scrivi_csv(csv_path, [("p9", "fen9", "e2e4", "1500", "90", "100", "pin", "url9")])
    n = costruisci(csv_path, db_path)
    assert n == 1

    conn = sqlite3.connect(db_path)
    ids = {r[0] for r in conn.execute("SELECT id FROM puzzle").fetchall()}
    conn.close()
    assert ids == {"p9"}  # il vecchio p1 non c'e' piu'


def test_csv_mancante(cartella):
    db_path = os.path.join(cartella, "p.db")
    assert costruisci(os.path.join(cartella, "non_esiste.csv"), db_path) is None
