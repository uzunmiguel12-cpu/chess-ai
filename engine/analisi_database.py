"""
Modulo analisi database (Fase 2) - analizza piu' partite e salva un file
JSON per ognuna.

Caratteristiche:
- mostra l'avanzamento ("partita 3 di 100...")
- salva ogni partita appena analizzata (niente lavoro perso se si interrompe)
- salta le partite che hanno gia' il loro file (ripartenza senza rifare tutto)

I file vengono salvati in data/analisi/, ognuno conforme al contratto Analisi.

Uso:  python analisi_database.py partite_multiple.pgn
"""

import os
import sys
import json
import logging
import chess
import chess.pgn

# Riusiamo le funzioni gia' scritte e testate nel modulo analisi_partita.
from analisi_partita import _valuta, PERCORSO_STOCKFISH, PROFONDITA
import chess.engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine")

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)


def _analizza_una(partita, motore, profondita):
    """
    Analizza una singola partita gia' letta e restituisce la lista delle
    mosse con il centipawn loss (stessa logica di analisi_partita).
    """
    board = partita.board()
    eval_corrente = _valuta(board, motore, profondita)

    risultati = []
    for mossa in partita.mainline_moves():
        fen_prima = board.fen()
        san = board.san(mossa)
        uci = mossa.uci()
        turno_bianco = board.turn == chess.WHITE

        eval_prima = eval_corrente
        board.push(mossa)
        eval_dopo = _valuta(board, motore, profondita)

        loss = (eval_prima - eval_dopo) if turno_bianco else (eval_dopo - eval_prima)
        loss = max(0, loss)

        risultati.append({
            "fen": fen_prima,
            "move_uci": uci,
            "san": san,
            "eval_prima": eval_prima,
            "eval_dopo": eval_dopo,
            "centipawn_loss": loss,
        })
        eval_corrente = eval_dopo

    return risultati


def analizza_database(percorso_pgn, profondita=PROFONDITA, percorso=PERCORSO_STOCKFISH):
    """
    Analizza TUTTE le partite di un file PGN, salvando un file JSON per ognuna
    in data/analisi/. Restituisce il numero di partite analizzate in questa
    esecuzione (escluse quelle saltate perche' gia' fatte).
    """
    if not os.path.exists(percorso):
        logger.error("Stockfish non trovato in: %s", percorso)
        return None

    os.makedirs(CARTELLA_ANALISI, exist_ok=True)

    # Primo giro: contiamo quante partite ci sono nel file.
    with open(percorso_pgn, "r", encoding="utf-8") as f:
        totale = 0
        while chess.pgn.read_game(f) is not None:
            totale += 1
    logger.info("Il file contiene %d partite", totale)

    nome_base = os.path.splitext(os.path.basename(percorso_pgn))[0]
    motore = chess.engine.SimpleEngine.popen_uci(percorso)

    analizzate = 0
    saltate = 0
    with open(percorso_pgn, "r", encoding="utf-8") as f:
        indice = 0
        while True:
            partita = chess.pgn.read_game(f)
            if partita is None:
                break
            indice += 1

            nome_file = f"{nome_base}_{indice:04d}.json"
            percorso_out = os.path.join(CARTELLA_ANALISI, nome_file)

            # Se il file esiste gia', saltiamo (non rifacciamo lavoro fatto).
            if os.path.exists(percorso_out):
                logger.info("Partita %d/%d gia' analizzata, salto", indice, totale)
                saltate += 1
                continue

            logger.info("Analizzo partita %d/%d ...", indice, totale)
            mosse = _analizza_una(partita, motore, profondita)

            dato = {
                "bianco": partita.headers.get("White", "Sconosciuto"),
                "nero": partita.headers.get("Black", "Sconosciuto"),
                "risultato": partita.headers.get("Result", "?"),
                "mosse": mosse,
            }

            # Salvataggio immediato: questa partita e' ora al sicuro.
            with open(percorso_out, "w", encoding="utf-8") as out:
                json.dump(dato, out, indent=2, ensure_ascii=False)
            logger.info("Salvato: %s", percorso_out)
            analizzate += 1

    motore.quit()
    logger.info("Fatto. Analizzate ora: %d, gia' presenti: %d", analizzate, saltate)
    return analizzate


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python analisi_database.py <file.pgn>")
        sys.exit(1)

    n = analizza_database(sys.argv[1])
    if n is None:
        print("\nAnalisi non riuscita (Stockfish presente?).")
        sys.exit(1)

    print()
    print(f"Analisi completata. Partite analizzate in questa esecuzione: {n}")
    print(f"I risultati sono in: data/analisi/")
    print()
