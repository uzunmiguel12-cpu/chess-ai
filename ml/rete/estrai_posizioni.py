"""
S3 — Estrae POSIZIONI (fen + mossa) per il training della rete neurale.

La rete lavora sulla scacchiera grezza, non sulle feature riassunte: serve quindi
un CSV leggero con (partita, fen, mossa, cp_loss, tattica, eval_prima), dalle
STESSE fonti e con gli STESSI filtri dei dataset a feature:

  --analisi            -> data/analisi/ (partite personali, prof. 15, best move vera)
  --pgn / --url        -> dump Lichess con [%eval] (come ml/dataset_lichess.py)

Filtri identici: salta 10 semi-tratti, sanita' ±700, no bullet / Elo in fascia
(per il dump), tattica come nei rispettivi dataset.

Uso:
    python estrai_posizioni.py --analisi --out ../../data/posizioni_personali.csv
    python estrai_posizioni.py --url https://database.lichess.org/standard/lichess_db_standard_rated_2026-06.pgn.zst --max-partite 30000 --out ../../data/posizioni_lichess.csv
"""

import argparse
import csv
import glob
import json
import os
import sys

import chess
import chess.pgn

_QUI = os.path.dirname(os.path.abspath(__file__))
_ML = os.path.join(_QUI, "..")
if _ML not in sys.path:
    sys.path.insert(0, _ML)

from dataset_posizionale import mossa_tattica, SANITA_CP, SALTA_APERTURA   # noqa: E402
from dataset_lichess import (apri_sorgente, partita_valida,                # noqa: E402
                             eval_cp_bianco, SOGLIA_TATTICA_CP)

DIR_ANALISI = os.path.join(_ML, "..", "data", "analisi")
CAMPI = ["partita", "fen", "mossa", "cp_loss", "tattica", "eval_prima"]


def da_analisi(writer, max_partite=0):
    files = sorted(glob.glob(os.path.join(DIR_ANALISI, "*.json")))
    if max_partite:
        files = files[:max_partite]
    righe = 0
    for percorso in files:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
        pid = os.path.splitext(os.path.basename(percorso))[0]
        for ply, m in enumerate(dati.get("mosse", []), start=1):
            if ply <= SALTA_APERTURA:
                continue
            if not all(k in m for k in ("fen", "move_uci", "centipawn_loss", "eval_prima")):
                continue
            if m["centipawn_loss"] is None or abs(m["eval_prima"]) > SANITA_CP:
                continue
            try:
                board = chess.Board(m["fen"])
                mv = chess.Move.from_uci(m["move_uci"])
                if mv not in board.legal_moves:
                    continue
            except (ValueError, AssertionError):
                continue
            tatt = mossa_tattica(board, m.get("best_move_uci", ""), m["centipawn_loss"])
            writer.writerow({"partita": pid, "fen": m["fen"], "mossa": m["move_uci"],
                             "cp_loss": m["centipawn_loss"], "tattica": int(tatt),
                             "eval_prima": m["eval_prima"]})
            righe += 1
    return len(files), righe


def da_dump(writer, pgn=None, url=None, max_partite=10000, salta=0,
            elo_min=1400, elo_max=2200):
    stream = apri_sorgente(pgn, url)
    lette = utili = righe = 0
    while utili < salta + max_partite:
        game = chess.pgn.read_game(stream)
        if game is None:
            break
        lette += 1
        if not partita_valida(game.headers, elo_min, elo_max):
            continue
        primo = game.next()
        if primo is None or primo.eval() is None:
            continue
        utili += 1
        if utili <= salta:
            continue
        pid = "lichess_" + game.headers.get("Site", "?").rsplit("/", 1)[-1]
        board = game.board()
        eval_prec, ply = 15, 0
        for node in game.mainline():
            mv = node.move
            ply += 1
            ev = eval_cp_bianco(node)
            if ev is None:
                break
            muove_bianco = board.turn == chess.WHITE
            segno = 1 if muove_bianco else -1
            if ply > SALTA_APERTURA and abs(eval_prec) <= SANITA_CP:
                cp_loss = max(0, segno * (eval_prec - ev))
                tatt = (cp_loss >= SOGLIA_TATTICA_CP or board.is_capture(mv)
                        or board.gives_check(mv) or mv.promotion is not None)
                writer.writerow({"partita": pid, "fen": board.fen(), "mossa": mv.uci(),
                                 "cp_loss": int(cp_loss), "tattica": int(tatt),
                                 "eval_prima": segno * eval_prec})
                righe += 1
            board.push(mv)
            eval_prec = ev
        if utili % 200 == 0:
            print(f"  ... {utili} partite utili / {lette} lette, {righe} righe", flush=True)
    return utili - salta, righe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analisi", action="store_true", help="usa data/analisi/")
    ap.add_argument("--pgn")
    ap.add_argument("--url")
    ap.add_argument("--out", required=True)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--max-partite", type=int, default=10000)
    ap.add_argument("--salta-partite", type=int, default=0)
    ap.add_argument("--elo-min", type=int, default=1400)
    ap.add_argument("--elo-max", type=int, default=2200)
    args = ap.parse_args()
    if not (args.analisi or args.pgn or args.url):
        ap.error("serve --analisi oppure --pgn/--url")

    esiste = os.path.exists(args.out) and os.path.getsize(args.out) > 0
    out = open(args.out, "a" if args.append else "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(out, fieldnames=CAMPI)
    if not (args.append and esiste):
        writer.writeheader()

    if args.analisi:
        partite, righe = da_analisi(writer, args.max_partite if not args.url else 0)
    else:
        partite, righe = da_dump(writer, args.pgn, args.url, args.max_partite,
                                 args.salta_partite, args.elo_min, args.elo_max)
    out.close()
    print(f"Fatto: {partite} partite, {righe} righe -> {args.out}")


if __name__ == "__main__":
    main()
