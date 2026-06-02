"""
Modulo categorizzazione errori (Fase 3).

Data una mossa analizzata (centipawn loss + posizione FEN), attribuisce:
- gravita: scala in stile Chess.com basata sul centipawn loss
           (best / excellent / good / inaccuracy / mistake / blunder)
- fase:    apertura / mediogioco / finale  (dal materiale sulla scacchiera)
- tipo_tattico: predisposto ma None (lo aggiungeremo in un passo successivo)

NOTA sulle soglie: Chess.com non rende pubblico il suo algoritmo esatto, che
e' adattivo (tiene conto del livello del giocatore e delle probabilita' di
vittoria). Queste soglie sono un'approssimazione ragionevole e diffusa, con i
nomi delle categorie di Chess.com. Le categorie speciali (Brilliant, Great,
Book, Miss) non sono incluse perche' richiedono criteri proprietari o un
database di aperture.

Uso (esempio dimostrativo):  python categorizza.py
"""

import logging
import chess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

# Soglie di gravita' in centipawn, in stile Chess.com.
# Un centipawn loss entro la soglia indicata riceve quella etichetta.
SOGLIA_EXCELLENT = 20    # 1-20   -> excellent
SOGLIA_GOOD = 60         # 21-60  -> good
SOGLIA_INACCURACY = 100  # 61-100 -> inaccuracy
SOGLIA_MISTAKE = 200     # 101-200-> mistake
# oltre 200 -> blunder; esattamente 0 -> best


def classifica_gravita(centipawn_loss):
    """
    Traduce il centipawn loss in un'etichetta in stile Chess.com.
      0         -> best        (identica alla mossa del motore)
      1-20      -> excellent
      21-60     -> good
      61-100    -> inaccuracy
      101-200   -> mistake
      > 200     -> blunder
    """
    if centipawn_loss <= 0:
        return "best"
    if centipawn_loss <= SOGLIA_EXCELLENT:
        return "excellent"
    if centipawn_loss <= SOGLIA_GOOD:
        return "good"
    if centipawn_loss <= SOGLIA_INACCURACY:
        return "inaccuracy"
    if centipawn_loss <= SOGLIA_MISTAKE:
        return "mistake"
    return "blunder"


def classifica_fase(fen):
    """
    Determina la fase di gioco contando i pezzi diversi da pedoni e re.
      >= 10 pezzi -> apertura
      4-9 pezzi   -> mediogioco
      < 4 pezzi   -> finale
    """
    board = chess.Board(fen)
    pezzi_maggiori = 0
    for square in chess.SQUARES:
        pezzo = board.piece_at(square)
        if pezzo is None:
            continue
        if pezzo.piece_type not in (chess.PAWN, chess.KING):
            pezzi_maggiori += 1

    if pezzi_maggiori >= 10:
        return "apertura"
    if pezzi_maggiori >= 4:
        return "mediogioco"
    return "finale"


def categorizza_mossa(mossa_analizzata):
    """
    Data una mossa analizzata (dizionario con almeno 'centipawn_loss' e 'fen'),
    RESTITUISCE lo stesso dizionario arricchito con: gravita, fase, tipo_tattico.
    """
    risultato = dict(mossa_analizzata)
    risultato["gravita"] = classifica_gravita(mossa_analizzata["centipawn_loss"])
    risultato["fase"] = classifica_fase(mossa_analizzata["fen"])
    risultato["tipo_tattico"] = None
    return risultato


if __name__ == "__main__":
    esempi = [
        {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
         "centipawn_loss": 0, "san": "e4"},
        {"fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
         "centipawn_loss": 35, "san": "Bc4"},
        {"fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
         "centipawn_loss": 85, "san": "d3"},
        {"fen": "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1",
         "centipawn_loss": 150, "san": "Kd3"},
        {"fen": "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1",
         "centipawn_loss": 350, "san": "Ke4"},
    ]

    print()
    print("Esempi di categorizzazione (scala stile Chess.com):")
    print()
    for e in esempi:
        c = categorizza_mossa(e)
        print(f"  {c['san']:5} loss={c['centipawn_loss']:4}  "
              f"-> gravita={c['gravita']:11} fase={c['fase']}")
    print()
