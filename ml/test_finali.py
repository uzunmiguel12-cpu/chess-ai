"""
Test del modulo ml/finali.py (logica riusabile sui finali).

Copre due cose:
  1) lo SPOSTAMENTO non regressivo di conta_pezzi/classifica_finale da
     analizza_finali.py a finali.py (stessi risultati su FEN noti, stesso oggetto);
  2) tassi_finali_per_tipo: conteggio dei denominatori, marcatura 'fragile' sotto
     MIN_MOSSE e conteggio degli errori posizionali puri (numeratore).

Non richiede Stockfish: FEN e mosse costruite ad arte.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import analizza_finali
from finali import (
    conta_pezzi, classifica_finale, tassi_finali_per_tipo, MIN_MOSSE,
)
import chess

# FEN noti (kings e3/e6, un pezzo bianco su a2 dove serve).
FEN_PEDONI = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"    # solo pedoni
FEN_TORRE = "8/8/4k3/8/8/4K3/R7/8 w - - 0 1"      # solo torre (+ re)
FEN_DONNA = "8/8/4k3/8/8/4K3/Q7/8 w - - 0 1"      # donna presente
FEN_MINORI = "8/8/4k3/8/8/4K3/B7/8 w - - 0 1"     # solo minori
FEN_MISTO = "8/8/4k3/8/8/4K3/RB6/8 w - - 0 1"     # torre + minore


# --- 1) Spostamento non regressivo ------------------------------------------

def test_stesse_funzioni_di_analizza_finali():
    """analizza_finali importa le funzioni da finali: sono lo STESSO oggetto."""
    assert analizza_finali.conta_pezzi is conta_pezzi
    assert analizza_finali.classifica_finale is classifica_finale
    assert analizza_finali.MIN_MOSSE == MIN_MOSSE


def test_classifica_finale_su_fen_noti():
    """La classificazione su FEN noti e' quella attesa (torre, donna, pedoni, ...)."""
    assert classifica_finale(FEN_PEDONI)[0] == "finale_pedoni"
    assert classifica_finale(FEN_TORRE)[0] == "finale_torre"
    assert classifica_finale(FEN_DONNA)[0] == "finale_donna"
    assert classifica_finale(FEN_MINORI)[0] == "finale_minori"
    assert classifica_finale(FEN_MISTO)[0] == "finale_misto"


def test_conta_pezzi_dettaglio():
    """conta_pezzi conta entrambi i colori esclusi i re."""
    d = conta_pezzi(chess.Board(FEN_MISTO))
    assert d == {"donne": 0, "torri": 1, "alfieri": 1, "cavalli": 0}


# --- 2) tassi_finali_per_tipo -----------------------------------------------

def _quiet(fen):
    """Mossa 'buona' (cl=0): entra nel denominatore ma non e' errore posizionale."""
    return {"fen": fen, "centipawn_loss": 0, "eval_prima": 50, "eval_dopo": 50,
            "best_move_uci": "e3d3", "san": "Kd3"}


def _err_torre():
    """Errore posizionale puro in finale di torre: best tranquilla (Ra2-a1)."""
    return {"fen": FEN_TORRE, "centipawn_loss": 250, "eval_prima": 100,
            "eval_dopo": 100, "best_move_uci": "a2a1", "san": "Ra1"}


def test_denominatore_per_tipo():
    """Le mosse in finale finiscono nel denominatore del tipo giusto."""
    r = tassi_finali_per_tipo([_quiet(FEN_TORRE), _quiet(FEN_TORRE),
                               _quiet(FEN_DONNA)])
    assert r["per_tipo"]["finale_torre"]["mosse"] == 2
    assert r["per_tipo"]["finale_donna"]["mosse"] == 1
    assert r["per_tipo"]["finale_pedoni"]["mosse"] == 0


def test_scarta_le_mosse_non_finale():
    """Le mosse fuori dal finale non entrano in nessun denominatore."""
    pos_apertura = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    r = tassi_finali_per_tipo([_quiet(pos_apertura)])
    assert sum(v["mosse"] for v in r["per_tipo"].values()) == 0


def test_conta_errore_posizionale():
    """Una best tranquilla con cl>=200 in posizione sana e' un errore posizionale."""
    r = tassi_finali_per_tipo([_err_torre()])
    assert r["per_tipo"]["finale_torre"]["errori"] == 1
    assert r["per_tipo"]["finale_torre"]["tasso"] == 100.0


def test_fragile_sotto_soglia_non_elegge_peggiore():
    """Con poche mosse il tipo e' 'fragile' e non viene eletto peggiore."""
    r = tassi_finali_per_tipo([_err_torre()])   # 1 sola mossa: sotto MIN_MOSSE
    assert r["per_tipo"]["finale_torre"]["fragile"] is True
    assert r["tipo_peggiore"] is None
    assert r["tasso_peggiore"] is None


def test_peggiore_fra_i_non_fragili():
    """Con abbastanza mosse il tipo non e' fragile ed e' eletto peggiore."""
    mosse = [_quiet(FEN_TORRE) for _ in range(MIN_MOSSE)] + [_err_torre()]
    r = tassi_finali_per_tipo(mosse)
    assert r["per_tipo"]["finale_torre"]["fragile"] is False
    assert r["tipo_peggiore"] == "finale_torre"
    assert r["tasso_peggiore"] == r["per_tipo"]["finale_torre"]["tasso"]


def test_mossa_senza_eval_non_crasha():
    """Una mossa senza eval_prima (cl=0) entra nel denominatore senza errori."""
    r = tassi_finali_per_tipo([{"fen": FEN_TORRE, "centipawn_loss": 0}])
    assert r["per_tipo"]["finale_torre"]["mosse"] == 1
    assert r["per_tipo"]["finale_torre"]["errori"] == 0
