"""
Test del modulo tattica (pezzo in presa + forchetta + inchiodatura).

Non richiede Stockfish. Gira ovunque.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import chess
from tattica import (
    _guadagno_cattura,
    trova_pezzo_in_presa,
    trova_forchetta,
    inchiodatura_creata,
    trova_infilata,
    rileva_tipo_tattico,
)


# --- Pezzo in presa ---

def test_torre_indifesa_e_in_presa():
    b = chess.Board("3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1")
    assert _guadagno_cattura(b, chess.D5, chess.BLACK) > 0


def test_trova_il_pezzo_in_presa():
    b = chess.Board("3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1")
    assert trova_pezzo_in_presa(b, chess.WHITE) == chess.D5


def test_nessun_pezzo_in_presa_iniziale():
    assert trova_pezzo_in_presa(chess.Board(), chess.WHITE) is None


# --- Forchetta ---

def test_trova_forchetta_cavallo():
    b = chess.Board("Q3R3/8/n6k/8/8/8/8/7K b - - 0 1")
    assert trova_forchetta(b, chess.WHITE) is True


def test_forchetta_non_valida_se_catturabile():
    b = chess.Board("Q3R3/8/n6k/B7/8/8/8/7K b - - 0 1")
    assert trova_forchetta(b, chess.WHITE) is False


# --- Inchiodatura ---

def test_inchiodatura_creata():
    """Ng1-e2 mette il cavallo davanti al re, inchiodato dalla torre e8."""
    prima = chess.Board("4r3/8/8/8/8/8/8/4K1N1 w - - 0 1")
    dopo = prima.copy()
    dopo.push(chess.Move.from_uci("g1e2"))
    assert inchiodatura_creata(prima, dopo, chess.WHITE) is True


def test_inchiodatura_preesistente_non_conta():
    """Se l'inchiodatura c'era gia' e muovo altro, non e' creata dalla mossa."""
    prima = chess.Board("4r3/8/8/8/8/P7/4N3/4K3 w - - 0 1")
    dopo = prima.copy()
    dopo.push(chess.Move.from_uci("a3a4"))
    assert inchiodatura_creata(prima, dopo, chess.WHITE) is False


# --- Infilata ---

def test_infilata_su_diagonale():
    """Alfiere a1 attacca donna d4, dietro torre g7: infilata."""
    b = chess.Board("8/6R1/8/8/3Q4/8/8/b3K2k w - - 0 1")
    assert trova_infilata(b, chess.WHITE) is True


def test_inchiodatura_non_e_infilata():
    """Cavallo (minore) davanti al re: e' inchiodatura, non infilata."""
    b = chess.Board("4r3/8/8/8/8/8/4N3/4K3 w - - 0 1")
    assert trova_infilata(b, chess.WHITE) is False


def test_nessuna_infilata_iniziale():
    assert trova_infilata(chess.Board(), chess.WHITE) is False


# --- Etichette finali (firma con fen_prima, fen_dopo) ---

def test_etichetta_pezzo_in_presa():
    fp = "8/8/8/8/8/8/8/4K3 w - - 0 1"
    fd = "3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1"
    assert rileva_tipo_tattico(fp, fd, chess.WHITE) == "pezzo_in_presa"


def test_etichetta_forchetta():
    fp = "8/8/8/8/8/8/8/4K3 w - - 0 1"
    fd = "Q3R3/8/n6k/8/8/8/8/7K b - - 0 1"
    assert rileva_tipo_tattico(fp, fd, chess.WHITE) == "forchetta"


def test_etichetta_inchiodatura():
    fp = "4r3/8/8/8/8/8/8/4K1N1 w - - 0 1"
    fd = "4r3/8/8/8/8/8/4N3/4K3 b - - 0 1"
    assert rileva_tipo_tattico(fp, fd, chess.WHITE) == "inchiodatura"


def test_etichetta_infilata():
    # Infilata sul re: torre a1 da' scacco, dietro la donna g1 (stessa traversa).
    # Il re non conta come "pezzo in presa", quindi l'etichetta e' infilata pulita.
    fp = "8/8/8/8/8/8/8/4K3 w - - 0 1"
    fd = "4k3/8/8/8/8/8/8/r3K1Q1 w - - 0 1"
    assert rileva_tipo_tattico(fp, fd, chess.WHITE) == "infilata"


def test_etichetta_niente():
    fd = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    assert rileva_tipo_tattico(chess.STARTING_FEN, fd, chess.WHITE) is None
