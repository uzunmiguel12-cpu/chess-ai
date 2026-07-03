"""
Test del motore di consiglio aperture. Offline e deterministico: inietta una funzione di
complessita' finta (numero di mosse) per non dipendere dal dataset ECO reale.

Esegui (dalla cartella rag):  pytest
"""

from consiglio_aperture import consiglia, _livello_max, _nota_tempo, APERTURE_CURATE


def _compl_finta(mosse):
    return len(mosse)  # complessita' deterministica per i test


def test_livello_da_elo():
    assert _livello_max(1000) == 1
    assert _livello_max(1400) == 2
    assert _livello_max(1800) == 3
    assert _livello_max(None) == 1


def test_filtra_per_livello():
    r = consiglia(1000, "migliorare", 30, f_complessita=_compl_finta)
    assert r["livello_max"] == 1
    assert r["consigli"] and all(c["livello"] == 1 for c in r["consigli"])
    r3 = consiglia(2000, "competere", 30, f_complessita=_compl_finta)
    assert any(c["livello"] == 3 for c in r3["consigli"])


def test_filtra_per_obiettivo():
    r = consiglia(2000, "competere", 30, f_complessita=_compl_finta)
    assert r["consigli"] and all("competere" in c["obiettivi"] for c in r["consigli"])


def test_filtra_per_colore():
    r = consiglia(1500, "migliorare", 30, colore="bianco", f_complessita=_compl_finta)
    assert r["consigli"] and all(c["colore"] == "bianco" for c in r["consigli"])


def test_ordina_per_livello_poi_complessita():
    r = consiglia(2000, None, 30, f_complessita=_compl_finta)
    coppie = [(c["livello"], c["complessita"]) for c in r["consigli"]]
    assert coppie == sorted(coppie)


def test_nota_tempo_qualitativa():
    assert "1-2 aperture" in _nota_tempo(10)
    assert "2-3 aperture" in _nota_tempo(30)
    assert "ampio" in _nota_tempo(90)


def test_consigli_hanno_i_campi():
    r = consiglia(1200, "migliorare", 30, f_complessita=_compl_finta)
    c = r["consigli"][0]
    for campo in ("nome", "colore", "livello", "mosse", "perche", "complessita", "obiettivi"):
        assert campo in c


def test_rosa_curata_non_vuota():
    assert len(APERTURE_CURATE) > 0
    assert all("mosse" in a and "livello" in a for a in APERTURE_CURATE)
