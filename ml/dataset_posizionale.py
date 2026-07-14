"""
Costruisce il DATASET del modello posizionale da data/analisi/ (partite gia'
analizzate a profondita' 15): NESSUNA nuova chiamata a Stockfish.

Per ogni mossa gia' analizzata:
  - estrae le feature posizionali dalla FEN (prima) e dopo la mossa (dopo);
  - riusa il centipawn_loss gia' calcolato come target;
  - marca la mossa come TATTICA (esclusa dal training) se la best move e'
    cattura / scacco / promozione (stesso criterio di ml/analizza_posizionale.py)
    oppure se centipawn_loss >= 300;
  - filtro di sanita' identico a estrai_errori.py: scarta posizioni oltre ±700 cp;
  - salta i primi 10 semi-tratti (teoria d'apertura).

Scrive data/dataset_posizionale.csv (append + file di progresso, riprendibile).

Uso (riprendibile a blocchi):
    python dataset_posizionale.py                 # continua da dove era arrivato
    python dataset_posizionale.py --blocco 200    # quante partite per esecuzione
    python dataset_posizionale.py --reset         # riparte da zero
"""

import argparse
import csv
import glob
import json
import os

import chess

from caratteristiche_posizionali import (
    estrai_caratteristiche, FEATURE_SIMMETRICHE,
)

_QUI = os.path.dirname(os.path.abspath(__file__))
DIR_ANALISI = os.path.join(_QUI, "..", "data", "analisi")
CSV_USCITA = os.path.join(_QUI, "..", "data", "dataset_posizionale.csv")
FILE_PROGRESSO = os.path.join(_QUI, "..", "data", "dataset_posizionale.progress.json")

SOGLIA_TATTICA_CP = 300     # perdita oltre la quale l'errore e' quasi sempre tattico
SANITA_CP = 700             # posizioni gia' decise: fuori dal training
SALTA_APERTURA = 10         # semi-tratti di teoria da ignorare


def mossa_tattica(board_prima: chess.Board, best_uci: str, cp_loss: int) -> bool:
    """Stesso criterio di ml/analizza_posizionale.py: la best e' cattura/scacco/
    promozione, oppure la perdita e' da capogiro (>=300)."""
    if cp_loss >= SOGLIA_TATTICA_CP:
        return True
    if not best_uci:
        return False
    try:
        best = chess.Move.from_uci(best_uci)
    except ValueError:
        return False
    if best not in board_prima.legal_moves:
        return False
    return (board_prima.is_capture(best)
            or board_prima.gives_check(best)
            or best.promotion is not None)


def intestazioni():
    dummy = estrai_caratteristiche(chess.Board())
    campi = ["partita", "n_mossa", "san", "muove_bianco", "cp_loss", "tattica", "eval_prima"]
    for k in dummy:
        campi += [f"pre_{k}", f"d_{k}"]
    return campi


def riga_dataset(partita_id, ply, mossa, f_prima, f_dopo, muove_bianco):
    riga = {
        "partita": partita_id,
        "n_mossa": (ply + 1) // 2,
        "san": mossa.get("san", ""),
        "muove_bianco": int(muove_bianco),
        "cp_loss": mossa["centipawn_loss"],
        "tattica": 0,
        "eval_prima": mossa["eval_prima"],
    }
    segno = 1 if muove_bianco else -1
    for k in f_prima:
        if k in FEATURE_SIMMETRICHE:
            riga[f"pre_{k}"] = f_prima[k]
            riga[f"d_{k}"] = f_dopo[k] - f_prima[k]
        else:
            riga[f"pre_{k}"] = segno * f_prima[k]
            riga[f"d_{k}"] = segno * (f_dopo[k] - f_prima[k])
    return riga


def elabora_partita(percorso, writer):
    """Estrae le righe di una partita. Ritorna (righe_scritte, mosse_totali)."""
    with open(percorso, encoding="utf-8") as f:
        dati = json.load(f)
    partita_id = os.path.splitext(os.path.basename(percorso))[0]
    scritte = 0
    for ply, mossa in enumerate(dati.get("mosse", []), start=1):
        if ply <= SALTA_APERTURA:
            continue
        campi_ok = all(k in mossa for k in ("fen", "move_uci", "centipawn_loss", "eval_prima"))
        if not campi_ok or mossa["centipawn_loss"] is None:
            continue
        if abs(mossa["eval_prima"]) > SANITA_CP:
            continue
        try:
            board = chess.Board(mossa["fen"])
            mv = chess.Move.from_uci(mossa["move_uci"])
            if mv not in board.legal_moves:
                continue
        except (ValueError, AssertionError):
            continue

        muove_bianco = board.turn == chess.WHITE
        f_prima = estrai_caratteristiche(board)
        tattica = mossa_tattica(board, mossa.get("best_move_uci", ""), mossa["centipawn_loss"])
        board.push(mv)
        f_dopo = estrai_caratteristiche(board)

        riga = riga_dataset(partita_id, ply, mossa, f_prima, f_dopo, muove_bianco)
        riga["tattica"] = int(tattica)
        writer.writerow(riga)
        scritte += 1
    return scritte, len(dati.get("mosse", []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocco", type=int, default=200, help="partite per esecuzione")
    ap.add_argument("--reset", action="store_true", help="riparte da zero")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(DIR_ANALISI, "*.json")))
    if not files:
        print(f"Nessun file in {DIR_ANALISI}")
        return

    fatto = 0
    if args.reset:
        for p in (CSV_USCITA, FILE_PROGRESSO):
            if os.path.exists(p):
                os.remove(p)
    if os.path.exists(FILE_PROGRESSO):
        fatto = json.load(open(FILE_PROGRESSO)).get("partite_fatte", 0)

    nuovo_file = not os.path.exists(CSV_USCITA)
    out = open(CSV_USCITA, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out, fieldnames=intestazioni())
    if nuovo_file:
        writer.writeheader()

    da_fare = files[fatto:fatto + args.blocco]
    righe = 0
    for percorso in da_fare:
        r, _ = elabora_partita(percorso, writer)
        righe += r
        fatto += 1
        if fatto % 50 == 0:
            out.flush()
            json.dump({"partite_fatte": fatto, "totale": len(files)},
                      open(FILE_PROGRESSO, "w"))

    out.close()
    json.dump({"partite_fatte": fatto, "totale": len(files)},
              open(FILE_PROGRESSO, "w"))
    print(f"Elaborate {len(da_fare)} partite ({righe} righe). "
          f"Progresso: {fatto}/{len(files)}.")


if __name__ == "__main__":
    main()
