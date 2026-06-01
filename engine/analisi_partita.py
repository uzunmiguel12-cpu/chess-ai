"""
Modulo analisi partita (Fase 2) - calcolo del centipawn loss.

Mette insieme parser (mosse giocate) e motore (valutazioni Stockfish) per
calcolare, per ogni mossa, quanto il giocatore ha perso rispetto al meglio.

Strategia efficiente: ogni posizione viene analizzata UNA volta sola.
La valutazione "dopo la mossa N" coincide con quella "prima della mossa N+1".

Uso:  python analisi_partita.py partita_esempio.pgn
"""

import os
import sys
import logging
import chess
import chess.engine
import chess.pgn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine")

PERCORSO_STOCKFISH = os.path.join(
    os.path.dirname(__file__), "bin", "stockfish.exe"
)
PROFONDITA = 15


def _valuta(board, motore, profondita):
    """Valutazione della posizione in centipawn, dal punto di vista del Bianco."""
    risultato = motore.analyse(board, chess.engine.Limit(depth=profondita))
    punteggio = risultato["score"].white()
    if punteggio.is_mate():
        return 100000 if punteggio.mate() > 0 else -100000
    return punteggio.score()


def analizza_partita(percorso_pgn, profondita=PROFONDITA, percorso=PERCORSO_STOCKFISH):
    """
    Analizza tutte le mosse della prima partita di un file PGN e calcola il
    centipawn loss di ognuna.

    RESTITUISCE una lista di dizionari:
      - fen, move_uci, san
      - eval_prima, eval_dopo (centipawn, punto di vista Bianco)
      - centipawn_loss (quanto ha perso chi ha mosso; 0 = mossa ottima)

    Restituisce None se Stockfish non c'e' o il file non ha partite.
    """
    if not os.path.exists(percorso):
        logger.error("Stockfish non trovato in: %s", percorso)
        return None

    with open(percorso_pgn, "r", encoding="utf-8") as f:
        partita = chess.pgn.read_game(f)
    if partita is None:
        logger.error("Nessuna partita nel file")
        return None

    motore = chess.engine.SimpleEngine.popen_uci(percorso)
    board = partita.board()

    # Valutazione della posizione iniziale (prima della 1a mossa).
    eval_corrente = _valuta(board, motore, profondita)

    risultati = []
    for mossa in partita.mainline_moves():
        fen_prima = board.fen()
        san = board.san(mossa)
        uci = mossa.uci()
        turno_bianco = board.turn == chess.WHITE  # chi sta muovendo?

        eval_prima = eval_corrente  # gia' calcolata in precedenza (riuso!)

        board.push(mossa)            # applichiamo la mossa giocata
        eval_dopo = _valuta(board, motore, profondita)

        # Il loss e' il peggioramento dal punto di vista di chi ha mosso.
        # Bianco: perde se la valutazione (vista dal Bianco) scende.
        # Nero: perde se la valutazione (vista dal Bianco) sale.
        if turno_bianco:
            loss = eval_prima - eval_dopo
        else:
            loss = eval_dopo - eval_prima
        loss = max(0, loss)  # un "guadagno" da imprecisioni d'analisi -> 0

        risultati.append({
            "fen": fen_prima,
            "move_uci": uci,
            "san": san,
            "eval_prima": eval_prima,
            "eval_dopo": eval_dopo,
            "centipawn_loss": loss,
        })

        eval_corrente = eval_dopo  # riuso per la prossima iterazione

    motore.quit()
    logger.info("Analizzate %d mosse", len(risultati))
    return risultati


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python analisi_partita.py <file.pgn>")
        sys.exit(1)

    risultati = analizza_partita(sys.argv[1])
    if not risultati:
        print("Analisi non riuscita (Stockfish presente? file valido?).")
        sys.exit(1)

    print()
    print("Centipawn loss per mossa (numeri alti = errori):")
    print()
    for i, r in enumerate(risultati, start=1):
        marcatore = ""
        if r["centipawn_loss"] >= 300:
            marcatore = "  <-- ERRORE GRAVE"
        elif r["centipawn_loss"] >= 100:
            marcatore = "  <-- imprecisione"
        print(f"  {i:3}. {r['san']:7} loss={r['centipawn_loss']:5}{marcatore}")
    print()
