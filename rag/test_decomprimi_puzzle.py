"""
Test del modulo decomprimi_puzzle (.zst -> testo).

Comprime dei dati finti con zstandard, li riscrive su file temporaneo, poi
verifica che la decompressione restituisca esattamente i byte originali.

Esegui (dalla cartella rag, con ambiente attivo):
    pytest
"""

import os
import tempfile
import pytest
import zstandard as zstd

from decomprimi_puzzle import decomprimi


@pytest.fixture
def cartella():
    c = tempfile.mkdtemp()
    yield c
    for nome in os.listdir(c):
        try:
            os.remove(os.path.join(c, nome))
        except OSError:
            pass
    try:
        os.rmdir(c)
    except OSError:
        pass


def test_round_trip(cartella):
    """I dati decompressi devono coincidere con gli originali."""
    originale = ("PuzzleId,FEN,Moves\n" + "abc,fen,e2e4\n" * 1000).encode("utf-8")
    zst_path = os.path.join(cartella, "dati.csv.zst")
    out_path = os.path.join(cartella, "dati.csv")

    with open(zst_path, "wb") as f:
        f.write(zstd.ZstdCompressor().compress(originale))

    scritti = decomprimi(zst_path, out_path)
    assert scritti == len(originale)

    with open(out_path, "rb") as f:
        assert f.read() == originale


def test_dati_vuoti(cartella):
    """Un input vuoto produce un output vuoto (0 byte scritti)."""
    zst_path = os.path.join(cartella, "vuoto.zst")
    out_path = os.path.join(cartella, "vuoto.csv")
    with open(zst_path, "wb") as f:
        f.write(zstd.ZstdCompressor().compress(b""))

    scritti = decomprimi(zst_path, out_path)
    assert scritti == 0
    assert os.path.getsize(out_path) == 0


def test_file_mancante(cartella):
    out_path = os.path.join(cartella, "out.csv")
    assert decomprimi(os.path.join(cartella, "non_esiste.zst"), out_path) is None
