"""
Parser PGN - versione testabile (Fase 1).

Separa l'estrazione dei dati (funzione che RESTITUISCE i dati) dalla
stampa (che li mostra a schermo). Questo rende il codice testabile:
un test puo' chiamare estrai_dati_partita e verificare cosa restituisce.

Uso:  python parser.py partita_esempio.pgn
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


def estrai_dati_partita(percorso_file):
    """
    Legge la prima partita da un file PGN e RESTITUISCE i suoi dati
    come dizionario. Non stampa nulla: restituisce, cosi' il risultato
    puo' essere usato da altro codice o verificato da un test.

    Restituisce None se nel file non c'e' nessuna partita.
    """
    logger.info("Apro il file PGN: %s", percorso_file)

    with open(percorso_file, "r", encoding="utf-8") as f:
        partita = chess.pgn.read_game(f)

    if partita is None:
        logger.error("Nessuna partita trovata nel file")
        return None

    numero_mosse = 0
    for _ in partita.mainline_moves():
        numero_mosse += 1

    dati = {
        "bianco": partita.headers.get("White", "Sconosciuto"),
        "nero": partita.headers.get("Black", "Sconosciuto"),
        "risultato": partita.headers.get("Result", "?"),
        "numero_mosse": numero_mosse,
    }

    logger.info("Partita letta correttamente")
    return dati


def stampa_riepilogo(dati):
    """Mostra a schermo i dati estratti. Questa parte serve agli umani."""
    print()
    print(f"Bianco:    {dati['bianco']}")
    print(f"Nero:      {dati['nero']}")
    print(f"Risultato: {dati['risultato']}")
    print(f"Mosse giocate (semimosse): {dati['numero_mosse']}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python parser.py <file.pgn>")
        sys.exit(1)

    risultato = estrai_dati_partita(sys.argv[1])
    if risultato is not None:
        stampa_riepilogo(risultato)
