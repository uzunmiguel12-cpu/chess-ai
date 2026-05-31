"""
Parser PGN (Fase 1).

Funzioni:
- estrai_dati_partita: metadati della partita (giocatori, risultato, n. mosse)
- estrai_mosse: lista delle mosse nel formato del contratto Mossa
  (uci, san, fen_before) definito in docs/CONTRATTI_DATI.md

Uso:  python parser.py partita_esempio.pgn
"""

import sys
import logging
import chess
import chess.pgn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine")


def _leggi_prima_partita(percorso_file):
    """Apre il file e restituisce il primo oggetto partita, o None."""
    with open(percorso_file, "r", encoding="utf-8") as f:
        return chess.pgn.read_game(f)


def estrai_dati_partita(percorso_file):
    """
    Legge la prima partita da un file PGN e RESTITUISCE i suoi metadati
    come dizionario. Restituisce None se nel file non c'e' nessuna partita.
    """
    logger.info("Apro il file PGN: %s", percorso_file)
    partita = _leggi_prima_partita(percorso_file)

    if partita is None:
        logger.error("Nessuna partita trovata nel file")
        return None

    numero_mosse = sum(1 for _ in partita.mainline_moves())

    dati = {
        "bianco": partita.headers.get("White", "Sconosciuto"),
        "nero": partita.headers.get("Black", "Sconosciuto"),
        "risultato": partita.headers.get("Result", "?"),
        "numero_mosse": numero_mosse,
    }
    logger.info("Metadati letti correttamente")
    return dati


def estrai_mosse(percorso_file):
    """
    Legge la prima partita da un file PGN e RESTITUISCE la lista delle mosse,
    ognuna nel formato del contratto Mossa:
        {"uci": ..., "san": ..., "fen_before": ...}

    Per calcolare san e fen_before serve sapere com'era la scacchiera PRIMA
    di ogni mossa: partiamo dalla posizione iniziale e facciamo avanzare la
    scacchiera una mossa alla volta.

    Restituisce None se nel file non c'e' nessuna partita.
    """
    logger.info("Estraggo le mosse da: %s", percorso_file)
    partita = _leggi_prima_partita(percorso_file)

    if partita is None:
        logger.error("Nessuna partita trovata nel file")
        return None

    # board parte dalla posizione iniziale e avanza mossa per mossa.
    board = partita.board()
    mosse = []

    for mossa in partita.mainline_moves():
        # Prima di applicare la mossa, registriamo la posizione attuale
        # e la notazione leggibile (che dipende da questa posizione).
        fen_before = board.fen()
        san = board.san(mossa)
        uci = mossa.uci()

        mosse.append({
            "uci": uci,
            "san": san,
            "fen_before": fen_before,
        })

        # Applichiamo la mossa: la scacchiera avanza alla posizione successiva.
        board.push(mossa)

    logger.info("Estratte %d mosse", len(mosse))
    return mosse


def stampa_riepilogo(dati):
    """Mostra a schermo i metadati estratti."""
    print()
    print(f"Bianco:    {dati['bianco']}")
    print(f"Nero:      {dati['nero']}")
    print(f"Risultato: {dati['risultato']}")
    print(f"Mosse giocate (semimosse): {dati['numero_mosse']}")
    print()


def stampa_prime_mosse(mosse, quante=5):
    """Mostra le prime mosse nel formato del contratto, come esempio."""
    print(f"Prime {min(quante, len(mosse))} mosse (formato contratto):")
    for i, m in enumerate(mosse[:quante], start=1):
        print(f"  {i}. san={m['san']:6} uci={m['uci']}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python parser.py <file.pgn>")
        sys.exit(1)

    percorso = sys.argv[1]

    dati = estrai_dati_partita(percorso)
    if dati is not None:
        stampa_riepilogo(dati)

    mosse = estrai_mosse(percorso)
    if mosse is not None:
        stampa_prime_mosse(mosse)
