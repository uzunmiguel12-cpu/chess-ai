"""
Utility (Fase 1/engine) - estrae le ultime N partite da un file PGN grande.

Le partite scaricate da Chess.com sono in ordine cronologico: le piu' recenti
stanno in fondo. Questo strumento legge un PGN con tante partite e ne scrive
uno nuovo con solo le ultime N, comodo per lavorare su un sottoinsieme.

Uso:  python estrai_ultime.py file_grande.pgn 30 file_piccolo.pgn
"""

import sys
import logging
import chess.pgn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine")


def estrai_ultime(percorso_in, n, percorso_out):
    """
    Legge tutte le partite da percorso_in e scrive le ULTIME n in percorso_out.
    RESTITUISCE il numero di partite effettivamente scritte.
    """
    # Leggiamo tutte le partite tenendole in memoria come oggetti.
    partite = []
    with open(percorso_in, "r", encoding="utf-8") as f:
        while True:
            partita = chess.pgn.read_game(f)
            if partita is None:
                break
            partite.append(partita)

    logger.info("Lette %d partite dal file", len(partite))

    # Prendiamo le ultime n (se ce ne sono meno di n, le prendiamo tutte).
    ultime = partite[-n:] if n < len(partite) else partite
    logger.info("Scrivo le ultime %d partite", len(ultime))

    # Le scriviamo nel nuovo file, una dopo l'altra.
    with open(percorso_out, "w", encoding="utf-8") as f:
        for partita in ultime:
            print(partita, file=f, end="\n\n")

    logger.info("Salvato in: %s", percorso_out)
    return len(ultime)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python estrai_ultime.py <file_in.pgn> <n> <file_out.pgn>")
        sys.exit(1)

    percorso_in = sys.argv[1]
    n = int(sys.argv[2])
    percorso_out = sys.argv[3]

    scritte = estrai_ultime(percorso_in, n, percorso_out)
    print()
    print(f"Estratte {scritte} partite in: {percorso_out}")
    print()
