"""
S2 — Dataset POSIZIONALE dal database Lichess (volume, zero ore di engine).

Legge un dump mensile di database.lichess.org (file .pgn.zst locale, .pgn locale,
oppure URL in streaming senza salvare il file) e accoda al CSV di training le
mosse delle partite che hanno gia' le valutazioni engine ([%eval ...] nei commenti,
presenti in una parte delle partite del dump).

Colonne IDENTICHE a ml/dataset_posizionale.py (stesso intestazioni()): i due CSV
si possono concatenare e allenare insieme con ml/allena_posizionale.py.

Filtri (coerenti con il progetto):
  - solo partite standard, NIENTE bullet (base < 180s scartata — regola del profilo);
  - entrambe le Elo nella fascia --elo-min/--elo-max (default 1400-2200);
  - salta i primi 10 semi-tratti (teoria, SALTA_APERTURA);
  - sanita': scarta posizioni oltre ±700 cp;
  - cp_loss dagli eval CONSECUTIVI del dump (POV di chi muove, clip come nel resto).

DIVERGENZA DICHIARATA sul filtro tattico [STIMA]: il dump non contiene la best
move, quindi "tattica" qui = cp_loss >= 300 OPPURE la mossa giocata e'
cattura/scacco/promozione. Nel dataset personale il criterio guarda la BEST move.
E' un'approssimazione piu' larga (butta qualche mossa posizionale in piu'):
accettabile perche' per il training contano le mosse NON tattiche.

Uso (sul PC, dove database.lichess.org e' raggiungibile):
    # streaming diretto dall'URL, si ferma a 20000 partite utili, senza salvare il dump
    python dataset_lichess.py --url https://database.lichess.org/standard/lichess_db_standard_rated_2026-05.pgn.zst --max-partite 20000

    # oppure da file scaricato a mano
    python dataset_lichess.py --pgn lichess_db_standard_rated_2026-05.pgn.zst --max-partite 20000

    # poi training combinato:
    python allena_posizionale.py --csv ../data/dataset_posizionale.csv ../data/dataset_lichess.csv
"""

import argparse
import csv
import io
import os
import sys
import urllib.request

import chess
import chess.pgn

from caratteristiche_posizionali import estrai_caratteristiche
from dataset_posizionale import intestazioni, riga_dataset, SANITA_CP, SALTA_APERTURA

_QUI = os.path.dirname(os.path.abspath(__file__))
CSV_DEFAULT = os.path.join(_QUI, "..", "data", "dataset_lichess.csv")

SOGLIA_TATTICA_CP = 300
PUNTEGGIO_MATTO = 10000
CLIP_CP = 1000
BASE_MINIMA_SECONDI = 180        # sotto: bullet, fuori dal training


def apri_sorgente(percorso=None, url=None):
    """Ritorna uno stream di testo PGN, decomprimendo al volo se .zst."""
    if url:
        grezzo = urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "chess-ai/S2"}))
        compresso = url.endswith(".zst")
    else:
        grezzo = open(percorso, "rb")
        compresso = percorso.endswith(".zst")
    if compresso:
        import zstandard
        flusso = zstandard.ZstdDecompressor(max_window_size=2 ** 31).stream_reader(grezzo)
    else:
        flusso = grezzo
    return io.TextIOWrapper(flusso, encoding="utf-8", errors="replace")


def partita_valida(headers, elo_min, elo_max):
    """Standard, non bullet, entrambe le Elo in fascia."""
    if headers.get("Variant", "Standard") != "Standard":
        return False
    tc = headers.get("TimeControl", "-")
    try:
        base = int(tc.split("+")[0])
    except ValueError:
        return False
    if base < BASE_MINIMA_SECONDI:
        return False
    try:
        eb, en = int(headers.get("WhiteElo", 0)), int(headers.get("BlackElo", 0))
    except ValueError:
        return False
    return elo_min <= eb <= elo_max and elo_min <= en <= elo_max


def eval_cp_bianco(node):
    """Eval del nodo (dopo la mossa) in centipawn dal POV del Bianco, o None."""
    score = node.eval()
    if score is None:
        return None
    s = score.white().score(mate_score=PUNTEGGIO_MATTO)
    return max(-CLIP_CP, min(CLIP_CP, s))


def elabora_partita(game, writer):
    """Estrae le righe di una partita del dump. Ritorna quante ne ha scritte."""
    partita_id = "lichess_" + game.headers.get("Site", "?").rsplit("/", 1)[-1]
    board = game.board()
    scritte = 0
    eval_prec = 15                    # convenzione: leggero vantaggio del Bianco in partenza
    ply = 0
    for node in game.mainline():
        mv = node.move
        ply += 1
        ev = eval_cp_bianco(node)
        if ev is None:                # eval finiti (es. coda gia' decisa): stop
            break
        muove_bianco = board.turn == chess.WHITE
        segno = 1 if muove_bianco else -1
        if ply > SALTA_APERTURA and abs(eval_prec) <= SANITA_CP:
            cp_loss = max(0, segno * (eval_prec - ev))
            tattica = (cp_loss >= SOGLIA_TATTICA_CP
                       or board.is_capture(mv)
                       or board.gives_check(mv)
                       or mv.promotion is not None)
            f_prima = estrai_caratteristiche(board)
            mossa = {"san": board.san(mv), "centipawn_loss": int(cp_loss),
                     "eval_prima": segno * eval_prec}
            board.push(mv)
            f_dopo = estrai_caratteristiche(board)
            riga = riga_dataset(partita_id, ply, mossa, f_prima, f_dopo, muove_bianco)
            riga["tattica"] = int(tattica)
            writer.writerow(riga)
            scritte += 1
        else:
            board.push(mv)
        eval_prec = ev
    return scritte


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", help="dump locale (.pgn o .pgn.zst)")
    ap.add_argument("--url", help="URL del dump (streaming, niente download su disco)")
    ap.add_argument("--out", default=CSV_DEFAULT)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--max-partite", type=int, default=10000,
                    help="quante partite UTILI (con eval) estrarre")
    ap.add_argument("--salta-partite", type=int, default=0,
                    help="salta le prime N partite utili (per riprendere)")
    ap.add_argument("--elo-min", type=int, default=1400)
    ap.add_argument("--elo-max", type=int, default=2200)
    args = ap.parse_args()
    if not args.pgn and not args.url:
        ap.error("serve --pgn oppure --url")

    stream = apri_sorgente(args.pgn, args.url)
    modo = "a" if args.append else "w"
    esiste = os.path.exists(args.out) and os.path.getsize(args.out) > 0
    out = open(args.out, modo, newline="", encoding="utf-8")
    writer = csv.DictWriter(out, fieldnames=intestazioni())
    if not (args.append and esiste):
        writer.writeheader()

    lette = utili = righe = 0
    try:
        while utili < args.salta_partite + args.max_partite:
            game = chess.pgn.read_game(stream)
            if game is None:
                break
            lette += 1
            if not partita_valida(game.headers, args.elo_min, args.elo_max):
                continue
            # eval presenti? guarda il primo nodo
            primo = game.next()
            if primo is None or primo.eval() is None:
                continue
            utili += 1
            if utili <= args.salta_partite:
                continue
            righe += elabora_partita(game, writer)
            if utili % 200 == 0:
                out.flush()
                print(f"  ... {utili} partite utili / {lette} lette, {righe} righe",
                      flush=True)
    except KeyboardInterrupt:
        print("Interrotto: salvo quanto fatto.")
    out.close()
    print(f"Fatto: {utili - args.salta_partite} partite utili su {lette} lette, "
          f"{righe} righe -> {args.out}")


if __name__ == "__main__":
    main()
