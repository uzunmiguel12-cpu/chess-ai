"""
Test del modulo estrai_errori (estrazione candidati-puzzle dalle analisi).

Non richiede Stockfish: usa file di analisi finti in cartella temporanea,
puliti alla fine.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
import pytest
from estrai_errori import (
    mio_colore,
    turno_da_fen,
    eval_dal_mio_punto_di_vista,
    posizione_contesa,
    cadenza_da_nome,
    raccogli_candidati,
    conta_per_soglia,
    salva_candidati,
)

# FEN di comodo: posizione iniziale (tocca al Bianco) e dopo 1.e4 (tocca al Nero).
FEN_BIANCO = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_NERO = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _m(fen, cpl, eval_prima, best="e2e4"):
    """Costruisce una mossa finta nel formato dei file di analisi."""
    return {"fen": fen, "move_uci": "d2d4", "san": "d4",
            "best_move_uci": best, "eval_prima": eval_prima,
            "eval_dopo": eval_prima - cpl, "centipawn_loss": cpl}


# --- Riconoscimento del colore ---

def test_colore_bianco():
    dato = {"bianco": "MigueL_uz", "nero": "Avv"}
    assert mio_colore(dato) == "w"


def test_colore_nero_case_insensitive():
    dato = {"bianco": "Avv", "nero": "miguel_UZ"}
    assert mio_colore(dato) == "b"


def test_colore_assente():
    dato = {"bianco": "Tizio", "nero": "Caio"}
    assert mio_colore(dato) is None


# --- Riconoscimento mossa mia dal turno FEN ---

def test_turno_da_fen():
    assert turno_da_fen(FEN_BIANCO) == "w"
    assert turno_da_fen(FEN_NERO) == "b"


# --- Filtro di sanita' ---

def test_eval_dal_mio_punto_di_vista():
    # Da Bianco resta uguale, da Nero si inverte.
    assert eval_dal_mio_punto_di_vista(300, True) == 300
    assert eval_dal_mio_punto_di_vista(300, False) == -300


def test_filtro_tiene_posizione_contesa():
    assert posizione_contesa(150) is True
    assert posizione_contesa(-200) is True


def test_filtro_scarta_gia_perso_e_gia_vincente():
    assert posizione_contesa(-800) is False   # ero gia' perso
    assert posizione_contesa(900) is False     # gia' vincevo facile


def test_filtro_scarta_mate_score():
    assert posizione_contesa(100000) is False
    assert posizione_contesa(-100000) is False


# --- Raccolta + conteggio su file finti ---

@pytest.fixture
def cartella():
    c = tempfile.mkdtemp()

    # Partita bullet, io Bianco: le mosse mie sono quelle con FEN " w ".
    bullet = {
        "bianco": "MigueL_uz", "nero": "Avv", "risultato": "0-1",
        "mosse": [
            _m(FEN_BIANCO, 250, 100),    # mia, contesa, cpl 250  -> candidato (>=200)
            _m(FEN_NERO, 400, 100),      # dell'avversario (turno nero) -> ignorata
            _m(FEN_BIANCO, 120, 50),     # mia, contesa, cpl 120  -> candidato (>=100)
            _m(FEN_BIANCO, 500, 900),    # mia ma gia' vincente   -> scartata dal filtro
        ],
    }
    with open(os.path.join(c, "bullet_0001.json"), "w", encoding="utf-8") as f:
        json.dump(bullet, f)

    # Partita rapid (non bullet), io Nero: le mosse mie sono quelle con FEN " b ".
    # Da Nero eval va invertita: eval_prima=-100 -> eval_mia=+100 (contesa).
    rapid = {
        "bianco": "Avv", "nero": "MigueL_uz", "risultato": "1-0",
        "mosse": [
            _m(FEN_BIANCO, 300, 100),    # turno bianco = avversario -> ignorata
            _m(FEN_NERO, 320, -100),     # mia, contesa, cpl 320  -> candidato (>=300)
        ],
    }
    with open(os.path.join(c, "rapid_0001.json"), "w", encoding="utf-8") as f:
        json.dump(rapid, f)

    # Partita che non gioco: deve essere saltata del tutto.
    altrui = {
        "bianco": "Tizio", "nero": "Caio", "risultato": "1-0",
        "mosse": [_m(FEN_BIANCO, 999, 0)],
    }
    with open(os.path.join(c, "rapid_0002.json"), "w", encoding="utf-8") as f:
        json.dump(altrui, f)

    yield c
    shutil.rmtree(c)


def test_cadenza_da_nome():
    assert cadenza_da_nome("bullet_0001.json") == "bullet"
    assert cadenza_da_nome("rapid_0001.json") == "altro"


def test_raccolta_riconosce_mosse_mie_e_filtro(cartella):
    candidati, scartati = raccogli_candidati(cartella)
    # Candidati attesi: cpl 250 e 120 (bullet, Bianco) + cpl 320 (rapid, Nero) = 3.
    assert len(candidati) == 3
    # Una mossa mia (gia' vincente) e' stata scartata dal filtro di sanita'.
    assert scartati == 1
    # La partita altrui non deve contribuire.
    assert all(c["fonte_file"] != "rapid_0002.json" for c in candidati)


def test_eval_mia_invertita_per_il_nero(cartella):
    candidati, _ = raccogli_candidati(cartella)
    rapid = [c for c in candidati if c["fonte_file"] == "rapid_0001.json"]
    assert len(rapid) == 1
    # eval_prima era -100 vista Bianco, ma giocando Nero il MIO valore e' +100.
    assert rapid[0]["eval_mia_prima"] == 100


def test_conteggio_per_soglia(cartella):
    candidati, _ = raccogli_candidati(cartella)
    conteggi = conta_per_soglia(candidati)
    # Bullet: cpl 250 e 120. >=100 -> 2, >=200 -> 1, >=300 -> 0.
    assert conteggi["bullet"] == {100: 2, 200: 1, 300: 0}
    # Altro (rapid): cpl 320. >=100 -> 1, >=200 -> 1, >=300 -> 1.
    assert conteggi["altro"] == {100: 1, 200: 1, 300: 1}
    # Totale.
    assert conteggi["totale"] == {100: 3, 200: 2, 300: 1}


def test_salvataggio(cartella):
    candidati, _ = raccogli_candidati(cartella)
    out = os.path.join(cartella, "candidati_errori.json")
    n = salva_candidati(candidati, out, soglia=200)
    # Sopra soglia 200: cpl 250 e 320 -> 2 salvati.
    assert n == 2
    with open(out, "r", encoding="utf-8") as f:
        salvati = json.load(f)
    assert len(salvati) == 2
    # Ogni candidato salvato ha tutti i campi richiesti.
    for c in salvati:
        for campo in ("fen", "mossa_giocata_uci", "soluzione_uci", "san_giocata",
                      "centipawn_loss", "eval_mia_prima", "fonte_file",
                      "indice_mossa", "cadenza"):
            assert campo in c
        assert c["centipawn_loss"] >= 200
