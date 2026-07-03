"""
Scarica il dataset ECO delle aperture (lichess/chess-openings) e lo salva in
data/aperture_eco.tsv con le mosse in UCI. Colonne di output: eco <TAB> name <TAB> uci.

Perche': la spina dati delle aperture usa dati REALI. L'Opening Explorer LIVE non e'
raggiungibile dalla rete dell'utente (401 su tutto l'host), quindi partiamo dai nomi e
dalle linee ECO in locale. Questo script FA richieste HTTP a GitHub: lanciarlo UNA volta.

Uso (dalla cartella rag, con la venv attiva):
    python scarica_eco.py
"""

import os
import re
import io
import csv
import logging

import chess
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")

BASE = "https://raw.githubusercontent.com/lichess-org/chess-openings/master/"
FILE = ["a.tsv", "b.tsv", "c.tsv", "d.tsv", "e.tsv"]
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "aperture_eco.tsv")

_NUM = re.compile(r"^\d+\.(\.\.)?$")  # "1." oppure "1..." (numeri di mossa)


def san_a_uci(pgn_san):
    """
    Converte il movetext SAN dell'ECO (es. '1. e4 e5 2. Nf3 Nc6') nella sequenza UCI
    ('e2e4 e7e5 g1f3 b8c6'). Restituisce '' se una mossa non e' legale/parsabile.
    """
    board = chess.Board()
    ucis = []
    for tok in pgn_san.split():
        if _NUM.match(tok) or tok in ("1-0", "0-1", "1/2-1/2", "*"):
            continue
        try:
            mossa = board.push_san(tok)
        except Exception:
            return ""
        ucis.append(mossa.uci())
    return " ".join(ucis)


def scarica():
    righe = []
    saltate = 0
    for nome_file in FILE:
        url = BASE + nome_file
        logger.info("Scarico %s ...", url)
        r = requests.get(url, timeout=30,
                         headers={"User-Agent": "chess-ai openings module (uzunmiguel12@gmail.com)"})
        r.raise_for_status()
        lettore = csv.reader(io.StringIO(r.text), delimiter="\t")
        intestazione = True
        for campi in lettore:
            if intestazione:
                intestazione = False
                continue
            if len(campi) < 3:
                continue
            eco, nome, pgn = campi[0], campi[1], campi[2]
            uci = san_a_uci(pgn)
            if not uci:
                saltate += 1
                continue
            righe.append((eco, nome, uci))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["eco", "name", "uci"])
        w.writerows(righe)
    logger.info("Fatto. Linee salvate: %d (saltate non parsabili: %d) in %s",
                len(righe), saltate, OUT)
    return len(righe)


if __name__ == "__main__":
    n = scarica()
    print(f"\nDataset ECO salvato: {n} linee in data/aperture_eco.tsv\n")
