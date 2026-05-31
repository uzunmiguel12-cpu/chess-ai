"""
Test del parser PGN.

Esegui (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
import json
from parser import (
    estrai_dati_partita,
    estrai_mosse,
    estrai_tutte_le_partite,
    salva_mosse_json,
)

CARTELLA_TEST = os.path.dirname(__file__)
PARTITA = os.path.join(CARTELLA_TEST, "partita_esempio.pgn")
MULTIPLE = os.path.join(CARTELLA_TEST, "partite_multiple.pgn")


# --- Metadati (prima partita) ---

def test_estrae_i_giocatori_giusti():
    dati = estrai_dati_partita(PARTITA)
    assert dati["bianco"] == "Donald Byrne"
    assert dati["nero"] == "Robert Fischer"


def test_estrae_il_risultato_giusto():
    dati = estrai_dati_partita(PARTITA)
    assert dati["risultato"] == "0-1"


def test_conta_le_mosse():
    dati = estrai_dati_partita(PARTITA)
    assert dati["numero_mosse"] > 0


# --- Estrazione mosse (prima partita) ---

def test_estrae_una_lista_di_mosse():
    mosse = estrai_mosse(PARTITA)
    assert isinstance(mosse, list)
    assert len(mosse) > 0


def test_ogni_mossa_rispetta_il_contratto():
    mosse = estrai_mosse(PARTITA)
    for m in mosse:
        assert "uci" in m
        assert "san" in m
        assert "fen_before" in m


def test_la_prima_mossa_e_corretta():
    mosse = estrai_mosse(PARTITA)
    assert mosse[0]["san"] == "Nf3"
    assert mosse[0]["uci"] == "g1f3"


def test_il_numero_di_mosse_coincide():
    dati = estrai_dati_partita(PARTITA)
    mosse = estrai_mosse(PARTITA)
    assert len(mosse) == dati["numero_mosse"]


# --- Salvataggio JSON ---

def test_salva_e_rilegge_json():
    mosse = estrai_mosse(PARTITA)
    percorso = salva_mosse_json(mosse, "test_temporaneo_mosse.json")
    assert os.path.exists(percorso)
    with open(percorso, "r", encoding="utf-8") as f:
        riletto = json.load(f)
    assert riletto == mosse
    os.remove(percorso)


# --- Lettura di piu' partite ---

def test_legge_tutte_le_partite():
    """Il file di prova contiene 3 partite: devono essere lette tutte e 3."""
    partite = estrai_tutte_le_partite(MULTIPLE)
    assert len(partite) == 3


def test_ogni_partita_ha_metadati_e_mosse():
    """Ogni partita letta deve avere i metadati e la lista delle mosse."""
    partite = estrai_tutte_le_partite(MULTIPLE)
    for p in partite:
        assert "bianco" in p
        assert "nero" in p
        assert "risultato" in p
        assert "mosse" in p
        assert len(p["mosse"]) > 0


def test_file_con_una_sola_partita():
    """estrai_tutte_le_partite deve funzionare anche con un file da 1 partita."""
    partite = estrai_tutte_le_partite(PARTITA)
    assert len(partite) == 1
    assert partite[0]["bianco"] == "Donald Byrne"
