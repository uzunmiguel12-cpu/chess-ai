"""
Test del modulo coda_errori (trasformazione dei puzzle validati nel formato che
la coda del backend consuma).

NON usa Stockfish: il modulo e' di sola lettura e tutte le funzioni sono pure o
leggono file JSON, quindi i test costruiscono dati finti (un file di analisi e
puzzle validati) e verificano il formato di output, il recupero del setup, la
coerenza setup+fen, la stima del rating e l'id.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json

import chess

import coda_errori
from coda_errori import (
    stima_rating,
    costruisci_moves,
    costruisci_id,
    recupera_setup,
    verifica_coerenza,
    trasforma_puzzle,
    istogramma_rating,
    costruisci_coda,
    carica_mosse_origine,
    CENTRO_ELO,
    RATING_MIN,
    RATING_MAX,
    THEMES,
    MOTIVO_ALLENAMENTO,
    FASE_ALLENAMENTO,
)

# Posizione iniziale: come setup giochiamo 1.e4, ottenendo il fen dopo e2e4.
FEN_INIZIALE = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_DOPO_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _mosse_finte():
    """
    Lista di mosse finta in stile file di analisi: l'indice 0 e' la mossa di
    setup (1.e4) col suo fen PRIMA della mossa; l'indice 1 e' il "mio errore",
    il cui fen e' la posizione DOPO il setup.
    """
    return [
        {"move_uci": "e2e4", "fen": FEN_INIZIALE},
        {"move_uci": "g8f6", "fen": FEN_DOPO_E4},
    ]


def _puzzle_finto(**override):
    """Puzzle validato finto (formato di data/puzzle_errori.json)."""
    puzzle = {
        "fen": FEN_DOPO_E4,
        "soluzione_uci": "e7e5",
        "gap_centipawn": 300,
        "era_matto": False,
        "fonte_file": "mie_partite_0001.json",
        "indice_mossa": 1,
    }
    puzzle.update(override)
    return puzzle


# --- moves col setup davanti ---------------------------------------------

def test_costruisci_moves_mette_il_setup_davanti():
    # La PRIMA mossa e' il setup, la SECONDA e' la soluzione del giocatore.
    assert costruisci_moves("e2e4", "e7e5") == "e2e4 e7e5"


def test_moves_split_ricostruisce_setup_e_soluzione():
    # Come fa il frontend: split(' ') -> [setup, soluzione].
    setup, soluzione = costruisci_moves("d8e7", "e5g7").split(" ")
    assert setup == "d8e7"
    assert soluzione == "e5g7"


# --- recupero del setup dal file di analisi ------------------------------

def test_recupera_setup_prende_la_mossa_precedente():
    mosse = _mosse_finte()
    # indice_mossa=1 -> setup all'indice 0.
    setup_uci, fen_setup = recupera_setup(mosse, 1)
    assert setup_uci == "e2e4"
    assert fen_setup == FEN_INIZIALE


def test_recupera_setup_alla_prima_mossa_restituisce_none():
    # indice_mossa=0 -> non c'e' nulla prima da usare come setup.
    assert recupera_setup(_mosse_finte(), 0) is None


def test_recupera_setup_indice_fuori_range_restituisce_none():
    assert recupera_setup(_mosse_finte(), 99) is None


# --- coerenza setup + fen ------------------------------------------------

def test_verifica_coerenza_caso_ok():
    # e2e4 applicata alla posizione iniziale da' esattamente FEN_DOPO_E4.
    assert verifica_coerenza(FEN_INIZIALE, "e2e4", FEN_DOPO_E4) is True


def test_verifica_coerenza_caso_incoerente():
    # d2d4 NON porta a FEN_DOPO_E4: incoerente, da scartare.
    assert verifica_coerenza(FEN_INIZIALE, "d2d4", FEN_DOPO_E4) is False


def test_verifica_coerenza_mossa_illegale_e_falsa():
    # e2e5 non e' legale dalla posizione iniziale.
    assert verifica_coerenza(FEN_INIZIALE, "e2e5", FEN_DOPO_E4) is False


# --- stima del rating ----------------------------------------------------

def test_rating_gap_200_e_il_massimo():
    # gap piccolo (200) => piu' difficile => rating ALTO = CENTRO_ELO + 150.
    assert stima_rating(200, False) == 1300
    assert stima_rating(200, False) == CENTRO_ELO + 150


def test_rating_gap_600_e_il_minimo():
    # gap grande (600) => piu' facile => rating BASSO = CENTRO_ELO - 150.
    assert stima_rating(600, False) == 1000
    assert stima_rating(600, False) == CENTRO_ELO - 150


def test_rating_gap_intermedio_interpolato():
    # gap 400 e' a meta' strada: scostamento 0 => CENTRO_ELO.
    assert stima_rating(400, False) == CENTRO_ELO


def test_rating_matto_e_basso():
    # Matto riconoscibile => rating basso a prescindere dal gap.
    assert stima_rating(100523, True) == 1000
    assert stima_rating(250, True) == RATING_MIN


def test_rating_clampato_in_fascia():
    # gap enorme => sotto il minimo, ma clampato a RATING_MIN.
    assert stima_rating(100000, False) == RATING_MIN
    # gap minuscolo => sopra il massimo, ma clampato a RATING_MAX.
    assert stima_rating(0, False) == RATING_MAX


def test_rating_sempre_intero():
    # gap dispari -> interpolazione non intera -> deve essere arrotondata.
    r = stima_rating(333, False)
    assert isinstance(r, int)
    assert RATING_MIN <= r <= RATING_MAX


# --- formato id ----------------------------------------------------------

def test_costruisci_id():
    assert costruisci_id("mie_partite_0001.json", 16) == "err_mie_partite_0001_16"


# --- trasformazione completa: tutti i campi target -----------------------

def test_trasforma_puzzle_ok_ha_tutti_i_campi():
    puzzle_coda, motivo = trasforma_puzzle(_puzzle_finto(), _mosse_finte())
    assert motivo is None
    # Tutti e soli i campi del formato coda del backend.
    assert set(puzzle_coda) == {
        "id", "fen", "moves", "rating",
        "themes", "motivo_allenamento", "fase_allenamento",
    }
    assert puzzle_coda["id"] == "err_mie_partite_0001_1"
    # fen = posizione PRIMA del setup (cosi' il frontend giocando il setup arriva
    # alla posizione dell'errore).
    assert puzzle_coda["fen"] == FEN_INIZIALE
    assert puzzle_coda["moves"] == "e2e4 e7e5"
    assert puzzle_coda["rating"] == stima_rating(300, False)
    assert puzzle_coda["themes"] == THEMES
    assert puzzle_coda["motivo_allenamento"] == MOTIVO_ALLENAMENTO
    assert puzzle_coda["fase_allenamento"] is FASE_ALLENAMENTO


def test_trasforma_puzzle_incoerente_scartato():
    # Il fen del puzzle non e' quello che si ottiene applicando il setup.
    puzzle = _puzzle_finto(fen="rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1")
    puzzle_coda, motivo = trasforma_puzzle(puzzle, _mosse_finte())
    assert puzzle_coda is None
    assert motivo == "incoerente"


def test_trasforma_puzzle_setup_mancante_scartato():
    # Errore alla prima mossa: nessun setup davanti.
    puzzle_coda, motivo = trasforma_puzzle(_puzzle_finto(indice_mossa=0), _mosse_finte())
    assert puzzle_coda is None
    assert motivo == "setup_mancante"


# --- istogramma del rating -----------------------------------------------

def test_istogramma_rating_per_fasce_di_50():
    # 1000, 1010 -> fascia 1000; 1300 -> fascia 1300.
    fasce = istogramma_rating([1000, 1010, 1300])
    assert (1000, 1050, 2) in fasce
    assert (1300, 1350, 1) in fasce
    # Ordinate per inizio fascia.
    assert fasce == sorted(fasce)


def test_istogramma_rating_vuoto():
    assert istogramma_rating([]) == []


# --- costruisci_coda end-to-end con file finti ---------------------------

def _scrivi_analisi(cartella, nome, mosse):
    """Scrive un file di analisi finto in cartella/nome."""
    percorso = os.path.join(cartella, nome)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump({"bianco": "x", "nero": "y", "mosse": mosse}, f)


def test_costruisci_coda_tiene_buoni_e_scarta_incoerenti(tmp_path):
    cartella = tmp_path / "analisi"
    cartella.mkdir()
    _scrivi_analisi(str(cartella), "mie_partite_0001.json", _mosse_finte())

    buono = _puzzle_finto()
    incoerente = _puzzle_finto(fen=FEN_INIZIALE)  # setup e2e4 non porta a FEN_INIZIALE

    coda, scarti = costruisci_coda([buono, incoerente], cartella=str(cartella))

    assert len(coda) == 1
    assert coda[0]["id"] == "err_mie_partite_0001_1"
    assert scarti["incoerente"] == 1
    assert scarti["setup_mancante"] == 0
    assert scarti["file_mancante"] == 0


def test_costruisci_coda_file_di_analisi_mancante(tmp_path):
    cartella = tmp_path / "analisi"
    cartella.mkdir()
    # Nessun file scritto: il puzzle punta a un file inesistente.
    coda, scarti = costruisci_coda([_puzzle_finto()], cartella=str(cartella))
    assert coda == []
    assert scarti["file_mancante"] == 1


def test_carica_mosse_origine_usa_la_cache(tmp_path):
    cartella = tmp_path / "analisi"
    cartella.mkdir()
    _scrivi_analisi(str(cartella), "mie_partite_0001.json", _mosse_finte())

    cache = {}
    primo = carica_mosse_origine("mie_partite_0001.json", cache, cartella=str(cartella))
    assert "mie_partite_0001.json" in cache
    # Seconda chiamata: stesso oggetto dalla cache (non rilegge il file).
    secondo = carica_mosse_origine("mie_partite_0001.json", cache, cartella=str(cartella))
    assert primo is secondo

    # File inesistente: None memorizzato in cache.
    assert carica_mosse_origine("manca.json", cache, cartella=str(cartella)) is None
    assert cache["manca.json"] is None
