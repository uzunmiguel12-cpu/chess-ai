"""
Modulo motore (Fase 2) - comunicazione con Stockfish.

Funzioni:
- saluta_stockfish: verifica che il motore risponda (stretta di mano UCI)
- analizza_posizione: data una FEN, restituisce valutazione e mossa migliore

Uso:  python motore.py
"""

import os
import logging
import chess
import chess.engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine")

PERCORSO_STOCKFISH = os.path.join(
    os.path.dirname(__file__), "bin", "stockfish.exe"
)

# Profondita' di analisi: quante mosse avanti guarda Stockfish.
# Piu' alta = piu' accurata ma piu' lenta. 15 e' un buon equilibrio.
PROFONDITA = 15


def saluta_stockfish(percorso=PERCORSO_STOCKFISH):
    """Avvia Stockfish, legge nome e autore, li restituisce, poi chiude."""
    if not os.path.exists(percorso):
        logger.error("Stockfish non trovato in: %s", percorso)
        return None
    logger.info("Avvio Stockfish: %s", percorso)
    motore = chess.engine.SimpleEngine.popen_uci(percorso)
    info = {
        "nome": motore.id.get("name", "sconosciuto"),
        "autore": motore.id.get("author", "sconosciuto"),
    }
    motore.quit()
    logger.info("Stockfish ha risposto correttamente")
    return info


def analizza_posizione(fen, profondita=PROFONDITA, percorso=PERCORSO_STOCKFISH):
    """
    Analizza una posizione (in formato FEN) con Stockfish.

    RESTITUISCE un dizionario con:
      - eval_cp: valutazione in centipawn, SEMPRE dal punto di vista del Bianco
                 (positivo = Bianco meglio, negativo = Nero meglio).
                 Se c'e' un matto forzato, usiamo un valore molto grande.
      - best_move_uci: la mossa migliore secondo Stockfish (UCI), o None.

    Restituisce None se Stockfish non e' disponibile.
    """
    if not os.path.exists(percorso):
        logger.error("Stockfish non trovato in: %s", percorso)
        return None

    board = chess.Board(fen)
    logger.info("Analizzo la posizione a profondita' %d", profondita)

    motore = chess.engine.SimpleEngine.popen_uci(percorso)
    risultato = motore.analyse(board, chess.engine.Limit(depth=profondita))
    motore.quit()

    # Stockfish da' il punteggio dal punto di vista di chi muove.
    # .white() lo converte SEMPRE al punto di vista del Bianco.
    punteggio_bianco = risultato["score"].white()

    if punteggio_bianco.is_mate():
        # Matto forzato: non c'e' un valore in centipawn.
        # Usiamo un numero molto grande col segno giusto.
        mosse_al_matto = punteggio_bianco.mate()
        eval_cp = 100000 if mosse_al_matto > 0 else -100000
    else:
        eval_cp = punteggio_bianco.score()

    # La mossa migliore e' il primo elemento della linea principale (pv).
    # Gestione robusta: in posizioni gia' terminate pv potrebbe mancare.
    pv = risultato.get("pv")
    best_move_uci = pv[0].uci() if pv else None

    logger.info("Analisi completata: eval=%s, best=%s", eval_cp, best_move_uci)
    return {"eval_cp": eval_cp, "best_move_uci": best_move_uci}


if __name__ == "__main__":
    info = saluta_stockfish()
    if info is None:
        print("\nImpossibile connettersi a Stockfish. Controlla engine/bin/stockfish.exe\n")
        raise SystemExit(1)

    print()
    print("Connessione a Stockfish riuscita!")
    print(f"  Motore: {info['nome']}")
    print()

    fen_iniziale = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    print("Analizzo la posizione iniziale degli scacchi...")
    a = analizza_posizione(fen_iniziale)
    if a:
        print(f"  Valutazione: {a['eval_cp']} centipawn (punto di vista del Bianco)")
        print(f"  Mossa migliore: {a['best_move_uci']}")
        print()
