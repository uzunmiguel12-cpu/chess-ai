"""
S3 — Codifica di (posizione, mossa) in tensori 8x8 per la rete neurale.

Design (deciso con Miguel):
  - 24 piani 8x8: 12 per la posizione PRIMA della mossa + 12 per quella DOPO
    (ordine: pezzi di CHI MUOVE P,N,B,R,Q,K poi avversario p,n,b,r,q,k);
  - PROSPETTIVA DI CHI MUOVE: se muove il Nero, entrambe le scacchiere vengono
    specchiate (board.mirror(): ribalta e scambia i colori), cosi' la rete vede
    sempre "io gioco verso l'alto" — dimezza cio' che deve imparare;
  - eval_prima (POV di chi muove) passa come scalare normalizzato a parte.

Solo numpy: PyTorch serve solo in modello.py/allena_rete.py (cosi' la codifica
e' testabile ovunque).
"""

import numpy as np
import chess

N_PIANI = 24
ORDINE_PEZZI = (chess.PAWN, chess.KNIGHT, chess.BISHOP,
                chess.ROOK, chess.QUEEN, chess.KING)
CLIP_EVAL = 1000.0


def _piani_scacchiera(board):
    """12 piani (8,8): prima i pezzi del Bianco (che dopo il mirror e' sempre
    chi muove), poi quelli del Nero. piano[traversa][colonna]."""
    piani = np.zeros((12, 8, 8), dtype=np.float32)
    for i, pt in enumerate(ORDINE_PEZZI):
        for sq in board.pieces(pt, chess.WHITE):
            piani[i, chess.square_rank(sq), chess.square_file(sq)] = 1.0
        for sq in board.pieces(pt, chess.BLACK):
            piani[i + 6, chess.square_rank(sq), chess.square_file(sq)] = 1.0
    return piani


def codifica(fen, mossa_uci):
    """(24,8,8) float32 dalla prospettiva di chi muove. Solleva ValueError se
    la mossa e' illegale nella posizione."""
    prima = chess.Board(fen)
    mv = chess.Move.from_uci(mossa_uci)
    if mv not in prima.legal_moves:
        raise ValueError(f"mossa illegale: {mossa_uci} in {fen}")
    dopo = prima.copy()
    dopo.push(mv)
    if prima.turn == chess.BLACK:          # prospettiva di chi muove
        prima = prima.mirror()
        dopo = dopo.mirror()
    return np.concatenate([_piani_scacchiera(prima), _piani_scacchiera(dopo)])


def normalizza_eval(eval_prima_cp):
    """Eval (POV di chi muove) in [-1, 1]."""
    return float(np.clip(eval_prima_cp, -CLIP_EVAL, CLIP_EVAL) / CLIP_EVAL)


if __name__ == "__main__":
    t = codifica(chess.Board().fen(), "e2e4")
    print("shape:", t.shape, "| pezzi prima:", int(t[:12].sum()),
          "| pezzi dopo:", int(t[12:].sum()))
