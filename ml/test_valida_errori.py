"""
Test del modulo valida_errori (validazione candidati-puzzle con Stockfish).

NON apre Stockfish davvero (troppo lento e non disponibile in CI): testa le
funzioni pure isolabili e simula l'output di Stockfish costruendo a mano gli
oggetti score/PV di python-chess (chess.engine.Cp/Mate/PovScore) e linee
MultiPV finte, come si fa con i fake in api/test_server.py.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os

import chess
import chess.engine

import valida_errori
from valida_errori import (
    turno_da_fen,
    eval_lato_mossa,
    estrai_linea,
    calcola_gap,
    valuta_multipv,
    filtra_non_bullet,
    seleziona_campione,
    seleziona_batch,
    tieni_puzzle,
    costruisci_puzzle,
    chiave_candidato,
    filtra_da_processare,
    componi_stato,
    carica_progresso,
    valida_batch,
    tasso_sopravvivenza,
    stima_tempo_totale,
    formatta_durata,
    SOGLIA_MATTO,
    GAP_MATTO,
)

FEN_BIANCO = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_NERO = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def _linea(cp_o_mate, uci, turno):
    """
    Costruisce una linea MultiPV finta come quelle di chess.engine.analyse:
    {"score": PovScore relativo a chi muove, "pv": [Move, ...]}.
    `cp_o_mate` e' un Cp(...) o Mate(...) dal punto di vista di chi muove.
    """
    colore = chess.WHITE if turno == "w" else chess.BLACK
    return {
        "score": chess.engine.PovScore(cp_o_mate, colore),
        "pv": [chess.Move.from_uci(uci)],
    }


# --- Turno dal FEN -------------------------------------------------------

def test_turno_da_fen():
    assert turno_da_fen(FEN_BIANCO) == "w"
    assert turno_da_fen(FEN_NERO) == "b"


# --- Punto di vista di chi muove -----------------------------------------

def test_eval_lato_mossa_bianco_invariato():
    assert eval_lato_mossa(300, "w") == 300


def test_eval_lato_mossa_nero_invertito():
    # +300 vista Bianco = -300 per il Nero che muove (e viceversa).
    assert eval_lato_mossa(300, "b") == -300
    assert eval_lato_mossa(-150, "b") == 150


# --- Estrazione di una linea (con fake score) ----------------------------

def test_estrai_linea_centipawn_bianco():
    info = _linea(chess.engine.Cp(80), "e2e4", "w")
    eval_bianco, matto, mossa = estrai_linea(info)
    assert eval_bianco == 80
    assert matto is False
    assert mossa == "e2e4"


def test_estrai_linea_centipawn_nero_riportato_a_bianco():
    # Cp(+50) per il Nero che muove diventa -50 vista Bianco.
    info = _linea(chess.engine.Cp(50), "e7e5", "b")
    eval_bianco, matto, _ = estrai_linea(info)
    assert eval_bianco == -50
    assert matto is False


def test_estrai_linea_matto_positivo():
    info = _linea(chess.engine.Mate(2), "d8h4", "w")
    eval_bianco, matto, _ = estrai_linea(info)
    assert matto is True
    assert eval_bianco == SOGLIA_MATTO


def test_estrai_linea_matto_subito():
    # Mate(-1) per chi muove = sta per essere mattato.
    info = _linea(chess.engine.Mate(-1), "a1a2", "w")
    eval_bianco, matto, _ = estrai_linea(info)
    assert matto is True
    assert eval_bianco == -SOGLIA_MATTO


# --- Calcolo del gap -----------------------------------------------------

def test_calcola_gap_normale():
    assert calcola_gap(300, 120) == 180


def test_calcola_gap_mai_negativo():
    # Per sicurezza non scende sotto zero anche con input incoerenti.
    assert calcola_gap(100, 150) == 0


def test_calcola_gap_matto_e_infinito():
    # Una 1a mossa di matto a favore di chi muove passa qualsiasi soglia.
    assert calcola_gap(SOGLIA_MATTO, 200) == GAP_MATTO
    assert calcola_gap(SOGLIA_MATTO + 5, -10) == GAP_MATTO


# --- valuta_multipv: integrazione delle funzioni pure --------------------

def _candidato(fen=FEN_BIANCO, soluzione="e2e4", cadenza="rapid"):
    return {"fen": fen, "soluzione_uci": soluzione, "cadenza": cadenza}


def test_valuta_multipv_gap_dal_lato_giusto_bianco():
    info = [_linea(chess.engine.Cp(250), "e2e4", "w"),
            _linea(chess.engine.Cp(40), "d2d4", "w")]
    r = valuta_multipv(info, "w", _candidato(soluzione="e2e4"))
    assert r["soluzione_validata_uci"] == "e2e4"
    assert r["gap"] == 210
    assert r["matto"] is False
    assert r["soluzione_cambiata"] is False


def test_valuta_multipv_gap_dal_lato_giusto_nero():
    # Tocca al Nero: gli score sono relativi a lui, il gap va calcolato sul Nero.
    info = [_linea(chess.engine.Cp(300), "d8h4", "b"),
            _linea(chess.engine.Cp(90), "g8f6", "b")]
    r = valuta_multipv(info, "b", _candidato(fen=FEN_NERO, soluzione="d8h4"))
    assert r["gap"] == 210
    assert r["matto"] is False


def test_valuta_multipv_segnala_soluzione_cambiata():
    info = [_linea(chess.engine.Cp(250), "e2e4", "w"),
            _linea(chess.engine.Cp(40), "d2d4", "w")]
    r = valuta_multipv(info, "w", _candidato(soluzione="g1f3"))
    assert r["soluzione_validata_uci"] == "e2e4"
    assert r["soluzione_cambiata"] is True


def test_valuta_multipv_matto_sempre_valido():
    info = [_linea(chess.engine.Mate(1), "d1h5", "w"),
            _linea(chess.engine.Cp(120), "f1c4", "w")]
    r = valuta_multipv(info, "w", _candidato(soluzione="d1h5"))
    assert r["matto"] is True
    assert r["gap"] == GAP_MATTO


def test_valuta_multipv_unica_mossa_gap_infinito():
    # Una sola linea (mossa forzata): nessuna alternativa -> unicita' garantita.
    info = [_linea(chess.engine.Cp(60), "e2e4", "w")]
    r = valuta_multipv(info, "w", _candidato(soluzione="e2e4"))
    assert r["gap"] == GAP_MATTO


# --- Filtro bullet -------------------------------------------------------

def test_filtra_non_bullet_esclude_i_bullet():
    cands = [{"cadenza": "bullet"}, {"cadenza": "rapid"},
             {"cadenza": "blitz"}, {"cadenza": "bullet"}]
    rimasti = filtra_non_bullet(cands)
    assert len(rimasti) == 2
    assert all(c["cadenza"] != "bullet" for c in rimasti)


# --- Logica del campione con seed ----------------------------------------

def _cands(n):
    """n candidati alternati bullet/altro, con id progressivo per riconoscerli."""
    return [{"id": i, "cadenza": "bullet" if i % 2 == 0 else "rapid"}
            for i in range(n)]


def test_campione_esclude_bullet_e_rispetta_n():
    campione, totale = seleziona_campione(_cands(40), 5)
    assert len(campione) == 5
    assert totale == 20  # i dispari, cioe' i non-bullet
    assert all(c["cadenza"] != "bullet" for c in campione)


def test_campione_deterministico_con_seed():
    a, _ = seleziona_campione(_cands(40), 8)
    b, _ = seleziona_campione(_cands(40), 8)
    assert [c["id"] for c in a] == [c["id"] for c in b]


def test_campione_e_mescolato_non_primi_in_ordine():
    # Mescolando con seed fisso l'ordine NON e' quello del file.
    non_bullet = [c for c in _cands(60) if c["cadenza"] != "bullet"]
    campione, _ = seleziona_campione(_cands(60), 30)
    assert [c["id"] for c in campione] != [c["id"] for c in non_bullet[:30]]


# --- Tasso di sopravvivenza ----------------------------------------------

def test_tasso_sopravvivenza_conta_per_soglia():
    gap = [80, 100, 150, 199, 200, GAP_MATTO]
    s = tasso_sopravvivenza(gap, soglie=[100, 150, 200])
    assert s[100] == 5   # 100,150,199,200,inf
    assert s[150] == 4   # 150,199,200,inf
    assert s[200] == 2   # 200,inf


def test_tasso_sopravvivenza_lista_vuota():
    assert tasso_sopravvivenza([], soglie=[100, 200]) == {100: 0, 200: 0}


# --- Stima e formattazione del tempo -------------------------------------

def test_stima_tempo_totale():
    assert stima_tempo_totale(2.0, 1500) == 3000.0


def test_formatta_durata():
    assert formatta_durata(45) == "45s"
    assert formatta_durata(90) == "1m 30s"
    assert formatta_durata(3725) == "1h 2m"


# =========================================================================
# BATCH (tappa 2b): tenere/scartare, formato del puzzle, ripartenza, --batch
# =========================================================================

# --- "tieni se gap>=soglia o matto" --------------------------------------

def _risultato(gap, matto=False, soluzione="e2e4", cambiata=False):
    """Risultato di valuta_multipv ridotto ai campi che servono al batch."""
    return {
        "fen": FEN_BIANCO,
        "soluzione_validata_uci": soluzione,
        "soluzione_cambiata": cambiata,
        "gap": gap,
        "matto": matto,
    }


def test_tieni_puzzle_gap_sopra_soglia():
    assert tieni_puzzle(_risultato(gap=250), soglia=200) is True


def test_tieni_puzzle_gap_uguale_soglia():
    # La soglia e' inclusiva (>=): un gap esattamente pari va tenuto.
    assert tieni_puzzle(_risultato(gap=200), soglia=200) is True


def test_tieni_puzzle_gap_sotto_soglia_scartato():
    assert tieni_puzzle(_risultato(gap=199), soglia=200) is False


def test_tieni_puzzle_matto_sempre_tenuto():
    # Un matto passa anche con gap nominale sotto soglia.
    assert tieni_puzzle(_risultato(gap=0, matto=True), soglia=200) is True


# --- Formato del puzzle salvato ------------------------------------------

def _candidato_completo():
    return {
        "fen": FEN_BIANCO,
        "mossa_giocata_uci": "c1e3",
        "soluzione_uci": "h8g8",           # vecchia best move (NON va salvata)
        "san_giocata": "Be3",
        "centipawn_loss": 329,
        "eval_mia_prima": 383,
        "fonte_file": "rapid_0007.json",
        "indice_mossa": 12,
        "cadenza": "rapid",
    }


def test_costruisci_puzzle_formato_e_campi():
    cand = _candidato_completo()
    ris = _risultato(gap=260, soluzione="d1h5", cambiata=True)
    puzzle = costruisci_puzzle(cand, ris, profondita=18)

    assert puzzle == {
        "fen": FEN_BIANCO,
        "soluzione_uci": "d1h5",
        "tua_mossa_uci": "c1e3",
        "san_giocata": "Be3",
        "gap_centipawn": 260,
        "era_matto": False,
        "eval_mia_prima": 383,
        "centipawn_loss": 329,
        "fonte_file": "rapid_0007.json",
        "indice_mossa": 12,
        "cadenza": "rapid",
        "profondita_validazione": 18,
    }


def test_costruisci_puzzle_usa_soluzione_validata_non_la_vecchia():
    cand = _candidato_completo()  # soluzione_uci vecchia = "h8g8"
    ris = _risultato(gap=260, soluzione="d1h5")
    puzzle = costruisci_puzzle(cand, ris, profondita=18)
    assert puzzle["soluzione_uci"] == "d1h5"
    assert puzzle["soluzione_uci"] != cand["soluzione_uci"]
    assert puzzle["tua_mossa_uci"] == cand["mossa_giocata_uci"]


# --- Ripartenza: chiave e filtro dei gia'-processati ---------------------

def test_chiave_candidato_fonte_piu_indice():
    cand = {"fonte_file": "rapid_0007.json", "indice_mossa": 12}
    assert chiave_candidato(cand) == "rapid_0007.json|12"


def test_filtra_da_processare_salta_i_gia_fatti():
    cands = [
        {"fonte_file": "a.json", "indice_mossa": 1},
        {"fonte_file": "a.json", "indice_mossa": 2},
        {"fonte_file": "b.json", "indice_mossa": 1},
    ]
    processati = {"a.json|1", "b.json|1"}
    rimasti = filtra_da_processare(cands, processati)
    assert [chiave_candidato(c) for c in rimasti] == ["a.json|2"]


def test_filtra_da_processare_senza_progresso_tiene_tutto():
    cands = [{"fonte_file": "a.json", "indice_mossa": i} for i in range(3)]
    assert filtra_da_processare(cands, set()) == cands


# --- --batch usa TUTTI i non-bullet, non un campione ---------------------

def test_seleziona_batch_tutti_i_non_bullet():
    cands = _cands(40)  # 20 bullet, 20 non-bullet alternati
    non_bullet, totale = seleziona_batch(cands)
    assert totale == 20
    assert len(non_bullet) == 20
    assert all(c["cadenza"] != "bullet" for c in non_bullet)


def test_seleziona_batch_non_tronca_come_il_campione():
    # Il campione di taratura tronca a n; il batch NO: deve restituirli tutti.
    cands = _cands(60)
    campione, _ = seleziona_campione(cands, 5)
    batch, _ = seleziona_batch(cands)
    assert len(campione) == 5
    assert len(batch) == 30  # tutti i 30 non-bullet di _cands(60)


# --- Integrazione del batch con un motore FINTO (niente Stockfish) -------

class FakeMotore:
    """
    Sostituto di Stockfish per i test: restituisce linee MultiPV preconfezionate
    in base al FEN, e registra quali FEN ha analizzato (per verificare i salti).
    """

    def __init__(self, mappa):
        self.mappa = mappa            # fen normalizzato -> lista di linee MultiPV
        self.analizzati = []
        self.chiuso = False

    def analyse(self, board, limit, multipv):
        fen = board.fen()
        self.analizzati.append(fen)
        return self.mappa[fen]

    def quit(self):
        self.chiuso = True


def _fen_norm(fen):
    return chess.Board(fen).fen()


# Tre FEN distinti, tutti con una mossa nettamente migliore (gap alto -> tenuti).
FEN_W2 = "rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1"


def _setup_batch(monkeypatch, tmp_path, mappa):
    """
    Prepara il batch a girare con un motore finto: forza l'esistenza del motore,
    fa restituire a popen_uci il nostro FakeMotore e instrada i salvataggi in
    tmp_path. Restituisce (fake, percorso_puzzle, percorso_progresso).
    """
    fake = FakeMotore(mappa)
    real_exists = os.path.exists

    def fake_exists(percorso):
        if percorso == valida_errori.PERCORSO_STOCKFISH:
            return True
        return real_exists(percorso)

    monkeypatch.setattr(valida_errori.os.path, "exists", fake_exists)
    monkeypatch.setattr(valida_errori.chess.engine.SimpleEngine, "popen_uci",
                        staticmethod(lambda percorso: fake))

    percorso_puzzle = str(tmp_path / "puzzle_errori.json")
    percorso_progresso = str(tmp_path / "puzzle_errori.progress.json")
    return fake, percorso_puzzle, percorso_progresso


def test_batch_tiene_solo_gap_sopra_soglia(monkeypatch, tmp_path):
    # Due non-bullet (gap alto -> tenuto, gap basso -> scartato) + un bullet.
    cand_tenuto = {"fen": FEN_BIANCO, "mossa_giocata_uci": "c1e3",
                   "soluzione_uci": "x", "san_giocata": "Be3",
                   "centipawn_loss": 300, "eval_mia_prima": 100,
                   "fonte_file": "rapid.json", "indice_mossa": 0, "cadenza": "rapid"}
    cand_scartato = {"fen": FEN_W2, "mossa_giocata_uci": "g8f6",
                     "soluzione_uci": "y", "san_giocata": "Nf6",
                     "centipawn_loss": 210, "eval_mia_prima": 50,
                     "fonte_file": "rapid.json", "indice_mossa": 1, "cadenza": "rapid"}
    cand_bullet = {"fen": FEN_NERO, "mossa_giocata_uci": "e7e5",
                   "soluzione_uci": "z", "san_giocata": "e5",
                   "centipawn_loss": 400, "eval_mia_prima": 0,
                   "fonte_file": "bullet.json", "indice_mossa": 0, "cadenza": "bullet"}

    mappa = {
        _fen_norm(FEN_BIANCO): [_linea(chess.engine.Cp(300), "e2e4", "w"),
                                _linea(chess.engine.Cp(40), "d2d4", "w")],
        _fen_norm(FEN_W2): [_linea(chess.engine.Cp(120), "g1e2", "b"),
                            _linea(chess.engine.Cp(90), "e7e6", "b")],
    }
    fake, pz, pr = _setup_batch(monkeypatch, tmp_path, mappa)

    riepilogo = valida_batch([cand_tenuto, cand_scartato, cand_bullet],
                             profondita=18, soglia=200,
                             percorso_puzzle=pz, percorso_progresso=pr)

    assert riepilogo["totale_non_bullet"] == 2
    assert riepilogo["n_bullet_saltati"] == 1
    assert riepilogo["validati"] == 2          # il bullet non viene mai aperto
    assert riepilogo["tenuti"] == 1
    assert riepilogo["scartati"] == 1
    # Il bullet non e' stato passato al motore.
    assert _fen_norm(FEN_NERO) not in fake.analizzati
    assert fake.chiuso is True

    import json
    with open(pz, encoding="utf-8") as f:
        puzzle = json.load(f)
    assert len(puzzle) == 1
    assert puzzle[0]["fen"] == FEN_BIANCO
    assert puzzle[0]["soluzione_uci"] == "e2e4"
    assert puzzle[0]["tua_mossa_uci"] == "c1e3"
    assert puzzle[0]["gap_centipawn"] == 260


def test_batch_riparte_e_salta_i_gia_processati(monkeypatch, tmp_path):
    # Tre non-bullet; uno (indice 0) e' gia' stato processato in una corsa
    # precedente: il batch deve saltarlo (motore mai chiamato per il suo FEN).
    cand0 = {"fen": FEN_BIANCO, "mossa_giocata_uci": "c1e3", "soluzione_uci": "x",
             "san_giocata": "Be3", "centipawn_loss": 300, "eval_mia_prima": 100,
             "fonte_file": "rapid.json", "indice_mossa": 0, "cadenza": "rapid"}
    cand1 = {"fen": FEN_W2, "mossa_giocata_uci": "g8f6", "soluzione_uci": "y",
             "san_giocata": "Nf6", "centipawn_loss": 300, "eval_mia_prima": 50,
             "fonte_file": "rapid.json", "indice_mossa": 1, "cadenza": "rapid"}
    cand2 = {"fen": FEN_NERO, "mossa_giocata_uci": "e7e5", "soluzione_uci": "z",
             "san_giocata": "e5", "centipawn_loss": 300, "eval_mia_prima": 0,
             "fonte_file": "rapid.json", "indice_mossa": 2, "cadenza": "rapid"}

    # Il motore finto conosce SOLO i FEN di cand1 e cand2: se provasse a
    # processare cand0 (gia' fatto) andrebbe in KeyError.
    mappa = {
        _fen_norm(FEN_W2): [_linea(chess.engine.Cp(300), "g1e2", "b"),
                            _linea(chess.engine.Cp(40), "e7e6", "b")],
        _fen_norm(FEN_NERO): [_linea(chess.engine.Cp(300), "d8h4", "b"),
                              _linea(chess.engine.Cp(40), "g8f6", "b")],
    }
    fake, pz, pr = _setup_batch(monkeypatch, tmp_path, mappa)

    # Pre-seed: una corsa precedente ha gia' tenuto cand0 e lo segna processato.
    import json
    puzzle_pre = [costruisci_puzzle(cand0, _risultato(gap=260, soluzione="e2e4"), 18)]
    with open(pz, "w", encoding="utf-8") as f:
        json.dump(puzzle_pre, f)
    stato_pre = componi_stato({"rapid.json|0"},
                              {"validati": 1, "tenuti": 1, "scartati": 0,
                               "matti": 0, "cambiate": 0},
                              gap=200, profondita=18)
    with open(pr, "w", encoding="utf-8") as f:
        json.dump(stato_pre, f)

    riepilogo = valida_batch([cand0, cand1, cand2], profondita=18, soglia=200,
                             percorso_puzzle=pz, percorso_progresso=pr)

    # cand0 saltato: il suo FEN non e' mai stato analizzato.
    assert _fen_norm(FEN_BIANCO) not in fake.analizzati
    assert _fen_norm(FEN_W2) in fake.analizzati
    assert _fen_norm(FEN_NERO) in fake.analizzati

    # Contatori cumulativi: 1 (ripreso) + 2 (nuovi) = 3.
    assert riepilogo["validati"] == 3
    assert riepilogo["tenuti"] == 3

    # Il file finale contiene i 3 puzzle e lo stato conosce le 3 chiavi.
    with open(pz, encoding="utf-8") as f:
        puzzle = json.load(f)
    assert len(puzzle) == 3
    ripresa = carica_progresso(pz, pr)
    assert ripresa is not None
    _, stato = ripresa
    assert set(stato["processati"]) == {"rapid.json|0", "rapid.json|1", "rapid.json|2"}


def test_batch_ricomincia_ignora_il_progresso(monkeypatch, tmp_path):
    # Con ricomincia=True il progresso precedente va ignorato: rivalida tutto.
    cand0 = {"fen": FEN_BIANCO, "mossa_giocata_uci": "c1e3", "soluzione_uci": "x",
             "san_giocata": "Be3", "centipawn_loss": 300, "eval_mia_prima": 100,
             "fonte_file": "rapid.json", "indice_mossa": 0, "cadenza": "rapid"}

    mappa = {
        _fen_norm(FEN_BIANCO): [_linea(chess.engine.Cp(300), "e2e4", "w"),
                                _linea(chess.engine.Cp(40), "d2d4", "w")],
    }
    fake, pz, pr = _setup_batch(monkeypatch, tmp_path, mappa)

    import json
    with open(pz, "w", encoding="utf-8") as f:
        json.dump([{"vecchio": True}], f)
    stato_pre = componi_stato({"rapid.json|0"},
                              {"validati": 1, "tenuti": 1, "scartati": 0,
                               "matti": 0, "cambiate": 0},
                              gap=200, profondita=18)
    with open(pr, "w", encoding="utf-8") as f:
        json.dump(stato_pre, f)

    riepilogo = valida_batch([cand0], profondita=18, soglia=200, ricomincia=True,
                             percorso_puzzle=pz, percorso_progresso=pr)

    # Riparte da zero: cand0 viene rianalizzato e i contatori NON includono la
    # corsa precedente.
    assert _fen_norm(FEN_BIANCO) in fake.analizzati
    assert riepilogo["validati"] == 1
    assert riepilogo["tenuti"] == 1
