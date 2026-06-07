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
import sqlite3
import tempfile
import pytest

import server
from server import (
    Esito, registra_esito, statistiche, statistiche_temi, lista_temi,
    scegli_tema, prossimo_puzzle, progressi, lista_flussi, imposta_flusso,
    _salva_stato, _carica_stato, _valuta_adattivita,
    _crea_snapshot, _calcola_tendenza, _riepilogo_progressi, _riepilogo_complessivo,
)


def _stato_pulito():
    """Riporta _sessione ai valori di default, come a backend appena avviato."""
    server._sessione.update({
        "pronta": True,  # evita che statistiche()/endpoint costruiscano un piano vero
        "flusso_attivo": "piano",
        "visti": set(),
        "flussi": {nome: server._nuovo_flusso() for nome in server.FLUSSI},
    })


def _flussi():
    return server._sessione["flussi"]


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
    assert r["flussi"]["errori"]["implementato"] is False
    assert "complessivo" in r


def test_imposta_flusso_cambia_attivo(ambiente):
    r = imposta_flusso("temi")
    assert server._sessione["flusso_attivo"] == "temi"
    assert r["flusso_attivo"] == "temi"


def test_imposta_flusso_errori_non_implementato(ambiente):
    """Il flusso 'errori' e' predisposto ma non attivabile: 501, attivo invariato."""
    r = imposta_flusso("errori")
    assert r.status_code == 501
    assert server._sessione["flusso_attivo"] == "piano"


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
