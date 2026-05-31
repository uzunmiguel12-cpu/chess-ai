"""
Primo test del parser PGN.

Un test e' un programma che verifica automaticamente che il codice faccia
quello che deve. Si esegue con pytest, che cerca i file che iniziano con
"test_" e dentro le funzioni che iniziano con "test_", le lancia tutte e
dice se passano o falliscono.

Per eseguire (dalla cartella engine, con ambiente attivo):
    pytest
"""

import os
from parser import estrai_dati_partita

# Costruiamo il percorso della partita di esempio in modo che funzioni
# indipendentemente da dove si lancia il test: prendiamo la cartella in cui
# si trova QUESTO file di test e cerchiamo la partita li' accanto.
CARTELLA_TEST = os.path.dirname(__file__)
PARTITA = os.path.join(CARTELLA_TEST, "partita_esempio.pgn")


def test_estrae_i_giocatori_giusti():
    """Verifica che il parser legga correttamente i nomi dei due giocatori."""
    dati = estrai_dati_partita(PARTITA)
    assert dati["bianco"] == "Donald Byrne"
    assert dati["nero"] == "Robert Fischer"


def test_estrae_il_risultato_giusto():
    """Verifica che il parser legga correttamente il risultato della partita."""
    dati = estrai_dati_partita(PARTITA)
    assert dati["risultato"] == "0-1"


def test_conta_le_mosse():
    """
    Verifica che il parser conti delle mosse (un numero positivo).
    Non fissiamo il numero esatto: ci basta che la partita abbia mosse.
    """
    dati = estrai_dati_partita(PARTITA)
    assert dati["numero_mosse"] > 0
