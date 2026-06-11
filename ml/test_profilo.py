"""
Test del modulo profilo (tasso per fase + dimensione tattica).

Non richiede Stockfish: dati finti in cartella temporanea, puliti alla fine.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
import pytest
from profilo import costruisci_profilo, _normalizza

POS_AP = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
POS_FIN = "8/8/4k3/8/8/4K3/4P3/8 w - - 0 1"


def _m(gravita, fase, tipo=None):
    return {"san": "x", "centipawn_loss": 0,
            "fen": POS_AP if fase == "apertura" else POS_FIN,
            "gravita": gravita, "fase": fase, "tipo_tattico": tipo}


@pytest.fixture
def cartella_tasso():
    """4 errori/20 mosse in apertura (20%), 3 errori/4 mosse in finale (75%)."""
    cartella = tempfile.mkdtemp()
    mosse = []

    def agg(grav, fase, tipo=None):
        mosse.append(_m(grav, fase, tipo))
        mosse.append(_m("best", fase))

    for i in range(20):
        agg("blunder" if i < 4 else "best", "apertura")
    for i in range(4):
        agg("blunder" if i < 3 else "best", "finale")

    p = {"bianco": "Miguel", "nero": "Avv", "risultato": "1-0", "mosse": mosse}
    with open(os.path.join(cartella, "p_0001.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)
    yield cartella
    shutil.rmtree(cartella)


@pytest.fixture
def cartella_tattica():
    """3 pezzi in presa, 2 forchette, 2 non tattici = 7 errori gravi."""
    cartella = tempfile.mkdtemp()
    mosse = []

    def agg(grav, fase, tipo):
        mosse.append(_m(grav, fase, tipo))
        mosse.append(_m("best", fase))

    agg("blunder", "mediogioco", "pezzo_in_presa")
    agg("blunder", "mediogioco", "pezzo_in_presa")
    agg("mistake", "finale", "pezzo_in_presa")
    agg("blunder", "apertura", "forchetta")
    agg("mistake", "mediogioco", "forchetta")
    agg("blunder", "mediogioco", None)
    agg("mistake", "apertura", None)

    p = {"bianco": "Miguel", "nero": "Avv", "risultato": "1-0", "mosse": mosse}
    with open(os.path.join(cartella, "p_0001.json"), "w", encoding="utf-8") as f:
        json.dump(p, f)
    yield cartella
    shutil.rmtree(cartella)


# --- Tasso per fase ---

def test_calcola_il_tasso(cartella_tasso):
    p = costruisci_profilo("Miguel", cartella_tasso)
    assert p["tasso_errore_per_fase"]["apertura"] == 20.0
    assert p["tasso_errore_per_fase"]["finale"] == 75.0


def test_debolezza_per_tasso(cartella_tasso):
    p = costruisci_profilo("Miguel", cartella_tasso)
    assert p["debolezza_principale"] == "finale"


# --- Dimensione tattica ---

def test_conteggio_tattico(cartella_tattica):
    p = costruisci_profilo("Miguel", cartella_tattica)
    assert p["conteggio_tattico"]["pezzo_in_presa"] == 3
    assert p["conteggio_tattico"]["forchetta"] == 2
    assert p["conteggio_tattico"]["non_tattico"] == 2


def test_percentuali_tattico(cartella_tattica):
    p = costruisci_profilo("Miguel", cartella_tattica)
    # 3 pezzi in presa su 7 errori = 42.9%
    assert p["percentuali_tattico"]["pezzo_in_presa"] == 42.9


def test_tattico_per_fase(cartella_tattica):
    p = costruisci_profilo("Miguel", cartella_tattica)
    # i pezzi in presa: 2 in mediogioco, 1 in finale
    assert p["tattico_per_fase"]["pezzo_in_presa"]["mediogioco"] == 2
    assert p["tattico_per_fase"]["pezzo_in_presa"]["finale"] == 1


def test_giocatore_inesistente(cartella_tattica):
    assert costruisci_profilo("Nessuno", cartella_tattica) is None


def test_inchiodatura_conteggiata():
    """L'inchiodatura deve avere la sua voce, non finire in non_tattico."""
    import tempfile, shutil
    cartella = tempfile.mkdtemp()
    try:
        mosse = [
            _m("blunder", "mediogioco", "inchiodatura"),
            _m("best", "mediogioco"),
        ]
        p = {"bianco": "Miguel", "nero": "Avv", "risultato": "1-0", "mosse": mosse}
        with open(os.path.join(cartella, "p_0001.json"), "w", encoding="utf-8") as f:
            json.dump(p, f)
        prof = costruisci_profilo("Miguel", cartella)
        assert prof["conteggio_tattico"].get("inchiodatura") == 1
        assert prof["conteggio_tattico"].get("non_tattico", 0) == 0
    finally:
        shutil.rmtree(cartella)


# --- Parametro solo_file (anti-diluizione, Tappa D) ---

@pytest.fixture
def cartella_due_file():
    """
    Due file partita con tassi DIVERSI, per testare solo_file:
      - vecchia.json: 1 errore su 10 mosse del giocatore (10%)
      - nuova.json:   5 errori su 10 mosse del giocatore (50%)
    """
    cartella = tempfile.mkdtemp()

    def partita(n_errori):
        mosse = []
        for i in range(10):
            mosse.append(_m("blunder" if i < n_errori else "best", "mediogioco",
                            "forchetta" if i < n_errori else None))
            mosse.append(_m("best", "mediogioco"))  # mossa dell'avversario
        return {"bianco": "Miguel", "nero": "Avv", "risultato": "1-0", "mosse": mosse}

    with open(os.path.join(cartella, "vecchia.json"), "w", encoding="utf-8") as f:
        json.dump(partita(1), f)
    with open(os.path.join(cartella, "nuova.json"), "w", encoding="utf-8") as f:
        json.dump(partita(5), f)
    yield cartella
    shutil.rmtree(cartella)


def test_solo_file_default_invariato(cartella_due_file):
    """Senza solo_file considera tutti i file: 6 errori su 20 mosse del giocatore."""
    p = costruisci_profilo("Miguel", cartella_due_file)
    assert p["partite_analizzate"] == 2
    assert p["mosse_totali"] == 20
    assert p["errori_gravi_totali"] == 6


def test_solo_file_filtra(cartella_due_file):
    """Con solo_file usa SOLO i file indicati: la sola 'nuova' ha tasso 50%."""
    p = costruisci_profilo("Miguel", cartella_due_file, solo_file=["nuova.json"])
    assert p["partite_analizzate"] == 1
    assert p["mosse_totali"] == 10
    assert p["errori_gravi_totali"] == 5
    assert p["tasso_errore_per_fase"]["mediogioco"] == 50.0


def test_solo_file_ignora_inesistenti(cartella_due_file):
    """Nomi non presenti in solo_file si ignorano senza crashare."""
    p = costruisci_profilo("Miguel", cartella_due_file,
                           solo_file=["nuova.json", "mai_esistita.json"])
    assert p["partite_analizzate"] == 1
