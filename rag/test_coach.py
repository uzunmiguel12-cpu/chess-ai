"""Test del coach runtime (lookup nella cache). Offline e deterministico: usa una cache finta."""

from coach import chiave, spiega

CACHE_FINTA = {
    "e2e4": "Apre le linee per alfiere e donna e rivendica il centro: mossa di sviluppo classica.",
    "e2e4 e7e5": "Il Nero risponde a specchio, contendendo il centro con pari diritti.",
}


def test_chiave():
    assert chiave(["e2e4", "e7e5"]) == "e2e4 e7e5"
    assert chiave([]) == ""


def test_spiega_trova_e_manca():
    assert spiega(["e2e4"], CACHE_FINTA).startswith("Apre le linee")
    assert spiega(["e2e4", "e7e5"], CACHE_FINTA).startswith("Il Nero")
    # posizione non in cache -> None (niente testo inventato)
    assert spiega(["d2d4"], CACHE_FINTA) is None
