"""
Test del backend (api/server.py).

Non avvia un vero server HTTP (servirebbe httpx): chiama direttamente le funzioni
degli endpoint, che sono normali funzioni Python. Lo stato globale _sessione viene
azzerato prima di ogni test, e i percorsi su disco (stato salvato, database) sono
reindirizzati su file temporanei con monkeypatch.

Dopo il punto 1 della visione estesa il backend gestisce TRE flussi indipendenti
(piano / temi / errori): molti test verificano l'indipendenza delle fasce, la
persistenza dei tre stati e la retrocompatibilita' col vecchio file a stato singolo.

Esegui (dalla cartella api, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import sqlite3
import tempfile
from unittest import mock
import pytest

import server
from server import (
    Esito, registra_esito, statistiche, statistiche_temi, lista_temi,
    scegli_tema, prossimo_puzzle, progressi, lista_flussi, imposta_flusso,
    _salva_stato, _carica_stato, _valuta_adattivita,
    _crea_snapshot, _calcola_tendenza, _riepilogo_progressi, _riepilogo_complessivo,
    _carica_puzzle_errori, _riempi_coda_errori,
    profilo_carenze, _arricchisci_profilo, storico_profili,
)


def _stato_pulito():
    """Riporta _sessione ai valori di default, come a backend appena avviato."""
    server._sessione.update({
        "pronta": True,  # evita che statistiche()/endpoint costruiscano un piano vero
        "flusso_attivo": "piano",
        "visti": set(),
        "flussi": {nome: server._nuovo_flusso() for nome in server.FLUSSI},
    })
    server._PUZZLE_ERRORI = []  # nessun puzzle-errore caricato, salvo dove serve


def _flussi():
    return server._sessione["flussi"]


@pytest.fixture
def ambiente(monkeypatch):
    """
    Stato pulito + percorsi su file temporanei, niente accessi al vero DB ne' ai dati
    reali. Reindirizza anche lo storico profili (Tappa D) e la cartella categorie su
    una sandbox temporanea, cosi' /profilo non legge ne' scrive i file di progetto.
    """
    cartella = tempfile.mkdtemp()
    stato_path = os.path.join(cartella, "stato.json")
    storico_path = os.path.join(cartella, "storico_profili.json")
    categorie_dir = os.path.join(cartella, "categorie")
    monkeypatch.setattr(server, "PERCORSO_STATO", stato_path)
    monkeypatch.setattr(server, "PERCORSO_STORICO", storico_path)
    monkeypatch.setattr(server, "PERCORSO_CATEGORIE", categorie_dir)
    _stato_pulito()
    yield {"stato_path": stato_path, "storico_path": storico_path,
           "categorie_dir": categorie_dir}
    _stato_pulito()
    try:
        shutil.rmtree(cartella)
    except OSError:
        pass


# --- Persistenza dei tre flussi ------------------------------------------

def test_salva_e_carica_tre_flussi(ambiente):
    """Round-trip: i tre flussi e i visti globali si salvano e si ricaricano."""
    fp = _flussi()["piano"]
    fp.update({"elo_min": 1150, "elo_max": 1350, "tentati": 7, "risolti_primo": 5,
               "storico_fasce": [{"azione": "alzata"}]})
    ft = _flussi()["temi"]
    ft.update({"elo_min": 1450, "elo_max": 1650, "tentati": 3, "tema_libero": "forchetta",
               "statistiche_temi": {"forchetta": {"tentati": 3, "risolti_primo": 2}}})
    server._sessione["visti"] = {"a", "b", "c"}
    server._sessione["flusso_attivo"] = "temi"
    _salva_stato()

    _stato_pulito()
    assert _carica_stato() is True
    assert _flussi()["piano"]["elo_min"] == 1150
    assert _flussi()["piano"]["tentati"] == 7
    assert _flussi()["piano"]["storico_fasce"] == [{"azione": "alzata"}]
    assert _flussi()["temi"]["elo_max"] == 1650
    assert _flussi()["temi"]["tema_libero"] == "forchetta"
    assert _flussi()["temi"]["statistiche_temi"]["forchetta"]["risolti_primo"] == 2
    assert server._sessione["visti"] == {"a", "b", "c"}  # globali, ricostruiti da lista
    assert server._sessione["flusso_attivo"] == "temi"


def test_salva_scrive_formato_v2(ambiente):
    """Il file salvato e' nel formato nuovo: versione 2, chiave 'flussi', visti globali."""
    server._sessione["visti"] = {"x", "y"}
    _flussi()["piano"]["tentati"] = 4
    _salva_stato()
    with open(ambiente["stato_path"], "r", encoding="utf-8") as f:
        dati = json.load(f)
    assert dati["versione"] == 2
    assert set(dati["flussi"].keys()) == set(server.FLUSSI)
    assert isinstance(dati["visti"], list)
    assert set(dati["visti"]) == {"x", "y"}
    assert dati["flussi"]["piano"]["tentati"] == 4


def test_carica_senza_file(ambiente):
    """Senza file salvato, _carica_stato segnala False (parte pulito)."""
    assert not os.path.exists(ambiente["stato_path"])
    assert _carica_stato() is False


def test_carica_file_corrotto(ambiente):
    with open(ambiente["stato_path"], "w", encoding="utf-8") as f:
        f.write("{ questo non e' json valido")
    assert _carica_stato() is False


# --- Retrocompatibilita' col vecchio formato (stato singolo) -------------

def test_carica_vecchio_formato_migra_in_piano(ambiente):
    """
    Il vecchio file a stato singolo (senza 'flussi') viene migrato nel flusso
    'piano' senza crashare; i visti diventano globali; gli altri flussi restano vuoti.
    """
    vecchio = {
        "elo_min": 1250, "elo_max": 1450, "tentati": 100, "risolti_primo": 80,
        "risolti_secondo": 15, "falliti": 5, "visti": ["x", "y", "z"],
        "storico_fasce": [{"azione": "alzata"}],
        "statistiche_temi": {"forchetta": {"tentati": 10, "risolti_primo": 8}},
        "snapshot_progresso": [{"timestamp": "t", "tentati": 10,
                                "percentuale_primo_colpo": 80.0,
                                "fascia_elo": [1250, 1450]}],
    }
    with open(ambiente["stato_path"], "w", encoding="utf-8") as f:
        json.dump(vecchio, f)

    assert _carica_stato() is True
    fp = _flussi()["piano"]
    assert fp["tentati"] == 100
    assert fp["risolti_primo"] == 80
    assert fp["elo_min"] == 1250
    assert fp["statistiche_temi"]["forchetta"]["risolti_primo"] == 8
    assert len(fp["snapshot_progresso"]) == 1
    # visti -> globali
    assert server._sessione["visti"] == {"x", "y", "z"}
    # gli altri flussi restano vuoti, fascia ai default
    assert _flussi()["temi"]["tentati"] == 0
    assert _flussi()["errori"]["tentati"] == 0
    assert _flussi()["temi"]["elo_min"] == server.ELO_MIN
    assert server._sessione["flusso_attivo"] == "piano"


def test_vecchio_formato_poi_risalva_in_v2(ambiente):
    """Dopo aver migrato un vecchio file, il salvataggio successivo e' in v2."""
    with open(ambiente["stato_path"], "w", encoding="utf-8") as f:
        json.dump({"elo_min": 1100, "elo_max": 1300, "tentati": 9,
                   "visti": ["a"]}, f)
    assert _carica_stato() is True
    _salva_stato()
    with open(ambiente["stato_path"], "r", encoding="utf-8") as f:
        dati = json.load(f)
    assert dati["versione"] == 2
    assert dati["flussi"]["piano"]["tentati"] == 9


# --- Statistiche ed esiti (sul flusso attivo) ----------------------------

def test_registra_esito_aggiorna_statistiche(ambiente):
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    registra_esito(Esito(puzzle_id="p2", risultato="secondo"))
    registra_esito(Esito(puzzle_id="p3", risultato="fallito"))

    s = statistiche()
    assert s["flusso"] == "piano"
    assert s["tentati"] == 3
    assert s["risolti_primo"] == 1
    assert s["risolti_secondo"] == 1
    assert s["falliti"] == 1
    assert s["percentuale_primo"] == round(100 / 3, 1)
    # il riepilogo complessivo e' presente
    assert s["complessivo"]["tentati_totali"] == 3


def test_esito_aggiorna_solo_flusso_attivo(ambiente):
    """Un esito conta solo nel flusso attivo: gli altri flussi non si toccano."""
    server._sessione["flusso_attivo"] = "temi"
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    assert _flussi()["temi"]["tentati"] == 1
    assert _flussi()["temi"]["risolti_primo"] == 1
    assert _flussi()["piano"]["tentati"] == 0
    assert _flussi()["errori"]["tentati"] == 0


def test_esito_persiste_su_file(ambiente):
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    assert os.path.exists(ambiente["stato_path"])
    with open(ambiente["stato_path"], "r", encoding="utf-8") as f:
        dati = json.load(f)
    assert dati["versione"] == 2
    assert dati["flussi"]["piano"]["tentati"] == 1
    assert dati["flussi"]["piano"]["risolti_primo"] == 1


# --- Riepilogo complessivo (somma dei flussi) ----------------------------

def test_riepilogo_complessivo_somma_flussi(ambiente):
    _flussi()["piano"].update({"tentati": 10, "risolti_primo": 7})
    _flussi()["temi"].update({"tentati": 5, "risolti_primo": 2})
    r = _riepilogo_complessivo()
    assert r["tentati_totali"] == 15
    assert r["risolti_primo_totali"] == 9
    assert r["percentuale_primo"] == 60.0
    assert r["per_flusso"]["piano"]["tentati"] == 10
    assert r["per_flusso"]["temi"]["risolti_primo"] == 2
    assert r["per_flusso"]["errori"]["tentati"] == 0


# --- Selettore di flusso -------------------------------------------------

def test_lista_flussi(ambiente):
    r = lista_flussi()
    assert r["flusso_attivo"] == "piano"
    assert set(r["flussi"].keys()) == set(server.FLUSSI)
    assert r["flussi"]["piano"]["implementato"] is True
    assert r["flussi"]["errori"]["implementato"] is True  # implementato col punto 6
    assert "complessivo" in r


def test_imposta_flusso_cambia_attivo(ambiente):
    r = imposta_flusso("temi")
    assert server._sessione["flusso_attivo"] == "temi"
    assert r["flusso_attivo"] == "temi"


def test_imposta_flusso_sconosciuto(ambiente):
    r = imposta_flusso("inesistente")
    assert r.status_code == 404


# --- Indipendenza delle fasce adattive tra flussi ------------------------

def test_fasce_indipendenti_tra_flussi(ambiente, monkeypatch):
    """Alzare la fascia del flusso 'piano' NON tocca la fascia del flusso 'temi'."""
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda f: None)
    fp = _flussi()["piano"]
    ft = _flussi()["temi"]
    ft_prima = (ft["elo_min"], ft["elo_max"])

    fp["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    fp["blocco_primo"] = server.BLOCCO_ADATTIVO  # 100% -> alza
    assert _valuta_adattivita(fp) == "alzata"
    assert fp["elo_min"] == server.ELO_MIN + server.PASSO_ELO
    # il flusso temi e' rimasto fermo
    assert (ft["elo_min"], ft["elo_max"]) == ft_prima
    assert ft["storico_fasce"] == []


def test_fasce_indipendenti_via_esiti(ambiente):
    """Esiti diversi sui due flussi muovono le rispettive fasce in modo indipendente."""
    # flusso temi: 10 esiti tutti al primo -> deve alzare la sua fascia
    server._sessione["flusso_attivo"] = "temi"
    for i in range(server.BLOCCO_ADATTIVO):
        registra_esito(Esito(puzzle_id=f"t{i}", risultato="primo"))
    assert _flussi()["temi"]["elo_min"] == server.ELO_MIN + server.PASSO_ELO
    # flusso piano: mai toccato, resta ai default
    assert _flussi()["piano"]["elo_min"] == server.ELO_MIN
    assert _flussi()["piano"]["elo_max"] == server.ELO_MAX


def test_adattivita_blocco_incompleto(ambiente):
    """Sotto BLOCCO_ADATTIVO puzzle non si valuta nulla."""
    fp = _flussi()["piano"]
    fp["blocco_conteggio"] = server.BLOCCO_ADATTIVO - 1
    fp["blocco_primo"] = server.BLOCCO_ADATTIVO - 1
    assert _valuta_adattivita(fp) is None


def test_adattivita_abbassa_fascia(ambiente, monkeypatch):
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda f: None)
    fp = _flussi()["piano"]
    fp["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    fp["blocco_primo"] = 0  # 0% al primo
    em0, ex0 = fp["elo_min"], fp["elo_max"]
    assert _valuta_adattivita(fp) == "abbassata"
    assert fp["elo_min"] == em0 - server.PASSO_ELO
    assert fp["elo_max"] == ex0 - server.PASSO_ELO


def test_adattivita_fascia_invariata(ambiente, monkeypatch):
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda f: None)
    fp = _flussi()["piano"]
    fp["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    fp["blocco_primo"] = 8  # 80%: tra le soglie -> invariata
    em0, ex0 = fp["elo_min"], fp["elo_max"]
    assert _valuta_adattivita(fp) is None
    assert (fp["elo_min"], fp["elo_max"]) == (em0, ex0)
    assert fp["storico_fasce"] == []


# --- Temi ----------------------------------------------------------------

def test_lista_temi(ambiente):
    risposta = lista_temi()
    assert set(risposta["temi"]) == set(server.TEMI_DISPONIBILI.keys())


def test_temi_raggruppati_per_categoria(ambiente):
    """I 24 temi sono divisi in 3 categorie e ogni tema appartiene a una sola."""
    risposta = lista_temi()
    assert set(risposta["categorie"].keys()) == {"Tattiche", "Matti", "Finali"}
    assert len(risposta["temi"]) == 24
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
    f = _flussi()["temi"]
    f["elo_min"], f["elo_max"] = 1050, 1250
    chiamate = []

    def pesca(emax):
        chiamate.append(emax)
        return list(range(server.PUZZLE_MINIMI)) if emax >= 1350 else list(range(2))

    righe, esaurito = server._pesca_allargando(f, pesca)
    assert esaurito is False
    assert len(righe) == server.PUZZLE_MINIMI
    assert chiamate == [1250, 1350]
    assert (f["elo_min"], f["elo_max"]) == (1050, 1250)  # base intatta


def test_pesca_allargando_rispetta_max_400(ambiente):
    """Senza puzzle, allarga di 100 alla volta fino a +400 e poi si arrende."""
    f = _flussi()["temi"]
    f["elo_min"], f["elo_max"] = 1050, 1250
    tetti = []

    def pesca(emax):
        tetti.append(emax)
        return []

    righe, esaurito = server._pesca_allargando(f, pesca)
    assert esaurito is True
    assert tetti == [1250, 1350, 1450, 1550, 1650]
    assert (f["elo_min"], f["elo_max"]) == (1050, 1250)


def test_pesca_allargando_cappa_a_elo_assoluto(ambiente):
    """L'allargamento non supera mai ELO_MAX_ASSOLUTO (2800)."""
    f = _flussi()["temi"]
    f["elo_min"], f["elo_max"] = 2500, 2700
    tetti = []

    def pesca(emax):
        tetti.append(emax)
        return []

    server._pesca_allargando(f, pesca)
    assert tetti == [2700, server.ELO_MAX_ASSOLUTO]


def test_tema_allarga_tetto_temporaneo_senza_toccare_base(ambiente, monkeypatch, tmp_path):
    """Pochi puzzle nuovi in fascia base ma abbastanza poco sopra: ripesca senza
    modificare la fascia di base del flusso temi."""
    db = str(tmp_path / "puzzle.db")
    puzzle = [(f"base{i}", 1100, "middlegame fork") for i in range(3)]
    puzzle += [(f"alto{i}", 1280, "middlegame fork") for i in range(8)]
    _crea_db_puzzle(db, puzzle)
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    f = _flussi()["temi"]
    f["tema_libero"] = "forchetta"
    esaurito = server._riempi_coda_tema(f, "fork")

    assert esaurito is False
    assert f["esaurito"] is False
    assert f["elo_min"] == server.ELO_MIN  # base intatta
    assert f["elo_max"] == server.ELO_MAX
    ids = {p["id"] for p in f["coda"]}
    assert any(i.startswith("alto") for i in ids)


def test_tema_esaurito_segnala(ambiente, monkeypatch, tmp_path):
    """Pochi puzzle nuovi anche col tetto massimo: esaurito=True, base intatta."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(2)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    f = _flussi()["temi"]
    f["tema_libero"] = "forchetta"
    esaurito = server._riempi_coda_tema(f, "fork")

    assert esaurito is True
    assert f["esaurito"] is True
    assert f["elo_min"] == server.ELO_MIN
    assert f["elo_max"] == server.ELO_MAX


def test_scegli_tema_attiva_flusso_temi(ambiente, monkeypatch, tmp_path):
    """scegli_tema attiva il flusso 'temi', imposta il tema e riempie la sua coda."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(20)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    risposta = scegli_tema("forchetta")
    assert risposta["flusso_attivo"] == "temi"
    assert server._sessione["flusso_attivo"] == "temi"
    assert _flussi()["temi"]["tema_libero"] == "forchetta"
    assert len(_flussi()["temi"]["coda"]) > 0
    # il flusso piano non e' stato toccato
    assert _flussi()["piano"]["coda"] == []


def test_scegli_tema_segnala_esaurimento(ambiente, monkeypatch, tmp_path):
    """scegli_tema riporta esaurito e un suggerimento di cambiare tema."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(2)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)

    risposta = scegli_tema("forchetta")
    assert risposta["esaurito"] is True
    assert "suggerimento" in risposta


def test_prossimo_puzzle_segnala_esaurimento(ambiente, monkeypatch, tmp_path):
    """prossimo_puzzle riporta esaurito mentre serve gli ultimi puzzle del tema."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(2)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    scegli_tema("forchetta")

    r = prossimo_puzzle()
    assert r["fine"] is False
    assert r["flusso"] == "temi"
    assert r["esaurito"] is True
    assert "suggerimento" in r


def test_visti_globali_tra_flussi(ambiente, monkeypatch, tmp_path):
    """I 'visti' sono globali: il flusso temi non ripesca puzzle gia' visti altrove."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"f{i}", 1100, "middlegame fork") for i in range(10)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    # Simulo che alcuni puzzle siano gia' stati visti (es. nel flusso piano).
    server._sessione["visti"] = {"f0", "f1", "f2"}

    f = _flussi()["temi"]
    f["tema_libero"] = "forchetta"
    server._riempi_coda_tema(f, "fork")
    ids = {p["id"] for p in f["coda"]}
    assert ids.isdisjoint({"f0", "f1", "f2"})


# --- Statistiche per tema (sul flusso attivo) ----------------------------

def test_statistiche_temi_traccia(ambiente):
    f = _flussi()["piano"]
    f["coda"] = [
        {"id": "p1", "motivo_allenamento": "forchetta"},
        {"id": "p2", "motivo_allenamento": "forchetta"},
        {"id": "p3", "motivo_allenamento": "inchiodatura"},
    ]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    registra_esito(Esito(puzzle_id="p2", risultato="fallito"))
    registra_esito(Esito(puzzle_id="p3", risultato="primo"))

    st = f["statistiche_temi"]
    assert st["forchetta"] == {"tentati": 2, "risolti_primo": 1}
    assert st["inchiodatura"] == {"tentati": 1, "risolti_primo": 1}


def test_statistiche_temi_secondo_non_conta_come_primo(ambiente):
    f = _flussi()["piano"]
    f["coda"] = [{"id": "p1", "motivo_allenamento": "infilata"}]
    registra_esito(Esito(puzzle_id="p1", risultato="secondo"))
    assert f["statistiche_temi"]["infilata"] == {"tentati": 1, "risolti_primo": 0}


def test_statistiche_temi_endpoint_percentuale(ambiente):
    f = _flussi()["piano"]
    f["coda"] = [
        {"id": "p1", "motivo_allenamento": "forchetta"},
        {"id": "p2", "motivo_allenamento": "forchetta"},
    ]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    registra_esito(Esito(puzzle_id="p2", risultato="fallito"))
    r = statistiche_temi()
    assert r["flusso"] == "piano"
    assert r["temi"]["forchetta"] == {
        "tentati": 2, "risolti_primo": 1, "percentuale_primo": 50.0}


def test_statistiche_temi_separate_per_flusso(ambiente):
    """Le statistiche-per-tema sono indipendenti tra i flussi."""
    # piano
    _flussi()["piano"]["coda"] = [{"id": "a1", "motivo_allenamento": "forchetta"}]
    registra_esito(Esito(puzzle_id="a1", risultato="primo"))
    # temi
    server._sessione["flusso_attivo"] = "temi"
    _flussi()["temi"]["coda"] = [{"id": "b1", "motivo_allenamento": "inchiodatura"}]
    registra_esito(Esito(puzzle_id="b1", risultato="fallito"))

    assert _flussi()["piano"]["statistiche_temi"] == {
        "forchetta": {"tentati": 1, "risolti_primo": 1}}
    assert _flussi()["temi"]["statistiche_temi"] == {
        "inchiodatura": {"tentati": 1, "risolti_primo": 0}}


def test_statistiche_temi_persiste_su_file(ambiente):
    f = _flussi()["piano"]
    f["coda"] = [{"id": "p1", "motivo_allenamento": "forchetta"}]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))

    with open(ambiente["stato_path"], "r", encoding="utf-8") as fp:
        dati = json.load(fp)
    assert dati["flussi"]["piano"]["statistiche_temi"]["forchetta"] == {
        "tentati": 1, "risolti_primo": 1}

    _stato_pulito()
    assert _carica_stato() is True
    assert _flussi()["piano"]["statistiche_temi"]["forchetta"] == {
        "tentati": 1, "risolti_primo": 1}


def test_statistiche_temi_puzzle_senza_tema(ambiente):
    f = _flussi()["piano"]
    f["coda"] = [{"id": "p1", "motivo_allenamento": None}]
    registra_esito(Esito(puzzle_id="p1", risultato="primo"))
    assert f["statistiche_temi"]["altro"] == {"tentati": 1, "risolti_primo": 1}


# --- Snapshot di progresso (per flusso) ----------------------------------

def test_crea_snapshot_fotografa_stato(ambiente):
    f = _flussi()["piano"]
    f.update({"tentati": 4, "risolti_primo": 3, "elo_min": 1200, "elo_max": 1400})
    _crea_snapshot(f)
    snap = f["snapshot_progresso"]
    assert len(snap) == 1
    assert snap[0]["tentati"] == 4
    assert snap[0]["percentuale_primo_colpo"] == 75.0
    assert snap[0]["fascia_elo"] == [1200, 1400]
    assert "timestamp" in snap[0]


def test_snapshot_ogni_dieci_tentativi(ambiente):
    """Uno snapshot ogni SNAPSHOT_OGNI puzzle tentati del flusso attivo."""
    for i in range(server.SNAPSHOT_OGNI * 2):
        registra_esito(Esito(puzzle_id=f"p{i}", risultato="secondo"))
    snap = _flussi()["piano"]["snapshot_progresso"]
    assert len(snap) == 2
    assert snap[0]["tentati"] == server.SNAPSHOT_OGNI
    assert snap[1]["tentati"] == server.SNAPSHOT_OGNI * 2


def test_snapshot_persiste_su_file(ambiente):
    f = _flussi()["piano"]
    f.update({"tentati": 10, "risolti_primo": 8})
    _crea_snapshot(f)
    _salva_stato()

    _stato_pulito()
    assert _carica_stato() is True
    snap = _flussi()["piano"]["snapshot_progresso"]
    assert len(snap) == 1
    assert snap[0]["percentuale_primo_colpo"] == 80.0


def test_snapshot_separati_per_flusso(ambiente):
    """Gli snapshot di un flusso non finiscono in un altro flusso."""
    _crea_snapshot(_flussi()["piano"])
    assert len(_flussi()["piano"]["snapshot_progresso"]) == 1
    assert len(_flussi()["temi"]["snapshot_progresso"]) == 0


# --- Indicatore di tendenza ----------------------------------------------

def _snap(fascia):
    return {"fascia_elo": list(fascia)}


def test_tendenza_pochi_snapshot_e_stabile(ambiente):
    assert _calcola_tendenza([]) == {
        "direzione": "stabile", "freccia": "→", "etichetta": "Stabile"}
    assert _calcola_tendenza([_snap([1200, 1400])])["direzione"] == "stabile"


def test_tendenza_in_crescita(ambiente):
    snap = [_snap([1100, 1300]), _snap([1200, 1400]), _snap([1300, 1500])]
    t = _calcola_tendenza(snap)
    assert t["direzione"] == "su"
    assert t["freccia"] == "↑"
    assert t["etichetta"] == "In crescita"


def test_tendenza_in_calo(ambiente):
    snap = [_snap([1400, 1600]), _snap([1300, 1500]), _snap([1200, 1400])]
    t = _calcola_tendenza(snap)
    assert t["direzione"] == "giu"
    assert t["freccia"] == "↓"
    assert t["etichetta"] == "In calo"


def test_tendenza_stabile_se_ferma(ambiente):
    snap = [_snap([1200, 1400]), _snap([1300, 1500]), _snap([1200, 1400])]
    assert _calcola_tendenza(snap)["direzione"] == "stabile"


def test_tendenza_usa_solo_la_finestra(ambiente):
    vecchi = [_snap([2000, 2200])] * 3
    finestra = [_snap([1000, 1200]), _snap([1100, 1300]),
                _snap([1200, 1400]), _snap([1300, 1500]), _snap([1400, 1600])]
    assert _calcola_tendenza(vecchi + finestra, finestra=5)["direzione"] == "su"


# --- Riepilogo ed endpoint progressi (per flusso) ------------------------

def test_riepilogo_calcola_guadagno_e_temi(ambiente):
    f = _flussi()["piano"]
    f.update({"tentati": 10, "risolti_primo": 7, "elo_min": 1300, "elo_max": 1500})
    f["snapshot_progresso"] = [{
        "timestamp": "t", "tentati": 5, "percentuale_primo_colpo": 60.0,
        "fascia_elo": [1100, 1300]}]
    f["statistiche_temi"] = {
        "forchetta": {"tentati": 4, "risolti_primo": 4},
        "inchiodatura": {"tentati": 4, "risolti_primo": 1},
    }
    r = _riepilogo_progressi(f)
    assert r["tentati_totali"] == 10
    assert r["percentuale_primo_storica"] == 70.0
    assert r["elo_iniziale"] == [1100, 1300]
    assert r["elo_attuale"] == [1300, 1500]
    assert r["guadagno"] == 200
    assert r["tema_migliore"]["tema"] == "forchetta"
    assert r["tema_peggiore"]["tema"] == "inchiodatura"


def test_riepilogo_senza_snapshot_usa_storico_fasce(ambiente):
    f = _flussi()["piano"]
    f["storico_fasce"] = [{"da": [1050, 1250], "a": [1150, 1350],
                           "percentuale": 100.0, "azione": "alzata"}]
    f.update({"elo_min": 1150, "elo_max": 1350})
    r = _riepilogo_progressi(f)
    assert r["elo_iniziale"] == [1050, 1250]
    assert r["guadagno"] == 100


def test_progressi_endpoint_struttura(ambiente):
    f = _flussi()["piano"]
    f["snapshot_progresso"] = [
        {"timestamp": "t1", "tentati": 10, "percentuale_primo_colpo": 50.0,
         "fascia_elo": [1100, 1300]},
        {"timestamp": "t2", "tentati": 20, "percentuale_primo_colpo": 60.0,
         "fascia_elo": [1200, 1400]},
    ]
    r = progressi()
    assert r["flusso"] == "piano"
    assert len(r["snapshot"]) == 2
    assert r["tendenza"]["direzione"] == "su"
    assert "riepilogo" in r


def test_progressi_riferito_al_flusso_attivo(ambiente):
    """L'endpoint /progressi riflette il flusso attivo, non un altro."""
    _flussi()["temi"]["snapshot_progresso"] = [
        {"timestamp": "t", "tentati": 10, "percentuale_primo_colpo": 90.0,
         "fascia_elo": [1500, 1700]}]
    server._sessione["flusso_attivo"] = "temi"
    r = progressi()
    assert r["flusso"] == "temi"
    assert len(r["snapshot"]) == 1
    # passando a piano, gli snapshot del temi non si vedono
    server._sessione["flusso_attivo"] = "piano"
    assert len(progressi()["snapshot"]) == 0


# --- Flusso "errori" (punto 6) -------------------------------------------

def _errore(pid, rating, lunghezza_soluzione=None):
    """Un puzzle-errore nel formato della coda (come in data/coda_errori.json).

    Con lunghezza_soluzione impostato simula un puzzle del file ESTESO (multi-mossa).
    """
    p = {"id": pid, "fen": "f", "moves": "m1 m2", "rating": rating,
         "themes": "errore", "motivo_allenamento": "errore",
         "fase_allenamento": None}
    if lunghezza_soluzione is not None:
        p["lunghezza_soluzione"] = lunghezza_soluzione
    return p


def _scrivi_coda_errori(percorso, puzzle):
    """Scrive un mini coda_errori.json temporaneo."""
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(puzzle, f)


def _percorsi_errori(monkeypatch, tmp_path):
    """Restituisce (esteso, base) come path stringa e li monkeypatcha sul server.

    Entrambi puntano dentro tmp_path: nessun test tocca i file reali in data/.
    """
    esteso = str(tmp_path / "coda_errori_estesa.json")
    base = str(tmp_path / "coda_errori.json")
    monkeypatch.setattr(server, "PERCORSO_CODA_ERRORI", esteso)
    monkeypatch.setattr(server, "PERCORSO_CODA_ERRORI_BASE", base)
    return esteso, base


def test_carica_puzzle_errori_preferisce_esteso(ambiente, monkeypatch, tmp_path):
    """Con esteso e base presenti, _carica_puzzle_errori usa l'ESTESO."""
    esteso, base = _percorsi_errori(monkeypatch, tmp_path)
    _scrivi_coda_errori(esteso, [_errore("ext1", 1100, lunghezza_soluzione=2)])
    _scrivi_coda_errori(base, [_errore("base1", 1100), _errore("base2", 1200)])

    _carica_puzzle_errori()
    assert {p["id"] for p in server._PUZZLE_ERRORI} == {"ext1"}


def test_carica_puzzle_errori_fallback_su_base(ambiente, monkeypatch, tmp_path):
    """Solo base presente (esteso mancante): ripiega sul base con un warning."""
    esteso, base = _percorsi_errori(monkeypatch, tmp_path)
    _scrivi_coda_errori(base, [_errore("base1", 1100), _errore("base2", 1200)])

    with mock.patch.object(server.logger, "warning") as warn:
        _carica_puzzle_errori()
    assert {p["id"] for p in server._PUZZLE_ERRORI} == {"base1", "base2"}
    assert warn.called  # il fallback deve loggare un warning


def test_carica_puzzle_errori_solo_esteso(ambiente, monkeypatch, tmp_path):
    """Solo esteso presente: lo usa direttamente."""
    esteso, base = _percorsi_errori(monkeypatch, tmp_path)
    _scrivi_coda_errori(esteso, [_errore("ext1", 1100, lunghezza_soluzione=3)])

    _carica_puzzle_errori()
    assert {p["id"] for p in server._PUZZLE_ERRORI} == {"ext1"}


def test_carica_puzzle_errori_file_mancante(ambiente, monkeypatch, tmp_path):
    """Nessuno dei due file: lista vuota, nessun crash (flusso esistera' ma vuoto)."""
    _percorsi_errori(monkeypatch, tmp_path)  # entrambi i path non esistono
    _carica_puzzle_errori()
    assert server._PUZZLE_ERRORI == []


def test_riempi_coda_errori_pesca_prima_dagli_errori(ambiente, monkeypatch, tmp_path):
    """Con abbastanza miei errori nella fascia, la coda e' fatta dai miei errori."""
    # DB con tanti rinforzi disponibili, per essere sicuri che NON vengano usati
    # quando i miei errori bastano gia'.
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"lic{i}", 1100, "fork") for i in range(50)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    # Tanti errori nella fascia base (1050-1250).
    server._PUZZLE_ERRORI = [_errore(f"err{i}", 1100)
                             for i in range(server.PUZZLE_PER_BLOCCO + 5)]

    f = _flussi()["errori"]
    f["errori_attivo"] = True
    server._riempi_coda_errori(f)

    assert len(f["coda"]) == server.PUZZLE_PER_BLOCCO
    # Tutti dai miei errori: nessun rinforzo lichess.
    assert all(p["origine"] == "errore" for p in f["coda"])
    assert all(p["motivo_allenamento"] == "errore" for p in f["coda"])
    assert all(p["id"].startswith("err") for p in f["coda"])
    # Gli id sono finiti nei visti globali.
    assert {p["id"] for p in f["coda"]}.issubset(server._sessione["visti"])


def test_riempi_coda_errori_completa_con_rinforzi_lichess(ambiente, monkeypatch, tmp_path):
    """Pochi miei errori nella fascia: la coda si completa con rinforzi Lichess."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"lic{i}", 1100, "fork") for i in range(50)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    # Solo 2 miei errori nella fascia: i restanti devono essere rinforzi lichess.
    server._PUZZLE_ERRORI = [_errore("err0", 1100), _errore("err1", 1200)]

    f = _flussi()["errori"]
    f["errori_attivo"] = True
    server._riempi_coda_errori(f)

    miei = [p for p in f["coda"] if p["origine"] == "errore"]
    rinforzi = [p for p in f["coda"] if p["origine"] == "lichess"]
    assert len(miei) == 2
    assert len(rinforzi) > 0
    assert len(f["coda"]) == server.PUZZLE_PER_BLOCCO
    # I rinforzi sono marcati correttamente.
    assert all(p["motivo_allenamento"] == "rinforzo" for p in rinforzi)
    assert all(p["id"].startswith("lic") for p in rinforzi)


def test_riempi_coda_errori_conserva_lunghezza_soluzione(ambiente, monkeypatch, tmp_path):
    """lunghezza_soluzione (puzzle estesi) sopravvive fino al puzzle in coda.

    I puzzle senza il campo (formato base) ricevono il default 1.
    """
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"lic{i}", 1100, "fork") for i in range(50)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._PUZZLE_ERRORI = [
        _errore("ext2", 1100, lunghezza_soluzione=2),
        _errore("ext3", 1150, lunghezza_soluzione=3),
        _errore("base1", 1200),  # senza il campo -> default 1
    ]

    f = _flussi()["errori"]
    f["errori_attivo"] = True
    server._riempi_coda_errori(f)

    per_id = {p["id"]: p for p in f["coda"] if p["origine"] == "errore"}
    assert per_id["ext2"]["lunghezza_soluzione"] == 2
    assert per_id["ext3"]["lunghezza_soluzione"] == 3
    assert per_id["base1"]["lunghezza_soluzione"] == 1


def test_riempi_coda_errori_non_blocca_se_nulla(ambiente, monkeypatch, tmp_path):
    """Senza miei errori e con DB vuoto la coda resta vuota, ma non si blocca."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._PUZZLE_ERRORI = []

    f = _flussi()["errori"]
    f["errori_attivo"] = True
    esaurito = server._riempi_coda_errori(f)
    assert f["coda"] == []
    assert esaurito is True  # niente puzzle nuovi -> esaurito


def test_imposta_flusso_errori_attiva_e_riempie(ambiente, monkeypatch, tmp_path):
    """Il flusso 'errori' NON risponde piu' 501: diventa attivo e riempie la coda."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"lic{i}", 1100, "fork") for i in range(50)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._PUZZLE_ERRORI = [_errore(f"err{i}", 1100) for i in range(10)]

    r = imposta_flusso("errori")
    assert not hasattr(r, "status_code")  # non e' piu' una risposta d'errore
    assert r["flusso_attivo"] == "errori"
    assert server._sessione["flusso_attivo"] == "errori"
    f = _flussi()["errori"]
    assert f["errori_attivo"] is True
    assert len(f["coda"]) > 0
    # il flusso piano non e' stato toccato
    assert _flussi()["piano"]["coda"] == []


def test_fascia_errori_indipendente_dagli_altri(ambiente, monkeypatch):
    """La fascia del flusso 'errori' e' indipendente: muoverla non tocca gli altri."""
    monkeypatch.setattr(server, "_ricostruisci_coda_con_fascia", lambda f: None)
    fe = _flussi()["errori"]
    fp_prima = (_flussi()["piano"]["elo_min"], _flussi()["piano"]["elo_max"])

    fe["blocco_conteggio"] = server.BLOCCO_ADATTIVO
    fe["blocco_primo"] = server.BLOCCO_ADATTIVO  # 100% -> alza
    assert _valuta_adattivita(fe) == "alzata"
    assert fe["elo_min"] == server.ELO_MIN + server.PASSO_ELO
    # piano e temi fermi
    assert (_flussi()["piano"]["elo_min"], _flussi()["piano"]["elo_max"]) == fp_prima
    assert _flussi()["temi"]["elo_min"] == server.ELO_MIN


def test_persistenza_errori_attivo_e_ricostruzione(ambiente, monkeypatch, tmp_path):
    """errori_attivo si persiste; dopo un reload la coda errori si ricostruisce."""
    # Salvo uno stato col flusso errori attivo.
    _flussi()["errori"]["errori_attivo"] = True
    _salva_stato()
    with open(ambiente["stato_path"], "r", encoding="utf-8") as fp:
        dati = json.load(fp)
    assert dati["flussi"]["errori"]["errori_attivo"] is True

    # Reload: il flag torna True.
    _stato_pulito()
    assert _carica_stato() is True
    fe = _flussi()["errori"]
    assert fe["errori_attivo"] is True

    # Ricostruzione della coda errori (come fa _prepara_sessione dopo il reload).
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [(f"lic{i}", 1100, "fork") for i in range(50)])
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._PUZZLE_ERRORI = [_errore(f"err{i}", 1100) for i in range(10)]
    _riempi_coda_errori(fe)
    assert len(fe["coda"]) > 0


def test_visti_globali_rispettati_da_errori(ambiente, monkeypatch, tmp_path):
    """Un mio errore gia' visto in un altro flusso non riappare nel flusso errori."""
    db = str(tmp_path / "puzzle.db")
    _crea_db_puzzle(db, [])  # nessun rinforzo, isoliamo i soli errori
    monkeypatch.setattr(server, "PERCORSO_DB", db)
    server._PUZZLE_ERRORI = [_errore(f"err{i}", 1100) for i in range(6)]
    # Simulo che alcuni errori siano gia' stati visti altrove.
    server._sessione["visti"] = {"err0", "err1", "err2"}

    f = _flussi()["errori"]
    f["errori_attivo"] = True
    _riempi_coda_errori(f)
    ids = {p["id"] for p in f["coda"]}
    assert ids.isdisjoint({"err0", "err1", "err2"})


# --- Report delle carenze (punto 2): endpoint /profilo -------------------

def _profilo_finto(**override):
    """
    Profilo finto nel formato di costruisci_profilo, per testare l'arricchimento
    senza toccare i file in data/categorie. Numeri scelti perche' i tassi siano
    distinguibili: 1000 mosse, 100 errori gravi.

    Tattica: pezzo_in_presa 40, forchetta 30 (rilevanti), inchiodatura 6 (al 6%,
    sopra soglia), infilata 0.1% (sotto soglia), non_tattico 24.
    """
    p = {
        "giocatore": "Tester",
        "partite_analizzate": 10,
        "mosse_totali": 1000,
        "errori_gravi_totali": 100,
        "conteggio_gravita": {"best": 500, "excellent": 200, "good": 140,
                              "inaccuracy": 60, "mistake": 60, "blunder": 40},
        "mosse_per_fase": {"apertura": 300, "mediogioco": 500, "finale": 200},
        "errori_per_fase": {"apertura": 30, "mediogioco": 50, "finale": 20},
        # Tre fasi tutte al 10%: divario nullo -> fasi vicine.
        "tasso_errore_per_fase": {"apertura": 10.0, "mediogioco": 10.0, "finale": 10.0},
        "debolezza_principale": "mediogioco",
        "conteggio_tattico": {"pezzo_in_presa": 40, "forchetta": 30,
                              "inchiodatura": 6, "infilata": 0, "non_tattico": 24},
        "percentuali_tattico": {"pezzo_in_presa": 40.0, "forchetta": 30.0,
                                "inchiodatura": 6.0, "infilata": 0.1,
                                "non_tattico": 24.0},
        "tattico_per_fase": {
            "pezzo_in_presa": {"apertura": 10, "mediogioco": 25, "finale": 5},
            "forchetta": {"apertura": 5, "mediogioco": 20, "finale": 5},
            "inchiodatura": {"mediogioco": 6},
            "infilata": {},
        },
    }
    p.update(override)
    return p


def test_profilo_endpoint_arricchisce(ambiente, monkeypatch):
    """L'endpoint restituisce il profilo coi campi arricchiti, senza perdere quelli base."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    for campo in ("tasso_su_mosse_per_tipo", "ogni_quante_mosse_per_tipo",
                  "temi_rilevanti", "temi_non_rilevanti", "sintesi",
                  "fasi_divario_piccolo"):
        assert campo in r
    # I campi originali del profilo restano presenti.
    assert r["mosse_totali"] == 1000
    assert r["debolezza_principale"] == "mediogioco"


def test_profilo_assente_404(ambiente, monkeypatch):
    """Senza partite del giocatore, l'endpoint risponde 404 invece di crashare."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: None)
    r = profilo_carenze()
    assert r.status_code == 404


def test_profilo_tasso_su_mosse_totali(ambiente, monkeypatch):
    """Il tasso ha come denominatore le MOSSE TOTALI, non gli errori gravi."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    t = r["tasso_su_mosse_per_tipo"]
    # 40 pezzi in presa su 1000 mosse = 4.0% (NON 40/100 = 40%, che sarebbe sugli errori).
    assert t["pezzo_in_presa"] == 4.0
    assert t["forchetta"] == 3.0
    assert t["non_tattico"] == 2.4
    # "una ogni ~N mosse" usa lo stesso denominatore (mosse_totali / conteggio).
    assert r["ogni_quante_mosse_per_tipo"]["pezzo_in_presa"] == 25  # round(1000/40)
    assert r["ogni_quante_mosse_per_tipo"]["infilata"] is None      # conteggio 0
    assert r["tasso_su_mosse_denominatore"] == "mosse_totali"


def test_profilo_soglia_rilevanza_classifica(ambiente, monkeypatch):
    """Un tema al 6% e' rilevante; uno allo 0.1% e' rumore (non rilevante)."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    assert "inchiodatura" in r["temi_rilevanti"]      # 6% >= soglia 5%
    assert "infilata" in r["temi_non_rilevanti"]      # 0.1% < soglia
    assert "pezzo_in_presa" in r["temi_rilevanti"]
    assert "forchetta" in r["temi_rilevanti"]


def test_profilo_sintesi_onesta(ambiente, monkeypatch):
    """La sintesi cita il tema dominante e dichiara la quota non_tattico posizionale."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    s = r["sintesi"]
    assert "pezzo in presa" in s              # tema dominante (tasso piu' alto)
    assert "24.0%" in s                       # quota non_tattico dichiarata
    assert "posizional" in s.lower()          # marcata come posizionale/strategica


def test_profilo_fasi_divario_piccolo_true(ambiente, monkeypatch):
    """Tassi per fase vicini (10/10/10): fasi_divario_piccolo e' True."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    assert r["fasi_divario_piccolo"] is True
    assert r["fasi_divario"] == 0.0


def test_profilo_fasi_divario_grande_false(ambiente, monkeypatch):
    """Quando una fase spicca (forbice >= 10 punti), fasi_divario_piccolo e' False."""
    p = _profilo_finto(
        tasso_errore_per_fase={"apertura": 5.0, "mediogioco": 25.0, "finale": 8.0})
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: p)
    r = profilo_carenze()
    assert r["fasi_divario_piccolo"] is False
    assert r["fasi_divario"] == 20.0


# --- Piano di studio personalizzato (Tappa C) ---------------------------

def test_piano_studio_solo_temi_rilevanti(ambiente, monkeypatch):
    """Il piano contiene SOLO i temi rilevanti: il 6% c'e', lo 0.1% (infilata) no."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    temi = [v["tema"] for v in r["piano_studio"]["voci"]]
    assert "pezzo_in_presa" in temi
    assert "forchetta" in temi
    assert "inchiodatura" in temi          # 6% >= soglia
    assert "infilata" not in temi          # 0.1% < soglia: fuori dal piano
    assert "non_tattico" not in temi       # posizionale, mai nel piano


def test_piano_studio_pesi_relativi(ambiente, monkeypatch):
    """Il dominante ha peso_relativo 1.0 e priorita' 'alta'; gli altri frazioni corrette."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    voci = {v["tema"]: v for v in r["piano_studio"]["voci"]}
    # Dominante: tasso 4.0% -> peso 1.0, priorita' alta.
    assert voci["pezzo_in_presa"]["peso_relativo"] == 1.0
    assert voci["pezzo_in_presa"]["priorita"] == "alta"
    # forchetta: 3.0/4.0 = 0.75 -> peso 0.8, sopra 0.5 -> media.
    assert voci["forchetta"]["peso_relativo"] == 0.8
    assert voci["forchetta"]["priorita"] == "media"
    # inchiodatura: 0.6/4.0 = 0.15 -> sotto 0.5 -> bassa.
    assert voci["inchiodatura"]["priorita"] == "bassa"
    # La prima voce e' il dominante (lista ordinata dal piu' pesante).
    assert r["piano_studio"]["voci"][0]["tema"] == "pezzo_in_presa"
    # Ogni voce porta il tema-libero per agganciare il flusso temi.
    assert voci["pezzo_in_presa"]["tema_libero"] == "pezzo_in_presa"


def test_piano_studio_nota_posizionale(ambiente, monkeypatch):
    """La nota_posizionale cita la percentuale non_tattico reale (24.0%)."""
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: _profilo_finto())
    r = profilo_carenze()
    nota = r["piano_studio"]["nota_posizionale"]
    assert "24.0%" in nota
    assert "posizional" in nota.lower()


def test_piano_studio_nessun_tema_rilevante(ambiente, monkeypatch):
    """Caso limite: nessun tema sopra soglia -> piano vuoto, niente crash."""
    p = _profilo_finto(
        percentuali_tattico={"pezzo_in_presa": 2.0, "forchetta": 1.0,
                             "inchiodatura": 0.5, "infilata": 0.1,
                             "non_tattico": 96.4})
    monkeypatch.setattr(server, "costruisci_profilo", lambda *a, **k: p)
    r = profilo_carenze()
    piano = r["piano_studio"]
    assert piano["voci"] == []
    assert piano["progressione"] == ""
    assert "96.4%" in piano["nota_posizionale"]   # cita comunque la quota posizionale


# --- Snapshot nel tempo + confronto "nuove vs storico" (Tappa D) ----------
# Test di INTEGRAZIONE: usano il vero costruisci_profilo su file partita finti nella
# cartella categorie temporanea (ambiente). GIOCATORE e' il giocatore reale del server.

def _mossa_finta(gravita, tipo=None, fase="mediogioco"):
    """Una mossa minima nel formato che costruisci_profilo si aspetta."""
    return {"gravita": gravita, "fase": fase, "tipo_tattico": tipo}


def _scrivi_partite(cartella, prefisso, quante, forchetta_per_partita,
                    mosse_giocatore=10):
    """
    Scrive `quante` file partita del GIOCATORE: ogni partita ha
    `forchetta_per_partita` errori gravi di tipo 'forchetta' sulle `mosse_giocatore`
    mosse del giocatore (il resto 'best'). Le mosse dell'avversario sono 'best'.
    """
    os.makedirs(cartella, exist_ok=True)
    for k in range(quante):
        mosse = []
        for i in range(mosse_giocatore):
            if i < forchetta_per_partita:
                mosse.append(_mossa_finta("blunder", "forchetta"))
            else:
                mosse.append(_mossa_finta("best"))
            mosse.append(_mossa_finta("best"))  # mossa dell'avversario (indici dispari)
        p = {"bianco": server.GIOCATORE, "nero": "Avv", "risultato": "1-0",
             "mosse": mosse}
        with open(os.path.join(cartella, f"{prefisso}_{k:03}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(p, f)


def _leggi_storico(ambiente):
    with open(ambiente["storico_path"], "r", encoding="utf-8") as f:
        return json.load(f)


def test_tappa_d_primo_snapshot_confronto_null(ambiente):
    """Primo avvio: crea lo snapshot-base, confronto None, nessun confronto possibile."""
    _scrivi_partite(ambiente["categorie_dir"], "vecchia", 10, forchetta_per_partita=2)
    r = profilo_carenze()
    assert r["confronto"] is None
    storico = _leggi_storico(ambiente)
    assert len(storico["snapshot"]) == 1
    assert storico["ultimo_confronto"] is None


def test_tappa_d_nessun_file_nuovo_non_duplica(ambiente):
    """Senza file nuovi: nessuno snapshot duplicato e confronto invariato (None)."""
    _scrivi_partite(ambiente["categorie_dir"], "vecchia", 10, forchetta_per_partita=2)
    profilo_carenze()                       # crea la base
    r = profilo_carenze()                   # secondo giro, nulla di nuovo
    assert r["confronto"] is None
    assert len(_leggi_storico(ambiente)["snapshot"]) == 1   # niente duplicati


def test_tappa_d_anti_diluizione(ambiente):
    """
    IL TEST PIU' IMPORTANTE: il tasso_recente riflette SOLO le partite nuove, non il
    cumulativo diluito. Storico 'pessimo' su forchetta (60%), nuove 'buone' (10%):
    il confronto deve dire 10% recente (non ~35% del cumulativo) e tendenza migliorato.
    """
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)  # storico: 60%
    profilo_carenze()                                            # snapshot-base
    _scrivi_partite(cat, "nuova", 60, forchetta_per_partita=1)   # nuove: 10%
    r = profilo_carenze()

    confronto = r["confronto"]
    assert confronto is not None
    assert confronto["partite_nuove"] == 60
    assert confronto["affidabile"] is True                       # 60 >= guardrail 50
    voce_forchetta = next(v for v in confronto["voci"] if v.get("tema") == "forchetta")
    assert voce_forchetta["tasso_storico"] == 60.0
    # ANTI-DILUIZIONE: 10% (solo nuove), NON ~35% del cumulativo 420/1200.
    assert voce_forchetta["tasso_recente"] == 10.0
    assert voce_forchetta["tendenza"] == "migliorato"
    # La voce del piano e' annotata con la tendenza del confronto.
    voce_piano = next(v for v in r["piano_studio"]["voci"] if v["tema"] == "forchetta")
    assert voce_piano["tendenza"] == "migliorato"


def test_tappa_d_guardrail_poche_partite(ambiente):
    """< GUARDRAIL_PARTITE partite nuove -> affidabile False + avvertenza presente."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)
    profilo_carenze()
    _scrivi_partite(cat, "nuova", 10, forchetta_per_partita=1)   # solo 10 < 50
    r = profilo_carenze()
    assert r["confronto"]["affidabile"] is False
    assert "avvertenza" in r["confronto"]
    assert "10" in r["confronto"]["avvertenza"]


def test_tappa_d_guardrail_abbastanza_partite(ambiente):
    """>= GUARDRAIL_PARTITE partite nuove -> affidabile True, niente avvertenza."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)
    profilo_carenze()
    _scrivi_partite(cat, "nuova", 50, forchetta_per_partita=1)   # esattamente 50
    r = profilo_carenze()
    assert r["confronto"]["affidabile"] is True
    assert "avvertenza" not in r["confronto"]


def test_tappa_d_tendenza_stabile(ambiente):
    """Stesso tasso tra storico e nuove (delta < SOGLIA_STABILE) -> 'stabile'."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 50, forchetta_per_partita=3)  # 30%
    profilo_carenze()
    _scrivi_partite(cat, "nuova", 50, forchetta_per_partita=3)    # 30%, delta 0
    r = profilo_carenze()
    voce = next(v for v in r["confronto"]["voci"] if v.get("tema") == "forchetta")
    assert voce["delta"] == 0.0
    assert voce["tendenza"] == "stabile"


def test_tappa_d_tendenza_peggiorato(ambiente):
    """Tasso in salita oltre la soglia -> 'peggiorato'."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 50, forchetta_per_partita=1)  # 10%
    profilo_carenze()
    _scrivi_partite(cat, "nuova", 50, forchetta_per_partita=5)    # 50%
    r = profilo_carenze()
    voce = next(v for v in r["confronto"]["voci"] if v.get("tema") == "forchetta")
    assert voce["tendenza"] == "peggiorato"
    assert voce["delta"] > 0


# --- Grafico storico dell'evoluzione: tassi DEL PERIODO (raffinamento punto 4) ---
# Lo snapshot del periodo salva i tassi delle SOLE partite nuove (anti-diluizione);
# /storico-profili li espone come serie temporale, saltando lo snapshot base.

def test_snapshot_periodo_salva_campi_periodo(ambiente):
    """Con partite nuove, lo snapshot porta i campi periodo_* dalle sole nuove."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)
    profilo_carenze()                                           # snapshot-base
    _scrivi_partite(cat, "nuova", 60, forchetta_per_partita=1)  # 60 partite nuove
    profilo_carenze()
    snap = _leggi_storico(ambiente)["snapshot"][-1]             # lo snapshot-periodo
    assert snap["periodo_partite"] == 60
    assert snap["periodo_affidabile"] is True                   # 60 >= guardrail 50
    assert "periodo_tasso_su_mosse_per_tipo" in snap
    assert "periodo_tasso_errore_per_fase" in snap


def test_snapshot_base_non_ha_campi_periodo(ambiente):
    """Lo snapshot base (primo) NON rappresenta un periodo: niente campi periodo_*."""
    _scrivi_partite(ambiente["categorie_dir"], "vecchia", 10, forchetta_per_partita=2)
    profilo_carenze()
    base = _leggi_storico(ambiente)["snapshot"][0]
    assert "periodo_partite" not in base
    assert "periodo_tasso_su_mosse_per_tipo" not in base
    assert "periodo_tasso_errore_per_fase" not in base
    assert "periodo_affidabile" not in base


def test_storico_profili_solo_base_ha_dati_false(ambiente):
    """Con il solo snapshot base, niente punti-periodo: ha_dati False, punti vuoti."""
    _scrivi_partite(ambiente["categorie_dir"], "vecchia", 10, forchetta_per_partita=2)
    profilo_carenze()
    r = storico_profili()
    assert r["ha_dati"] is False
    assert r["punti"] == []


def test_storico_profili_salta_base_e_segnala_dati(ambiente):
    """Con >=1 periodo: /storico-profili salta il base e ha_dati True (1 solo punto)."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)
    profilo_carenze()                                           # base
    _scrivi_partite(cat, "nuova", 60, forchetta_per_partita=1)
    profilo_carenze()                                           # periodo 1
    r = storico_profili()
    assert r["ha_dati"] is True
    assert len(r["punti"]) == 1                                 # il base e' saltato
    assert r["punti"][0]["periodo_partite"] == 60


def test_storico_profili_punti_sono_del_periodo_non_cumulativi(ambiente):
    """
    TEST ANTI-DILUIZIONE DEL GRAFICO: i punti riflettono il tasso DEL PERIODO (sole
    partite nuove), non il cumulativo diluito. Storico 60% su forchetta, nuove 10%:
    il punto deve valere 10 (non ~35% del cumulativo).
    """
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)  # storico 60%
    profilo_carenze()
    _scrivi_partite(cat, "nuova", 60, forchetta_per_partita=1)    # periodo 10%
    profilo_carenze()
    r = storico_profili()
    punto = r["punti"][0]
    assert punto["tasso_tipo"]["forchetta"] == 10.0              # periodo, non ~35%


def test_storico_profili_due_periodi_ordinati(ambiente):
    """Due periodi nuovi -> due punti, in ordine temporale, ciascuno coi propri tassi."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)
    profilo_carenze()                                            # base
    _scrivi_partite(cat, "primo", 60, forchetta_per_partita=5)   # periodo 1: 50%
    profilo_carenze()
    _scrivi_partite(cat, "secondo", 60, forchetta_per_partita=1)  # periodo 2: 10%
    profilo_carenze()
    r = storico_profili()
    assert len(r["punti"]) == 2
    assert r["punti"][0]["tasso_tipo"]["forchetta"] == 50.0
    assert r["punti"][1]["tasso_tipo"]["forchetta"] == 10.0
    timestamps = [p["timestamp"] for p in r["punti"]]
    assert timestamps == sorted(timestamps)


def test_storico_profili_periodo_poche_partite_non_affidabile(ambiente):
    """Periodo con poche partite (< guardrail) -> punto marcato affidabile False."""
    cat = ambiente["categorie_dir"]
    _scrivi_partite(cat, "vecchia", 60, forchetta_per_partita=6)
    profilo_carenze()
    _scrivi_partite(cat, "nuova", 10, forchetta_per_partita=1)   # solo 10 < 50
    profilo_carenze()
    r = storico_profili()
    assert r["punti"][0]["affidabile"] is False
