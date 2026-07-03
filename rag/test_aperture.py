"""
Test del modulo aperture (spina dati). NON usa la rete: il parser dell'Explorer e' puro e
lo testiamo su una risposta FINTA (canned). Cosi' gira anche in CI.

Esegui (dalla cartella rag):  pytest
"""

from aperture import (
    _parse_continuazioni, ramificazione, nome_apertura, _fascia_a_bucket, ECO_SAMPLE,
    continuazioni_eco, ramificazione_eco, mossa_da_libro_eco,
)

# Risposta finta dell'Explorer nella forma reale (moves ordinate per frequenza).
CANNED = {
    "white": 1000, "draws": 200, "black": 800,
    "moves": [
        {"uci": "g1f3", "san": "Nf3", "white": 600, "draws": 120, "black": 480, "averageRating": 1200},
        {"uci": "f1c4", "san": "Bc4", "white": 300, "draws": 50, "black": 250, "averageRating": 1180},
        {"uci": "b1c3", "san": "Nc3", "white": 100, "draws": 30, "black": 70, "averageRating": 1150},
    ],
    "opening": {"eco": "C40", "name": "King's Knight Opening"},
}


def test_parse_continuazioni_frequenza_e_quota():
    p = _parse_continuazioni(CANNED)
    cont = p["continuazioni"]
    # giocate = white+draws+black; totale = 2000; quote 0.6/0.3/0.1
    assert cont[0]["uci"] == "g1f3" and cont[0]["giocate"] == 1200
    assert cont[0]["quota"] == 0.6
    assert cont[1]["quota"] == 0.3
    assert cont[2]["quota"] == 0.1
    assert p["totale_partite"] == 2000
    assert p["apertura"] == {"eco": "C40", "nome": "King's Knight Opening"}


def test_punteggio_bianco():
    p = _parse_continuazioni(CANNED)
    # g1f3: 600 vittorie bianco su 1200 = 50%
    assert p["continuazioni"][0]["punteggio_bianco"] == 50.0


def test_ramificazione_e_proxy_di_complessita():
    # soglia 0.1 -> tutte e tre (0.6, 0.3, 0.1); soglia 0.2 -> due; soglia 0.5 -> una
    assert ramificazione(CANNED, soglia=0.1) == 3
    assert ramificazione(CANNED, soglia=0.2) == 2
    assert ramificazione(CANNED, soglia=0.5) == 1


def test_nome_apertura_prefisso_piu_lungo():
    # "e2e4 e7e5 g1f3 b8c6 f1c4" e' Italian; un prefisso piu' corto da' il nome piu' generico.
    # Passo ECO_SAMPLE esplicito: test deterministico anche se esiste data/aperture_eco.tsv.
    assert nome_apertura(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4"], ECO_SAMPLE) == ("C50", "Italian Game")
    assert nome_apertura(["e2e4", "e7e5", "g1f3"], ECO_SAMPLE) == ("C40", "King's Knight Opening")
    assert nome_apertura(["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"], ECO_SAMPLE) == ("C50", "Italian Game")
    assert nome_apertura(["g1f3"], ECO_SAMPLE) is None  # non nel sample


def test_fascia_a_bucket():
    assert _fascia_a_bucket(1100) == 1000
    assert _fascia_a_bucket(1400) == 1400
    assert _fascia_a_bucket(999) == 0
    assert _fascia_a_bucket(None) is None


def test_sample_eco_non_vuoto():
    assert isinstance(ECO_SAMPLE, dict) and len(ECO_SAMPLE) > 0


# Mini albero ECO per testare le continuazioni offline (deterministico).
ECO_FIXTURE = {
    "e2e4 e7e5": ("C20", "King's Pawn Game"),
    "e2e4 e7e5 g1f3": ("C40", "King's Knight Opening"),
    "e2e4 e7e5 g1f3 b8c6": ("C44", "Open Game"),
    "e2e4 e7e5 g1f3 b8c6 f1c4": ("C50", "Italian Game"),
    "e2e4 e7e5 g1f3 b8c6 f1b5": ("C60", "Ruy Lopez"),
    "e2e4 e7e5 f1c4": ("C23", "Bishop's Opening"),
}


def test_continuazioni_eco_e_mossa_da_libro():
    cont = continuazioni_eco(["e2e4", "e7e5"], ECO_FIXTURE)
    # g1f3 attraversa 4 linee, f1c4 solo 1 -> g1f3 in testa
    assert cont[0]["uci"] == "g1f3" and cont[0]["linee"] == 4
    assert cont[0]["nome"] == "King's Knight Opening"   # P+g1f3 e' una linea nominata
    assert cont[1]["uci"] == "f1c4" and cont[1]["linee"] == 1
    assert ramificazione_eco(["e2e4", "e7e5"], ECO_FIXTURE) == 2
    assert mossa_da_libro_eco(["e2e4", "e7e5"], ECO_FIXTURE) == "g1f3"


def test_continuazioni_eco_posizione_foglia():
    # una linea senza prosecuzioni note -> nessuna continuazione, niente mossa da libro
    assert continuazioni_eco(["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"], ECO_FIXTURE) == []
    assert mossa_da_libro_eco(["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"], ECO_FIXTURE) is None
