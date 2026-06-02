"""
Modulo categorizzazione errori (Fase 3, primo passo).

Data una mossa analizzata (centipawn loss + posizione FEN), attribuisce:
- gravita: ok / imprecisione / errore / blunder  (dalle soglie sul loss)
- fase:    apertura / mediogioco / finale         (dal materiale sulla scacchiera)
- tipo_tattico: predisposto ma None (lo aggiungeremo in un passo successivo)

Non richiede Stockfish ne' addestramento: sono regole dirette sui dati che
il motore (Fase 2) ha gia' prodotto.

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

# Soglie di gravita' in centipawn (standard, equilibrate).
SOGLIA_IMPRECISIONE = 50
SOGLIA_ERRORE = 100
SOGLIA_BLUNDER = 300


def classifica_gravita(centipawn_loss):
    """
    Traduce il centipawn loss in un'etichetta di gravita'.
      < 50   -> ok            (non e' un errore)
      50-99  -> imprecisione
      100-299-> errore
      >= 300 -> blunder       (errore grave)
    """
    if centipawn_loss < SOGLIA_IMPRECISIONE:
        return "ok"
    if centipawn_loss < SOGLIA_ERRORE:
        return "imprecisione"
    if centipawn_loss < SOGLIA_BLUNDER:
        return "errore"
    return "blunder"


def classifica_fase(fen):
    """
    Determina la fase di gioco contando il materiale (pezzi diversi dai pedoni
    e dai re) presente sulla scacchiera nella posizione data.

    Regola (semplice e sensata):
      - molti pezzi pesanti/leggeri ancora in gioco -> apertura/mediogioco
      - pochi pezzi rimasti -> finale

    Usiamo il numero di pezzi NON pedone e NON re come indicatore:
      >= 10 pezzi  -> apertura   (quasi tutto il materiale e' presente)
      4-9 pezzi    -> mediogioco
      < 4 pezzi    -> finale
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
    RESTITUISCE lo stesso dizionario arricchito con le categorie:
      - gravita
      - fase
      - tipo_tattico (None per ora; predisposto per il futuro)
    """
    risultato = dict(mossa_analizzata)  # copia, non modifichiamo l'originale
    risultato["gravita"] = classifica_gravita(mossa_analizzata["centipawn_loss"])
    risultato["fase"] = classifica_fase(mossa_analizzata["fen"])
    risultato["tipo_tattico"] = None  # da riempire in un passo successivo
    return risultato


if __name__ == "__main__":
    # Esempio dimostrativo con alcuni casi inventati.
    esempi = [
        {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
         "centipawn_loss": 10, "san": "e4"},
        {"fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
         "centipawn_loss": 75, "san": "Bc4"},
        {"fen": "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1",
         "centipawn_loss": 350, "san": "Kd3"},
    ]

    print()
    print("Esempi di categorizzazione:")
    print()
    for e in esempi:
        c = categorizza_mossa(e)
        print(f"  {c['san']:5} loss={c['centipawn_loss']:4}  "
              f"-> gravita={c['gravita']:12} fase={c['fase']}")
    print()
