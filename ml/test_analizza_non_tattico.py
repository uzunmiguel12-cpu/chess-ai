"""
Test del modulo analizza_non_tattico (scomposizione del 'non_tattico', T3).

Non richiede Stockfish: usa posizioni costruite ad arte e file di analisi finti
in cartella temporanea, puliti alla fine.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
import pytest

import analizza_non_tattico
from analizza_non_tattico import (
    e_errore_grave,
    fen_dopo_mossa,
    tipo_tattico_best_mossa,
    classifica_non_tattico,
    scomponi_non_tattici,
    analizza_cartella,
    _pct,
)

# --- Posizioni di comodo (FEN completa, " w - - 0 1") ---

# Caso forchetta: tocca al Bianco; la BEST move e' Kg1-h1, che lascia il Re/Donna
# bianchi forchettabili dal Cavallo nero in c7 (stessa posizione del test di
# tattica.py). rileva_tipo_tattico deve dare "forchetta".
FEN_FORK = "Q3R3/8/n6k/8/8/8/8/6K1 w - - 0 1"

# Caso cattura senza pattern noto: Torre bianca a1 cattura il pedone a2.
FEN_CATTURA = "7k/8/8/8/8/8/p7/R6K w - - 0 1"

# Caso posizionale: solo torre e re; la best move e' uno spostamento tranquillo.
FEN_QUIETO = "7k/8/8/8/8/8/8/R6K w - - 0 1"


def _m(fen, move_uci, best_move_uci, cpl=250):
    """Costruisce una mossa finta nel formato dei file di analisi."""
    return {
        "fen": fen,
        "move_uci": move_uci,
        "san": move_uci,
        "best_move_uci": best_move_uci,
        "eval_prima": 0,
        "eval_dopo": 0,
        "centipawn_loss": cpl,
    }


# --- Soglia errore grave (allineata al profilo: mistake/blunder) ---

def test_e_errore_grave_allineato_al_profilo():
    assert not e_errore_grave(0)     # best
    assert not e_errore_grave(50)    # good
    assert not e_errore_grave(100)   # inaccuracy (esattamente la soglia)
    assert e_errore_grave(101)       # mistake
    assert e_errore_grave(200)       # mistake (limite)
    assert e_errore_grave(250)       # blunder


# --- Ricostruzione FEN dopo la mossa ---

def test_fen_dopo_mossa_legale():
    assert fen_dopo_mossa(FEN_CATTURA, "a1a2") is not None


def test_fen_dopo_mossa_illegale_o_mancante():
    assert fen_dopo_mossa(FEN_QUIETO, "e2e4") is None   # casa vuota: illegale
    assert fen_dopo_mossa(FEN_QUIETO, None) is None
    assert fen_dopo_mossa(FEN_QUIETO, "") is None


# --- Riconoscimento del non_tattico sulla BEST move (come fa il sistema) ---

def test_best_forchetta_non_e_non_tattico():
    # La BEST move (g1h1) lascia il Bianco forchettabile dal Cavallo nero: e' un
    # pattern NOTO. Il sistema la etichetta gia' "forchetta", quindi NON e' un
    # non_tattico VERO: tipo_tattico_best_mossa lo riconosce e restituisce il tipo.
    assert tipo_tattico_best_mossa(_m(FEN_FORK, "g1f1", "g1h1")) == "forchetta"


def test_best_posizionale_e_non_tattico_vero():
    # La BEST move e' uno spostamento tranquillo: nessun pattern -> non_tattico VERO.
    assert tipo_tattico_best_mossa(_m(FEN_QUIETO, "a1b1", "a1d1")) is None


# --- Scomposizione del singolo non_tattico VERO (guardando la best) ---

def test_best_cattura_senza_pattern_noto():
    cat = classifica_non_tattico(_m(FEN_CATTURA, "h1g1", "a1a2"))
    assert cat == "probabile_tattica_non_coperta"


def test_best_posizionale_senza_cattura():
    cat = classifica_non_tattico(_m(FEN_QUIETO, "h1g1", "a1d1"))
    assert cat == "probabile_posizionale"


def test_best_illegale_o_mancante_e_incerto():
    assert classifica_non_tattico(_m(FEN_QUIETO, "h1g1", "e2e4")) == "incerto"
    assert classifica_non_tattico(_m(FEN_QUIETO, "h1g1", None)) == "incerto"


# --- Aggregazione: conteggi e percentuali ---

def test_scomponi_conta_e_ripartisce():
    # Tutte le mosse qui sono non_tattici VERI (best non e' un pattern noto): la
    # forchetta non compare perche' sarebbe stata esclusa a monte.
    mosse = [
        _m(FEN_CATTURA, "h1g1", "a1a2"),   # probabile_tattica_non_coperta
        _m(FEN_CATTURA, "h1g1", "a1a2"),   # probabile_tattica_non_coperta (di nuovo)
        _m(FEN_QUIETO, "h1g1", "a1d1"),    # probabile_posizionale
        _m(FEN_QUIETO, "h1g1", "e2e4"),    # incerto (best illegale)
    ]
    ris = scomponi_non_tattici(mosse)
    cat = ris["categorie"]
    assert cat["probabile_tattica_non_coperta"] == 2
    assert cat["probabile_posizionale"] == 1
    assert cat["incerto"] == 1
    assert sum(cat.values()) == 4
    # La vecchia categoria non esiste piu': per definizione 0.
    assert cat["tattica_riconoscibile_mancata"] == 0
    # Le percentuali: 1 su 4 = 25%.
    assert _pct(cat["incerto"], sum(cat.values())) == 25.0


def test_pct_robusta_su_zero():
    assert _pct(0, 0) == 0.0
    assert _pct(3, 0) == 0.0


# --- Integrazione su file di analisi finti ---

def _scrivi(cartella, nome, dato):
    with open(os.path.join(cartella, nome), "w", encoding="utf-8") as f:
        json.dump(dato, f, ensure_ascii=False)


def test_analizza_cartella_filtra_e_scompone():
    cartella = tempfile.mkdtemp()
    try:
        # File NON bullet, gioco io col Bianco (USERNAME default di estrai_errori).
        partita = {
            "bianco": "MigueL_uz",
            "nero": "Avversario",
            "risultato": "1-0",
            "mosse": [
                # Mia mossa, errore grave, non_tattico VERO: la best (a1d1) e'
                # uno spostamento tranquillo -> probabile_posizionale.
                _m(FEN_QUIETO, "a1b1", "a1d1", cpl=250),
                # Mossa del Nero (turno "b" nel FEN): NON e' mia, va ignorata.
                {"fen": "7k/8/8/8/8/8/8/3R3K b - - 0 1", "move_uci": "h8g8",
                 "san": "Kg8", "best_move_uci": "h8g8",
                 "eval_prima": 0, "eval_dopo": 0, "centipawn_loss": 300},
                # Mia mossa NON grave (cpl 30): non conta tra gli errori gravi.
                _m(FEN_QUIETO, "a1c1", "a1d1", cpl=30),
                # Mia mossa grave la cui BEST move e' un pattern noto (forchetta):
                # il sistema la etichetta gia', quindi conta tra gli errori gravi
                # ma NON tra i non_tattici VERI.
                _m(FEN_FORK, "g1f1", "g1h1", cpl=300),
            ],
        }
        _scrivi(cartella, "altro_0001.json", partita)

        # File bullet: deve essere escluso a monte.
        _scrivi(cartella, "bullet_0009.json", partita)

        # File dove NON gioco io: file saltato.
        _scrivi(cartella, "altro_0002.json", {
            "bianco": "Tizio", "nero": "Caio", "risultato": "1-0", "mosse": [],
        })

        rie = analizza_cartella(cartella)

        assert rie["partite_bullet_escluse"] == 1
        assert rie["file_saltati"] == 1
        # 2 errori gravi miei non-bullet (la posizionale + quella gia' tattica);
        # la mossa cpl 30 e quella del Nero non contano.
        assert rie["errori_gravi_non_bullet"] == 2
        # Di questi, solo 1 e' attualmente non_tattico.
        assert rie["non_tattici"] == 1
        assert rie["categorie"]["probabile_posizionale"] == 1
    finally:
        shutil.rmtree(cartella, ignore_errors=True)


def test_tipo_tattico_best_mossa_rileva_pezzo_in_presa():
    # La BEST move a2a1 lascia la torre bianca attaccata dalla torre nera in a7
    # (pattern noto): e' una tattica gia' etichettata, NON un non_tattico VERO.
    mossa = _m("7k/r7/8/8/8/8/R7/7K w - - 0 1", "a2a6", "a2a1", cpl=300)
    assert tipo_tattico_best_mossa(mossa) == "pezzo_in_presa"
