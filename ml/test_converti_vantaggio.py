"""
Test del modulo converti_vantaggio (misurazione della conversione del vantaggio).

Non richiede Stockfish: usa file di analisi finti, costruiti ad arte, in cartella
temporanea, puliti alla fine.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json
import shutil
import tempfile
import pytest
import converti_vantaggio
from converti_vantaggio import (
    mio_colore,
    turno_da_fen,
    cap_mate,
    eval_dal_mio_punto_di_vista,
    risultato_dal_mio_punto_di_vista,
    costruisci_timeline,
    picco_vantaggio,
    classifica_perdita,
    analizza_partite,
    diagnosi_conversione,
    _stampa_tabella,
    SOGLIA_MATTO,
    CAP_MATTO,
    PICCO_MIN_CONVERSIONE,
    PICCO_MAX_CONVERSIONE,
)

# FEN di comodo: tocca al Bianco e tocca al Nero (serve solo il 2o token).
FEN_BIANCO = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_NERO = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _m(fen, eval_prima, eval_dopo, cpl):
    """Costruisce una mossa finta nel formato dei file di analisi."""
    return {"fen": fen, "move_uci": "d2d4", "san": "d4", "best_move_uci": "e2e4",
            "eval_prima": eval_prima, "eval_dopo": eval_dopo, "centipawn_loss": cpl}


# --- Normalizzazione eval per colore ---

def test_eval_dal_mio_punto_di_vista():
    # Da Bianco resta uguale, da Nero si inverte di segno.
    assert eval_dal_mio_punto_di_vista(300, True) == 300
    assert eval_dal_mio_punto_di_vista(300, False) == -300


def test_timeline_inverte_eval_per_il_nero():
    # Giocando Nero, un eval +250 (vista Bianco) e' -250 dal mio lato.
    dato = {"mosse": [_m(FEN_NERO, 250, 250, 0)]}
    timeline = costruisci_timeline(dato, "b")
    assert timeline[0]["eval_prima_mia"] == -250
    assert timeline[0]["mia"] is True   # turno nero == mio colore


# --- Cap dei mate-score fasulli ---

def test_cap_mate():
    assert cap_mate(300) == 300            # eval normale invariato
    assert cap_mate(SOGLIA_MATTO) == CAP_MATTO
    assert cap_mate(-SOGLIA_MATTO - 5) == -CAP_MATTO


# --- Risultato dal mio punto di vista ---

def test_risultato_patta():
    assert risultato_dal_mio_punto_di_vista("1/2-1/2", True) == "patta"
    assert risultato_dal_mio_punto_di_vista("1/2-1/2", False) == "patta"


def test_risultato_dal_mio_lato_bianco_e_nero():
    # 1-0: vince il Bianco.
    assert risultato_dal_mio_punto_di_vista("1-0", True) == "vittoria"
    assert risultato_dal_mio_punto_di_vista("1-0", False) == "sconfitta"
    # 0-1: vince il Nero.
    assert risultato_dal_mio_punto_di_vista("0-1", True) == "sconfitta"
    assert risultato_dal_mio_punto_di_vista("0-1", False) == "vittoria"


def test_risultato_illeggibile():
    assert risultato_dal_mio_punto_di_vista("*", True) is None
    assert risultato_dal_mio_punto_di_vista(None, True) is None


# --- Calcolo del picco ---

def test_picco_vantaggio_bianco():
    dato = {"mosse": [
        _m(FEN_BIANCO, 50, 120, 0),
        _m(FEN_NERO, 120, 300, 0),    # picco a 300
        _m(FEN_BIANCO, 300, 80, 220),
    ]}
    assert picco_vantaggio(costruisci_timeline(dato, "w")) == 300


def test_picco_con_mate_score_viene_tagliato():
    # Un mate-score fasullo non deve falsare il picco: viene tagliato a CAP_MATTO.
    dato = {"mosse": [_m(FEN_BIANCO, 200, SOGLIA_MATTO, 0)]}
    assert picco_vantaggio(costruisci_timeline(dato, "w")) == CAP_MATTO


def test_picco_timeline_vuota():
    assert picco_vantaggio([]) is None


# --- Classificazione crollo vs erosione (sequenze costruite ad arte) ---

def test_classifica_crollo():
    # Gioco Bianco: ero a +400, una mia mossa con cpl 350 crolla a +50 (< 200).
    dato = {"mosse": [
        _m(FEN_BIANCO, 250, 400, 0),    # mia, salgo
        _m(FEN_NERO, 400, 400, 0),      # avversario, neutro
        _m(FEN_BIANCO, 400, 50, 350),   # mia, CROLLO: da >=200 a <200 con cpl 350
    ]}
    timeline = costruisci_timeline(dato, "w")
    assert classifica_perdita(timeline, soglia=200) == "crollo"


def test_classifica_erosione_tante_imprecisioni_piccole():
    # Gioco Bianco: il vantaggio scende sotto 200 a piccoli passi, nessuna mia
    # mossa raggiunge cpl 300 -> erosione.
    dato = {"mosse": [
        _m(FEN_BIANCO, 350, 300, 50),   # mia, cpl 50
        _m(FEN_NERO, 300, 290, 10),     # avversario gioca bene
        _m(FEN_BIANCO, 290, 210, 80),   # mia, cpl 80
        _m(FEN_NERO, 210, 200, 10),     # avversario
        _m(FEN_BIANCO, 200, 120, 80),   # mia, cpl 80: scende sotto 200 ma piano
    ]}
    timeline = costruisci_timeline(dato, "w")
    assert classifica_perdita(timeline, soglia=200) == "erosione"


def test_classifica_crollo_grosso_ma_resta_sopra_soglia_e_erosione():
    # Mossa con cpl alto ma che NON scende sotto soglia (da +800 a +250): non e'
    # crollo a soglia 200; il calo finale sotto soglia avviene per erosione.
    dato = {"mosse": [
        _m(FEN_BIANCO, 800, 250, 550),  # mia, cpl 550 ma resta >= 200
        _m(FEN_NERO, 250, 230, 20),
        _m(FEN_BIANCO, 230, 150, 80),   # mia, scende sotto 200 con cpl piccolo
    ]}
    timeline = costruisci_timeline(dato, "w")
    assert classifica_perdita(timeline, soglia=200) == "erosione"


# --- Conteggio per soglia su file finti ---

@pytest.fixture
def cartella():
    c = tempfile.mkdtemp()

    # Partita 1: Bianco, picco +320, NON convertita (patta), per CROLLO.
    p1 = {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "1/2-1/2", "mosse": [
        _m(FEN_BIANCO, 100, 320, 0),    # picco 320
        _m(FEN_NERO, 320, 320, 0),
        _m(FEN_BIANCO, 320, 40, 280),   # mia: ma cpl < 300 -> non crollo
        _m(FEN_BIANCO, 320, 30, 300),   # mia: cpl 300, scende sotto 200 -> crollo
    ]}
    with open(os.path.join(c, "rapid_0001.json"), "w", encoding="utf-8") as f:
        json.dump(p1, f)

    # Partita 2: Nero, picco +250 (eval vista Bianco = -250), NON convertita
    # (sconfitta: 1-0 da Nero), per EROSIONE (nessuna mia mossa cpl >= 300).
    p2 = {"bianco": "Avv", "nero": "MigueL_uz", "risultato": "1-0", "mosse": [
        _m(FEN_NERO, -250, -210, 40),   # mia (turno nero): eval_mia da +250 a +210
        _m(FEN_BIANCO, -210, -150, 60), # avversario
        _m(FEN_NERO, -150, -100, 50),   # mia: eval_mia +150 -> +100 (sotto 200)
    ]}
    with open(os.path.join(c, "rapid_0002.json"), "w", encoding="utf-8") as f:
        json.dump(p2, f)

    # Partita 3: Bianco, picco +500, CONVERTITA (vittoria) -> non e' non-conversione.
    p3 = {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "1-0", "mosse": [
        _m(FEN_BIANCO, 200, 500, 0),
        _m(FEN_NERO, 500, 500, 0),
    ]}
    with open(os.path.join(c, "rapid_0003.json"), "w", encoding="utf-8") as f:
        json.dump(p3, f)

    # Partita 4: Bianco, picco +160 (sotto 200), NON convertita (sconfitta).
    p4 = {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "0-1", "mosse": [
        _m(FEN_BIANCO, 100, 160, 0),
        _m(FEN_BIANCO, 160, -300, 460),
    ]}
    with open(os.path.join(c, "rapid_0004.json"), "w", encoding="utf-8") as f:
        json.dump(p4, f)

    # Partita 5: non la gioco io -> deve essere saltata.
    p5 = {"bianco": "Tizio", "nero": "Caio", "risultato": "1-0",
          "mosse": [_m(FEN_BIANCO, 0, 0, 0)]}
    with open(os.path.join(c, "rapid_0005.json"), "w", encoding="utf-8") as f:
        json.dump(p5, f)

    yield c
    shutil.rmtree(c)


def test_analizza_conteggi_e_saltati(cartella):
    rie = analizza_partite(cartella)
    # 4 partite mie misurabili, 1 saltata (non gioco io).
    assert rie["n_partite_analizzate"] == 4
    assert rie["n_file_saltati"] == 1


def test_analizza_per_soglia(cartella):
    rie = analizza_partite(cartella)
    s = rie["soglie"]
    # Picchi: P1=320, P2=250, P3=500, P4=160.
    # >=150: tutte e 4 (320,250,500,160). Non convertite: P1,P2,P4 = 3.
    assert s[150] == {"con_vantaggio": 4, "non_convertite": 3}
    # >=200: P1,P2,P3 (160 esclusa). Non convertite: P1,P2 = 2.
    assert s[200] == {"con_vantaggio": 3, "non_convertite": 2}
    # >=300: P1(320),P3(500). Non convertite: solo P1 = 1.
    assert s[300] == {"con_vantaggio": 2, "non_convertite": 1}


def test_analizza_ripartizione_crollo_erosione(cartella):
    rie = analizza_partite(cartella)
    # Alla soglia 200 le non-conversioni sono P1 (crollo) e P2 (erosione).
    assert rie["ripartizione_dettaglio"] == {"crollo": 1, "erosione": 1}


def test_analizza_cartella_vuota():
    c = tempfile.mkdtemp()
    try:
        rie = analizza_partite(c)
        assert rie["n_partite_analizzate"] == 0
    finally:
        shutil.rmtree(c)


# --- Diagnosi consultabile (diagnosi_conversione, punto 5) ---

def test_diagnosi_campi(cartella):
    d = diagnosi_conversione(soglia=200, cartella=cartella)
    for campo in ("soglia", "picco_min", "picco_max",
                  "partite_con_vantaggio", "non_convertite",
                  "tasso_non_conversione", "crollo", "erosione",
                  "erosioni_sopra_tetto_escluse",
                  "partite_erosione", "affidabile",
                  "partite_bullet_escluse", "escludi_bullet"):
        assert campo in d
    assert d["soglia"] == 200
    # Intervallo tecnico del tetto al picco esposto nel dict.
    assert d["picco_min"] == PICCO_MIN_CONVERSIONE == 200
    assert d["picco_max"] == PICCO_MAX_CONVERSIONE == 600
    # Il fixture non ha picchi sopra il tetto (320, 250, 500): nessuna esclusione.
    assert d["erosioni_sopra_tetto_escluse"] == 0
    # Il fixture non ha file bullet: nessuna esclusione, ma il flag e' attivo.
    assert d["escludi_bullet"] is True
    assert d["partite_bullet_escluse"] == 0
    # crollo/erosione sono sottodizionari {n, perc}.
    for sotto in ("crollo", "erosione"):
        assert set(d[sotto].keys()) == {"n", "perc"}
    # Coerenza coi conteggi del fixture (P1 crollo, P2 erosione a soglia 200).
    assert d["partite_con_vantaggio"] == 3   # P1, P2, P3 (P4 sotto 200)
    assert d["non_convertite"] == 2          # P1, P2 (P3 e' vittoria)
    assert d["crollo"]["n"] == 1
    assert d["erosione"]["n"] == 1


def test_diagnosi_partite_erosione_solo_erosioni(cartella):
    d = diagnosi_conversione(soglia=200, cartella=cartella)
    # Solo P2 e' erosione: i crolli (P1) NON devono comparire nella lista.
    file_erosione = [p["fonte_file"] for p in d["partite_erosione"]]
    assert file_erosione == ["rapid_0002.json"]
    voce = d["partite_erosione"][0]
    assert voce["risultato"] == "sconfitta"
    assert voce["picco_vantaggio"] == 250    # eval mia max (Nero: -250 -> +250)


def test_diagnosi_erosioni_ordinate_per_picco_decrescente():
    # Due erosioni con picchi diversi: devono uscire dalla piu' grossa alla piu' piccola.
    c = tempfile.mkdtemp()
    try:
        # Erosione picco +600 (cala piano sotto 200, nessuna mia mossa cpl>=300).
        grossa = {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "1/2-1/2", "mosse": [
            _m(FEN_BIANCO, 500, 600, 100),
            _m(FEN_BIANCO, 600, 150, 80),
        ]}
        # Erosione picco +250.
        piccola = {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "1/2-1/2", "mosse": [
            _m(FEN_BIANCO, 200, 250, 50),
            _m(FEN_BIANCO, 250, 120, 80),
        ]}
        with open(os.path.join(c, "a_piccola.json"), "w", encoding="utf-8") as f:
            json.dump(piccola, f)
        with open(os.path.join(c, "z_grossa.json"), "w", encoding="utf-8") as f:
            json.dump(grossa, f)
        d = diagnosi_conversione(soglia=200, cartella=c)
        picchi = [p["picco_vantaggio"] for p in d["partite_erosione"]]
        assert picchi == [600, 250]   # decrescente, non per nome file
    finally:
        shutil.rmtree(c)


# --- Tetto al picco: erosioni da vantaggi stratosferici escluse dalla diagnosi ---

def _erosione_con_picco(picco):
    """
    Partita mia (Bianco) NON convertita (patta) per EROSIONE, con il picco indicato.
    Salgo al picco e poi scendo sotto 200 a piccoli passi (nessuna mia mossa cpl>=300),
    cosi' classifica_perdita la marca "erosione" qualunque sia il picco.
    """
    return {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "1/2-1/2", "mosse": [
        _m(FEN_BIANCO, 200, picco, 50),     # mia: salgo al picco (cpl 50)
        _m(FEN_NERO, picco, 250, 0),        # avversario: riduce (non mia)
        _m(FEN_BIANCO, 250, 150, 80),       # mia: scendo sotto 200 piano (cpl 80)
    ]}


def test_diagnosi_tetto_al_picco_conta_solo_intervallo():
    # Erosioni a picchi +250, +400 (in [200,600]) e +900, +1300 (sopra il tetto):
    # solo le prime due devono essere contate; le altre due escluse dal tetto.
    c = tempfile.mkdtemp()
    try:
        picchi = {"a_250": 250, "b_400": 400, "c_900": 900, "d_1300": 1300}
        for nome, picco in picchi.items():
            with open(os.path.join(c, f"rapid_{nome}.json"), "w", encoding="utf-8") as f:
                json.dump(_erosione_con_picco(picco), f)

        d = diagnosi_conversione(soglia=200, cartella=c)
        # Solo +250 e +400 cadono in [200,600]: contate.
        assert d["partite_con_vantaggio"] == 2
        assert d["non_convertite"] == 2
        assert d["erosione"]["n"] == 2
        # +900 e +1300 sono sopra il tetto: due erosioni escluse, riportate a parte.
        assert d["erosioni_sopra_tetto_escluse"] == 2
        # In lista compaiono solo le erosioni dentro l'intervallo, picco decrescente.
        picchi_lista = [p["picco_vantaggio"] for p in d["partite_erosione"]]
        assert picchi_lista == [400, 250]
    finally:
        shutil.rmtree(c)


def test_diagnosi_tetto_picco_al_limite_incluso():
    # Picco esattamente al tetto (+600 = PICCO_MAX_CONVERSIONE) deve essere INCLUSO.
    c = tempfile.mkdtemp()
    try:
        with open(os.path.join(c, "rapid_limite.json"), "w", encoding="utf-8") as f:
            json.dump(_erosione_con_picco(PICCO_MAX_CONVERSIONE), f)
        d = diagnosi_conversione(soglia=200, cartella=c)
        assert d["partite_con_vantaggio"] == 1
        assert d["erosione"]["n"] == 1
        assert d["erosioni_sopra_tetto_escluse"] == 0
    finally:
        shutil.rmtree(c)


def test_analizza_senza_picco_max_non_applica_tetto():
    # Senza picco_max (default), il tetto NON si applica: l'erosione +900 e' contata.
    c = tempfile.mkdtemp()
    try:
        with open(os.path.join(c, "rapid_900.json"), "w", encoding="utf-8") as f:
            json.dump(_erosione_con_picco(900), f)
        rie = analizza_partite(c)   # picco_max=None
        assert rie["soglie"][200]["con_vantaggio"] == 1
        assert rie["ripartizione_dettaglio"]["erosione"] == 1
        assert rie["erosioni_sopra_tetto_escluse"] == 0
    finally:
        shutil.rmtree(c)


def test_diagnosi_affidabile_false_su_poche_erosioni(cartella):
    # Una sola erosione nel fixture: sotto SOGLIA_AFFIDABILITA -> non affidabile.
    d = diagnosi_conversione(soglia=200, cartella=cartella)
    assert d["erosione"]["n"] == 1
    assert d["affidabile"] is False


def test_diagnosi_affidabile_true_quando_supera_soglia(cartella, monkeypatch):
    # Abbasso la soglia di significativita' a 1: la singola erosione basta.
    monkeypatch.setattr(converti_vantaggio, "SOGLIA_AFFIDABILITA", 1)
    d = diagnosi_conversione(soglia=200, cartella=cartella)
    assert d["affidabile"] is True


# --- La modalita' CLI di stampa resta funzionante ---

def test_stampa_tabella_non_crasha(cartella, capsys):
    rie = analizza_partite(cartella)
    _stampa_tabella(rie)   # deve stampare senza sollevare eccezioni
    out = capsys.readouterr().out
    assert "Conversione del vantaggio" in out
    assert "crollo" in out and "erosione" in out
    # La tabella mostra anche quante partite bullet sono state escluse.
    assert "bullet escluse" in out


# --- Esclusione delle partite bullet ---

def _cartella_mista():
    """
    Crea una cartella con due NON-conversioni a soglia 200, una in bullet e una no.
    Entrambe sono erosioni (nessuna mia mossa cpl>=300), io Bianco, picco +300.
    """
    c = tempfile.mkdtemp()
    partita = {"bianco": "MigueL_uz", "nero": "Avv", "risultato": "1/2-1/2", "mosse": [
        _m(FEN_BIANCO, 200, 300, 50),   # mia, salgo a +300
        _m(FEN_BIANCO, 300, 120, 80),   # mia, scendo sotto 200 piano (cpl 80)
    ]}
    # Stesso contenuto, ma un file e' bullet (dal NOME) e l'altro no.
    with open(os.path.join(c, "bullet_0001.json"), "w", encoding="utf-8") as f:
        json.dump(partita, f)
    with open(os.path.join(c, "rapid_0001.json"), "w", encoding="utf-8") as f:
        json.dump(partita, f)
    return c


def test_bullet_escluso_dai_conteggi_di_default():
    c = _cartella_mista()
    try:
        rie = analizza_partite(c)   # escludi_bullet=True di default
        # Solo la rapid e' contata; la bullet e' saltata prima di ogni conteggio.
        assert rie["n_partite_analizzate"] == 1
        assert rie["partite_bullet_escluse"] == 1
        assert rie["soglie"][200]["con_vantaggio"] == 1
        # L'unica erosione in lista viene dal file NON bullet.
        assert [p["fonte_file"] for p in rie["partite_erosione"]] == ["rapid_0001.json"]
    finally:
        shutil.rmtree(c)


def test_escludi_bullet_false_ripristina_comportamento_vecchio():
    c = _cartella_mista()
    try:
        rie = analizza_partite(c, escludi_bullet=False)
        # Ora contano entrambe (bullet + rapid).
        assert rie["n_partite_analizzate"] == 2
        assert rie["partite_bullet_escluse"] == 0
        assert rie["soglie"][200]["con_vantaggio"] == 2
    finally:
        shutil.rmtree(c)


def test_diagnosi_bullet_escluse_riportate():
    c = _cartella_mista()
    try:
        d = diagnosi_conversione(soglia=200, cartella=c)
        assert d["escludi_bullet"] is True
        assert d["partite_bullet_escluse"] == 1
        assert d["partite_con_vantaggio"] == 1   # solo la rapid
        # Con escludi_bullet=False si misura tutto.
        d2 = diagnosi_conversione(soglia=200, cartella=c, escludi_bullet=False)
        assert d2["escludi_bullet"] is False
        assert d2["partite_bullet_escluse"] == 0
        assert d2["partite_con_vantaggio"] == 2
    finally:
        shutil.rmtree(c)


def test_e_bullet_dal_nome():
    from converti_vantaggio import e_bullet
    assert e_bullet("bullet_0001.json") is True
    assert e_bullet("/percorso/Bullet_99.json") is True   # case-insensitive
    assert e_bullet("rapid_0001.json") is False
    assert e_bullet("mie_partite_12.json") is False
