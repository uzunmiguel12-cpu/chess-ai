"""
Test di ml/dataset_lichess.py su un mini-dump SINTETICO con [%eval]:
  - filtri: passa solo la partita standard non-bullet con eval e Elo in fascia;
  - colonne identiche a dataset_posizionale.intestazioni();
  - matematica del cp_loss verificata a mano (POV Bianco e POV Nero);
  - decompressione .zst.

Esecuzione:  pytest test_dataset_lichess.py -q     (dalla cartella ml/)
"""

import csv
import random
import subprocess
import sys
import os

import chess
import chess.pgn
import pytest

_QUI = os.path.dirname(os.path.abspath(__file__))

# eval controllati (in pedoni, POV Bianco), uno per semi-tratto
EVALS = [0.2, 0.1, 0.3, 0.2, 0.4, 0.3, 0.5, 0.2, 0.4, 0.3,     # ply 1-10 (teoria, saltati)
         -0.6, -0.4, 0.1, 0.0, 0.3, -0.2, 0.5, 0.4, 0.2, 0.1, 0.6, 0.2, 0.3, 0.1]

INTESTAZIONE = {
    "Event": "Rated Blitz game", "Site": "https://lichess.org/abcd1234",
    "White": "a", "Black": "b", "Result": "*",
    "WhiteElo": "1600", "BlackElo": "1550",
    "TimeControl": "300+0", "Variant": "Standard",
}


def _partita(headers, con_eval=True, plies=24, evals=None, seme=7):
    rnd = random.Random(seme)
    g = chess.pgn.Game()
    for k, v in headers.items():
        g.headers[k] = v
    b = chess.Board()
    node = g
    for i in range(plies):
        mv = rnd.choice(list(b.legal_moves))
        node = node.add_variation(mv)
        if con_eval:
            e = evals[i] if evals else round(rnd.uniform(-1.5, 1.5), 2)
            node.comment = f"[%eval {e}]"
        b.push(mv)
        if b.is_game_over():
            break
    return g


@pytest.fixture
def mini_dump(tmp_path):
    percorso = tmp_path / "dump.pgn"
    partite = [
        _partita(dict(INTESTAZIONE), True, 24, EVALS),                                   # VALIDA
        _partita({**INTESTAZIONE, "Event": "Rated Bullet game", "TimeControl": "60+0",
                  "Site": "https://lichess.org/bull0001"}),                              # bullet: fuori
        _partita({**INTESTAZIONE, "Site": "https://lichess.org/noev0001"}, con_eval=False),  # senza eval
        _partita({**INTESTAZIONE, "WhiteElo": "2500",
                  "Site": "https://lichess.org/hielo001"}),                              # Elo fuori fascia
    ]
    with open(percorso, "w") as f:
        for g in partite:
            print(g, file=f)
            print(file=f)
    return percorso


def _esegui(pgn, out):
    subprocess.run(
        [sys.executable, os.path.join(_QUI, "dataset_lichess.py"),
         "--pgn", str(pgn), "--out", str(out), "--max-partite", "100"],
        check=True, capture_output=True, cwd=_QUI)
    with open(out) as f:
        return list(csv.DictReader(f))


def test_filtri_e_cploss(mini_dump, tmp_path):
    righe = _esegui(mini_dump, tmp_path / "out.csv")

    # 1) filtri: passa SOLO la partita valida
    assert {r["partita"] for r in righe} == {"lichess_abcd1234"}
    assert len(righe) == 14                       # 24 plies - 10 di teoria

    # 2) colonne identiche al dataset personale
    from dataset_posizionale import intestazioni
    assert list(righe[0].keys()) == intestazioni()

    # 3) cp_loss a mano — ply 11 (Bianco): e10=+30cp, e11=-60cp -> perde 90
    assert int(righe[0]["cp_loss"]) == 90
    assert int(righe[0]["eval_prima"]) == 30
    # ply 12 (Nero): e11=-60, e12=-40 -> dal POV del Nero perde 20
    assert int(righe[1]["cp_loss"]) == 20
    assert int(righe[1]["eval_prima"]) == 60


def test_zst(mini_dump, tmp_path):
    zstandard = pytest.importorskip("zstandard")
    compresso = tmp_path / "dump.pgn.zst"
    with open(mini_dump, "rb") as fi, open(compresso, "wb") as fo:
        zstandard.ZstdCompressor().copy_stream(fi, fo)
    righe = _esegui(compresso, tmp_path / "out.csv")
    assert len(righe) == 14
