"""
Test del backend (api/server.py).

Non avvia un vero server HTTP (servirebbe httpx): chiama direttamente le funzioni
degli endpoint, che sono normali funzioni Python. Lo stato globale _sessione viene
azzerato prima di ogni test, e i percorsi su disco (stato salvato, database) sono
reindirizzati su file temporanei con monkeypatch.

Esegui (dalla cartella api, con ambiente attivo):
    pytest
"""

import os
import json
import sqlite3
import tempfile
import pytest

import server
from server import (
    Esito, registra_esito, statistiche, statistiche_temi, lista_temi,
    scegli_tema, prossimo_puzzle,
    _salva_stato, _carica_stato, _valuta_adattivita,
)


def _stato_pulito():
    """Riporta _sessione ai valori di default, come a backend appena avviato."""
    server._sessione.update({
        "piano": None, "coda": [], "serviti": 0,
        "tentati": 0, "risolti_primo": 0, "risolti_secondo": 0, "falliti": 0,
        "elo_min": server.ELO_MIN, "elo_max": server.ELO_MAX,
        "blocco_primo": 0, "blocco_conteggio": 0,
        "storico_fasce": [], "visti": set(), "tema_libero": None,
        "esaurito": False, "statistiche_temi": {},
    })


@pytest.fixture
def ambiente(monkeypatch):
    """Stato pulito + percorso file-stato temporaneo, niente accessi al vero DB."""
    cartella = tempfile.mkdtemp()
    stato_path = os.path.join(cartella, "stato.json")
    monkeypatch.setattr(server, "PERCORSO_STATO", stato_path)
    _stato_pulito()
    yield {"stato_path": stato_path}
    _stato_pulito()
    try:
        if os.path.exists(stato_path):
            os.remove(stato_path)
        os.rmdir(cartella)
    except OSError:
        pass


# --- Persistenza ---------------------------------------------------------

def test_salva_e_carica_round_trip(ambiente):
    server._sessione["elo_min"] = 1150
    server._sessione["elo_max"] = 1350
    server._sessione["tentati"] = 7
    server._sessione["risolti_primo"] = 5
    server._sessione["visti"] = {"a", "b", "c"}
    server._sessione["storico_fasce"] = [{"azione": "alzata"}]
    _salva_stato()

    # azzero e ricarico
    _stato_pulito()
    assert _carica_stato() is True
    assert server._sessione["elo_min"] == 1150
    assert server._sessione["elo_max"] == 1350
    assert server._sessione["tentati"] == 7
    assert server._sessione["risolti_primo"] == 5
    assert server._sessione["visti"] == {"a", "b", "c"}  # ricostruito da lista
    assert server._sessione["storico_fasce"] == [{"azione": "alzata"}]


def test_salva_scrive_file_valido(ambiente):
    server._sessione["visti"] = {"x", "y"}
    _salva_stato()
    with open(ambiente["stato_path"], "r", encoding="utf-8") as f:
        dati = json.load(f)
    assert isinstance(dati["visti"], list)  # set serializzato come lista
    assert set(dati["visti"]) == {"x", "y"}


def test_carica_senza_file(ambiente):
    """Senza file salvato, _carica_stato segnala False (parte pulito)."""
    assert not os.path.exists(ambiente["stato_path"])
    assert _carica_stato() is False


def test_carica_file_corrotto(ambiente):
    with open(ambiente["stato_path"], "w", encoding="utf-8") as f:
        f.write("{ questo non e' json valido")
    assert _carica_stato() is False


# --- Statistiche ed esiti ------------------------------------------------

def test_registra_esito_aggiorna_statistiche(ambiente):
    # evito che statistiche()/registra_esito provino a costruire un piano vero
    server._sessione["piano"] = {"blocchi": []}

    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    registra_esito(Esito(puzzle_id="p2", risultato="secondo"))
    registra_esito(Esito(puzzle_id="p3", risultato="fallito"))

    s = statistiche()
    assert s["tentati"] == 3
    assert s["risolti_primo"] == 1
    assert s["risolti_secondo"] == 1
    assert s["falliti"] == 1
    assert s["percentuale_primo"] == round(100 / 3, 1)


def test_esito_persiste_su_file(ambiente):
    server._sessione["piano"] = {"blocchi": []}
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    # dopo ogni esito lo stato viene salvato
    assert os.path.exists(ambiente["stato_path"])
    with open(ambiente["stato_path"], "r", encoding="utf-8") as f:
        dati = json.load(f)
    assert dati["tentati"] == 1
    assert dati["risolti_primo"] == 1


# --- Difficolta' adattiva ------------------------------------------------

def test_adattivita_blocco_incompleto(ambiente):
    """Sotto BLOCCO_ADATTIVO puzzle non si valuta nulla."""
    server._sessione["blocco_conteggio"] = server.BLOCCO_ADATTIVO - 1
    server._sessione["blocco_primo"] = server.BLOCCO_ADATTIVO - 1
    assert _valuta_adattivita() is None


def test_adattivita_alza_fascia(ambiente, monkeypatch):
    # niente ripesca dal DB: la sostituisco con un no-op
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda: None)
    server._sessione["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    server._sessione["blocco_primo"] = server.BLOCCO_ADATTIVO  # 100% al primo
    em0, ex0 = server._sessione["elo_min"], server._sessione["elo_max"]

    assert _valuta_adattivita() == "alzata"
    assert server._sessione["elo_min"] == em0 + server.PASSO_ELO
    assert server._sessione["elo_max"] == ex0 + server.PASSO_ELO
    assert server._sessione["blocco_conteggio"] == 0  # blocco azzerato
    assert len(server._sessione["storico_fasce"]) == 1


def test_adattivita_abbassa_fascia(ambiente, monkeypatch):
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda: None)
    server._sessione["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    server._sessione["blocco_primo"] = 0  # 0% al primo
    em0, ex0 = server._sessione["elo_min"], server._sessione["elo_max"]

    assert _valuta_adattivita() == "abbassata"
    assert server._sessione["elo_min"] == em0 - server.PASSO_ELO
    assert server._sessione["elo_max"] == ex0 - server.PASSO_ELO


def test_adattivita_fascia_invariata(ambiente, monkeypatch):
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda: None)
    server._sessione["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    # 80%: tra SOGLIA_ABBASSA (70) e SOGLIA_ALZA (90) -> invariata
    server._sessione["blocco_primo"] = 8
    em0, ex0 = server._sessione["elo_min"], server._sessione["elo_max"]

    assert _valuta_adattivita() is None
    assert (server._sessione["elo_min"], server._sessione["elo_max"]) == (em0, ex0)
    assert server._sessione["storico_fasce"] == []


# --- Temi ----------------------------------------------------------------

def test_lista_temi(ambiente):
    risposta = lista_temi()
    assert set(risposta["temi"]) == set(server.TEMI_DISPONIBILI.keys())


def test_temi_raggruppati_per_categoria(ambiente):
    """I 24 temi sono divisi in 3 categorie e ogni tema appartiene a una sola."""
    risposta = lista_temi()
    assert set(risposta["categorie"].keys()) == {"Tattiche", "Matti", "Finali"}
    assert len(risposta["temi"]) == 24
    # l'unione delle categorie coincide con la lista piatta, senza doppioni
    tutti = [t for temi in risposta["categorie"].values() for t in temi]
    assert len(tutti) == 24
    assert set(tutti) == set(risposta["temi"])


def test_scegli_tema_sconosciuto(ambiente):
    risposta = scegli_tema("tema_che_non_esiste")
    assert risposta.status_code == 404


# --- Esaurimento puzzle --------------------------------------------------

def _crea_db_puzzle(percorso, puzzle):
    """Mini-DB puzzle. `puzzle` = lista di (id, rating, themes)."""
    conn = sqlite3.connect(percorso)
    c = conn.cursor()
    c.execute("CREATE TABLE puzzle (id TEXT PRIMARY KEY, fen TEXT, moves TEXT, "
              "rating INTEGER, themes TEXT)")
    c.executemany("INSERT INTO puzzle VALUES (?,?,?,?,?)",
                  [(pid, "f", "m", rating, themes) for pid, rating, themes in puzzle])
    conn.commit()
    conn.close()


def test_pesca_allargando_si_ferma_quando_basta(ambiente):
    """Appena trova >= PUZZLE_MINIMI puzzle nuovi smette di allargare."""
    server._sessione["elo_min"] = 1050
    server._sessione["elo_max"] = 1250
    chiamate = []

    def pesca(emax):
        chiamate.append(emax)
        # abbastanza solo dal primo allargamento (1350) in poi
        return list(range(server.PUZZLE_MINIMI)) if emax >= 1350 else list(range(2))

    righe, esaurito = server._pesca_allargando(pesca)
    assert esaurito is False
    assert len(righe) == server.PUZZLE_MINIMI
    assert chiamate == [1250, 1350]  # si ferma appena basta
    # la fascia di base non e' stata toccata
    assert (server._sessione["elo_min"], server._sessione["elo_max"]) == (1050, 1250)


def test_pesca_allargando_rispetta_max_400(ambiente):
    """Senza puzzle, allarga di 100 alla volta fino a +400 e poi si arrende."""
    server._sessione["elo_min"] = 1050
    server._sessione["elo_max"] = 1250
    tetti = []

    def pesca(emax):
        tetti.append(emax)
        return []  # mai abbastanza

    righe, esaurito = server._pesca_allargando(pesca)
    assert esaurito is True
    assert tetti == [1250, 1350, 1450, 1550, 1650]  # base + fino a 400
    assert (server._sessione["elo_min"], server._sessione["elo_max"]) == (1050, 1250)


def test_pesca_allargando_cappa_a_elo_assoluto(ambiente):
    """L'allargamento non supera mai ELO_MAX_ASSOLUTO (2800)."""
    server._sessione["elo_min"] = 2500
    server._sessione["elo_max"] = 2700
    tetti = []

    def pesca(emax):
        tetti.append(emax)
        return []

    server._pesca_allargando(pesca)
    assert tetti == [2700, server.ELO_MAX_ASSOLUTO]  # 2700 -> 2800, non oltre


def test_tema_allarga_tetto_temporaneo_senza_toccare_base(ambiente, monkeypatch, tmp_path):
    """Pochi puzzle nuovi in fascia base ma abbastanza poco sopra: ripesca senza
    modificare la fascia di base di sessione."""
    db = str(tmp_path / "puzzle.db")
    puzzle = [(f"base{i}", 1100, "middlegame fork") for i in range(3)]   # in 1050-1250
    puzzle += [(f"alto{i}", 1280, "middlegame fork") for i in range(8)]  # serve +100
    _crea_db_puzzle(db, puzzle)
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    server._sessione["tema_libero"] = "forchetta"
    esaurito = server._riempi_coda_tema("fork")

    assert esaurito is False
    assert server._sessione["esaurito"] is False
    # fascia di base intatta: l'adattivita' resta padrona
    assert server._sessione["elo_min"] == server.ELO_MIN
    assert server._sessione["elo_max"] == server.ELO_MAX
    # ha pescato anche puzzle oltre il tetto base (allargamento temporaneo)
    ids = {p["id"] for p in server._sessione["coda"]}
    assert any(i.startswith("alto") for i in ids)


def test_tema_esaurito_segnala(ambiente, monkeypatch, tmp_path):
    """Pochi puzzle nuovi anche col tetto massimo: esaurito=True, base intatta."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(2)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    server._sessione["tema_libero"] = "forchetta"
    esaurito = server._riempi_coda_tema("fork")

    assert esaurito is True
    assert server._sessione["esaurito"] is True
    assert server._sessione["elo_min"] == server.ELO_MIN
    assert server._sessione["elo_max"] == server.ELO_MAX


def test_tema_non_esaurito_se_abbastanza(ambiente, monkeypatch, tmp_path):
    """Con tanti puzzle nuovi in fascia base non c'e' allargamento ne' esaurimento."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(20)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    server._sessione["tema_libero"] = "forchetta"
    esaurito = server._riempi_coda_tema("fork")

    assert esaurito is False
    assert server._sessione["esaurito"] is False


def test_scegli_tema_segnala_esaurimento(ambiente, monkeypatch, tmp_path):
    """L'endpoint /scegli-tema riporta esaurito e un suggerimento di cambiare tema."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(2)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._sessione["piano"] = {"blocchi": []}  # sessione gia' "pronta"

    risposta = scegli_tema("forchetta")
    assert risposta["esaurito"] is True
    assert "suggerimento" in risposta


def test_prossimo_puzzle_segnala_esaurimento(ambiente, monkeypatch, tmp_path):
    """L'endpoint /prossimo-puzzle riporta esaurito mentre serve gli ultimi puzzle."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(2)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._sessione["piano"] = {"blocchi": []}
    scegli_tema("forchetta")

    r = prossimo_puzzle()
    assert r["fine"] is False
    assert r["esaurito"] is True
    assert "suggerimento" in r


# --- Statistiche per tema ------------------------------------------------

def test_statistiche_temi_traccia(ambiente):
    """Conta tentati e risolti_primo per il tema di ogni puzzle (preso dalla coda)."""
    server._sessione["piano"] = {"blocchi": []}
    server._sessione["coda"] = [
        {"id": "p1", "motivo_allenamento": "forchetta"},
        {"id": "p2", "motivo_allenamento": "forchetta"},
        {"id": "p3", "motivo_allenamento": "inchiodatura"},
    ]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    registra_esito(Esito(puzzle_id="p2", risultato="fallito"))
    registra_esito(Esito(puzzle_id="p3", risultato="primo"))

    st = server._sessione["statistiche_temi"]
    assert st["forchetta"] == {"tentati": 2, "risolti_primo": 1}
    assert st["inchiodatura"] == {"tentati": 1, "risolti_primo": 1}


def test_statistiche_temi_secondo_non_conta_come_primo(ambiente):
    """Il 'secondo' conta come tentato ma non come risolto al primo colpo."""
    server._sessione["piano"] = {"blocchi": []}
    server._sessione["coda"] = [{"id": "p1", "motivo_allenamento": "infilata"}]
    registra_esito(Esito(puzzle_id="p1", risultato="secondo"))
    assert server._sessione["statistiche_temi"]["infilata"] == {
        "tentati": 1, "risolti_primo": 0}


def test_statistiche_temi_endpoint_percentuale(ambiente):
    """L'endpoint espone la percentuale di successo al primo colpo per tema."""
    server._sessione["piano"] = {"blocchi": []}
    server._sessione["coda"] = [
        {"id": "p1", "motivo_allenamento": "forchetta"},
        {"id": "p2", "motivo_allenamento": "forchetta"},
    ]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    registra_esito(Esito(puzzle_id="p2", risultato="fallito"))
    r = statistiche_temi()
    assert r["temi"]["forchetta"] == {
        "tentati": 2, "risolti_primo": 1, "percentuale_primo": 50.0}


def test_statistiche_temi_persiste_su_file(ambiente):
    """Le statistiche per tema sopravvivono al riavvio (salvate e ricaricate)."""
    server._sessione["piano"] = {"blocchi": []}
    server._sessione["coda"] = [{"id": "p1", "motivo_allenamento": "forchetta"}]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))

    # il file contiene gia' i dati per tema
    with open(ambiente["stato_path"], "r", encoding="utf-8") as f:
        dati = json.load(f)
    assert dati["statistiche_temi"]["forchetta"] == {"tentati": 1, "risolti_primo": 1}

    # azzero e ricarico: i dati tornano
    _stato_pulito()
    assert _carica_stato() is True
    assert server._sessione["statistiche_temi"]["forchetta"] == {
        "tentati": 1, "risolti_primo": 1}


def test_statistiche_temi_non_influenza_fascia(ambiente):
    """I conteggi per tema non toccano la fascia Elo (non-interferenza)."""
    server._sessione["piano"] = {"blocchi": []}
    server._sessione["coda"] = [
        {"id": f"p{i}", "motivo_allenamento": "forchetta"} for i in range(3)]
    em0, ex0 = server._sessione["elo_min"], server._sessione["elo_max"]
    for i in range(3):
        registra_esito(Esito(puzzle_id=f"p{i}", risultato="primo"))
    # meno di BLOCCO_ADATTIVO esiti: nessun ricalibro, fascia invariata
    assert (server._sessione["elo_min"], server._sessione["elo_max"]) == (em0, ex0)
    assert server._sessione["statistiche_temi"]["forchetta"]["tentati"] == 3


def test_statistiche_temi_puzzle_senza_tema(ambiente):
    """Un puzzle senza motivo_allenamento finisce nel secchio 'altro'."""
    server._sessione["piano"] = {"blocchi": []}
    server._sessione["coda"] = [{"id": "p1", "motivo_allenamento": None}]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    assert server._sessione["statistiche_temi"]["altro"] == {
        "tentati": 1, "risolti_primo": 1}
