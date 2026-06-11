"""
Test del modulo estendi_sequenze (estensione dei puzzle-errore in sequenze
forzate con Stockfish).

NON apre Stockfish davvero: testa le funzioni pure (regola di forzatura) e simula
l'output del motore con un FakeMotore che restituisce linee MultiPV finte in base
al FEN, come in test_valida_errori.py. Le mosse delle linee finte sono mosse
LEGALI sulla scacchiera reale (l'estensione le gioca davvero), cosi' si verifica
anche la costruzione di "moves" e lunghezza_soluzione.

Esegui (dalla cartella ml, con ambiente attivo):
    pytest
"""

import os
import json

import chess
import chess.engine

import estendi_sequenze
from estendi_sequenze import (
    risolvi_soglie,
    turno_scacchiera,
    eval_e_mossa,
    gap_multipv,
    passo_avversario,
    passo_mio,
    costruisci_esteso,
    estendi_puzzle,
    seleziona_campione,
    chiave_puzzle,
    filtra_da_processare,
    componi_stato,
    carica_progresso,
    estendi_batch,
    SOGLIA_MATTO,
    GAP_MATTO,
    SOGLIA_DECISA,
)


def _linea(cp_o_mate, uci, turno):
    """
    Linea MultiPV finta come quelle di chess.engine.analyse:
    {"score": PovScore relativo a chi muove, "pv": [Move]}.
    """
    colore = chess.WHITE if turno == "w" else chess.BLACK
    return {
        "score": chess.engine.PovScore(cp_o_mate, colore),
        "pv": [chess.Move.from_uci(uci)],
    }


def _fen_norm(fen):
    return chess.Board(fen).fen()


# =========================================================================
# Funzioni pure: turno, estrazione, gap
# =========================================================================

FEN_BIANCO = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FEN_NERO = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def test_turno_scacchiera():
    assert turno_scacchiera(chess.Board(FEN_BIANCO)) == "w"
    assert turno_scacchiera(chess.Board(FEN_NERO)) == "b"


def test_eval_e_mossa_bianco():
    info = [_linea(chess.engine.Cp(120), "e2e4", "w")]
    eval_lato, vincente, subito, mossa = eval_e_mossa(info, "w")
    assert eval_lato == 120
    assert vincente is False and subito is False
    assert mossa == "e2e4"


def test_eval_e_mossa_matto_vincente_e_subito():
    info_v = [_linea(chess.engine.Mate(1), "d1h5", "w")]
    _, vincente, subito, _ = eval_e_mossa(info_v, "w")
    assert vincente is True and subito is False

    info_s = [_linea(chess.engine.Mate(-1), "a1a2", "w")]
    eval_lato, vincente, subito, _ = eval_e_mossa(info_s, "w")
    assert eval_lato == -SOGLIA_MATTO
    assert vincente is False and subito is True


def test_gap_multipv_due_linee():
    info = [_linea(chess.engine.Cp(300), "e2e4", "w"),
            _linea(chess.engine.Cp(90), "d2d4", "w")]
    assert gap_multipv(info, "w") == 210


def test_gap_multipv_unica_linea_e_infinito():
    info = [_linea(chess.engine.Cp(60), "e2e4", "w")]
    assert gap_multipv(info, "w") == GAP_MATTO


# =========================================================================
# Regola di forzatura: lato avversario
# =========================================================================

def test_passo_avversario_forzato_continua():
    # Gap netto dal lato dell'avversario (nero): e' forzato -> gioca la sua mossa.
    info = [_linea(chess.engine.Cp(-100), "g8f6", "b"),    # eval_mia = +100 (<800)
            _linea(chess.engine.Cp(-400), "e7e6", "b")]    # gap = 300 >= 200
    azione, mossa = passo_avversario(info, "b", soglia=200)
    assert azione == "continua"
    assert mossa == "g8f6"


def test_passo_avversario_ha_scelta_stop():
    # Gap piccolo: l'avversario ha una scelta reale -> stop (ambiguo oltre).
    info = [_linea(chess.engine.Cp(-100), "g8f6", "b"),
            _linea(chess.engine.Cp(-180), "e7e6", "b")]    # gap = 80 < 200
    azione, mossa = passo_avversario(info, "b", soglia=200)
    assert azione == "stop_scelta"
    assert mossa is None


def test_passo_avversario_unica_mossa_continua():
    # Una sola linea (mossa forzata): nessuna alternativa -> continua.
    info = [_linea(chess.engine.Cp(-50), "g8f6", "b")]
    azione, mossa = passo_avversario(info, "b", soglia=200)
    assert azione == "continua"
    assert mossa == "g8f6"


def test_passo_avversario_costretto_al_matto_continua():
    # L'avversario subisce matto (eval_mia = matto vincente): e' costretto.
    info = [_linea(chess.engine.Mate(-1), "g8f6", "b"),
            _linea(chess.engine.Mate(-2), "e7e6", "b")]
    azione, mossa = passo_avversario(info, "b", soglia=200)
    assert azione == "continua"
    assert mossa == "g8f6"


def test_passo_avversario_posizione_decisa_stop():
    # eval_mia = +900 (> 800) e nessun matto: posizione decisa -> stop (no accanimento).
    info = [_linea(chess.engine.Cp(-900), "g8f6", "b"),
            _linea(chess.engine.Cp(-1200), "e7e6", "b")]   # gap alto ma irrilevante
    azione, mossa = passo_avversario(info, "b", soglia=200)
    assert azione == "stop_decisa"
    assert mossa is None


# =========================================================================
# Regola di forzatura: lato mio
# =========================================================================

def test_passo_mio_netto_continua():
    info = [_linea(chess.engine.Cp(300), "e2e4", "w"),
            _linea(chess.engine.Cp(50), "d2d4", "w")]      # gap = 250 >= 200
    azione, mossa, eval_lato, vincente = passo_mio(info, "w", soglia=200)
    assert azione == "continua"
    assert mossa == "e2e4"
    assert eval_lato == 300
    assert vincente is False


def test_passo_mio_ambiguo_stop():
    info = [_linea(chess.engine.Cp(300), "e2e4", "w"),
            _linea(chess.engine.Cp(180), "d2d4", "w")]     # gap = 120 < 200
    azione, mossa, _, _ = passo_mio(info, "w", soglia=200)
    assert azione == "stop_scelta"
    assert mossa is None


def test_passo_mio_matto_vincente_continua():
    info = [_linea(chess.engine.Mate(1), "d1h5", "w"),
            _linea(chess.engine.Cp(120), "f1c4", "w")]
    azione, mossa, _, vincente = passo_mio(info, "w", soglia=200)
    assert azione == "continua"
    assert mossa == "d1h5"
    assert vincente is True


# =========================================================================
# Costruzione del puzzle esteso
# =========================================================================

def _puzzle(moves, fen=None, id="err_test_1"):
    return {
        "id": id,
        "fen": fen or chess.STARTING_FEN,
        "moves": moves,
        "rating": 1200,
        "themes": "errore",
        "motivo_allenamento": "errore",
        "fase_allenamento": None,
    }


def test_costruisci_esteso_aggiorna_moves_e_lunghezza():
    p = _puzzle("e2e4 e7e5")
    esteso = costruisci_esteso(p, ["e2e4", "e7e5", "g1f3", "b8c6"], n_mie=2)
    assert esteso["moves"] == "e2e4 e7e5 g1f3 b8c6"
    assert esteso["lunghezza_soluzione"] == 2
    # Gli altri campi e il loro ordine restano invariati.
    assert esteso["id"] == p["id"]
    assert esteso["rating"] == 1200
    assert list(esteso)[:len(p)] == list(p)


# =========================================================================
# FakeMotore + scacchiera reale: integrazione dell'estensione
# =========================================================================

class FakeMotore:
    """Restituisce linee MultiPV preconfezionate in base al FEN della posizione."""

    def __init__(self, mappa):
        self.mappa = mappa
        self.analizzati = []
        self.chiuso = False

    def analyse(self, board, limit, multipv):
        fen = board.fen()
        self.analizzati.append(fen)
        return self.mappa[fen]

    def quit(self):
        self.chiuso = True


def _coppia_linee(board, eval_lato, gap):
    """
    Due linee MultiPV per la posizione: la 1a mossa = prima legale (quella che il
    codice giochera'), la 2a = seconda legale. eval_lato e' la valutazione della 1a
    dal lato di chi muove; la 2a vale eval_lato-gap (cosi' il gap e' esattamente gap).
    Restituisce (linee, prima_mossa_legale).
    """
    turno = turno_scacchiera(board)
    mosse = list(board.legal_moves)
    m1 = mosse[0]
    m2 = mosse[1] if len(mosse) > 1 else mosse[0]
    linee = [_linea(chess.engine.Cp(eval_lato), m1.uci(), turno),
             _linea(chess.engine.Cp(eval_lato - gap), m2.uci(), turno)]
    return linee, m1


def _catena_forzata(puzzle, n_coppie, eval_avv=-300, eval_mio=300, gap=400):
    """
    Costruisce una mappa fen->linee per una catena di n_coppie (avversario+mia)
    tutte forzate: in ogni posizione la 1a mossa e' la prima legale e il gap e'
    grande. Le valutazioni restano sotto la soglia "decisa" (eval_mia<800) per non
    fermare la catena. Restituisce (mappa, mosse) con mosse = semimosse aggiunte
    dopo la mia prima mossa (avv, mia, avv, mia, ...).
    """
    board = chess.Board(puzzle["fen"])
    for u in puzzle["moves"].split():
        board.push(chess.Move.from_uci(u))

    mappa = {}
    mosse = []
    for _ in range(n_coppie):
        linee, m_avv = _coppia_linee(board, eval_avv, gap)
        mappa[board.fen()] = linee
        board.push(m_avv)
        mosse.append(m_avv.uci())

        linee, m_mio = _coppia_linee(board, eval_mio, gap)
        mappa[board.fen()] = linee
        board.push(m_mio)
        mosse.append(m_mio.uci())
    return mappa, mosse


# Posizione di partenza comoda: dopo 1.e4 e5 e' di nuovo il turno del Bianco
# (l'avversario, nel nostro schema setup=e4 / mia=e5).
PUZZLE_BASE = {
    "id": "err_catena", "fen": chess.STARTING_FEN, "moves": "e2e4 e7e5",
    "rating": 1200, "themes": "errore",
    "motivo_allenamento": "errore", "fase_allenamento": None,
}


def _motore_estendi(monkeypatch, mappa):
    """Forza l'esistenza del motore e fa restituire a popen_uci il FakeMotore."""
    fake = FakeMotore(mappa)
    real_exists = os.path.exists

    def fake_exists(percorso):
        if percorso == estendi_sequenze.PERCORSO_STOCKFISH:
            return True
        return real_exists(percorso)

    monkeypatch.setattr(estendi_sequenze.os.path, "exists", fake_exists)
    monkeypatch.setattr(estendi_sequenze.chess.engine.SimpleEngine, "popen_uci",
                        staticmethod(lambda percorso: fake))
    return fake


def test_estendi_tetto_tre_mosse(monkeypatch):
    # Tutto forzato: la catena si ferma al tetto di 3 mosse mie.
    mappa, mosse = _catena_forzata(PUZZLE_BASE, n_coppie=2)
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18, gap=200)

    assert dettaglio["lunghezza"] == 3
    assert dettaglio["motivo_stop"] == "tetto"
    assert dettaglio["a_matto"] is False
    assert esteso["moves"] == "e2e4 e7e5 " + " ".join(mosse)
    assert esteso["lunghezza_soluzione"] == 3


def test_estendi_stop_lato_avversario(monkeypatch):
    # L'avversario ha scelta alla prima risposta: la soluzione resta da 1 mossa.
    board = chess.Board(PUZZLE_BASE["fen"])
    for u in PUZZLE_BASE["moves"].split():
        board.push(chess.Move.from_uci(u))
    # Gap piccolo dal lato dell'avversario -> stop_scelta.
    linee, _ = _coppia_linee(board, eval_lato=-100, gap=50)
    mappa = {board.fen(): linee}
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18, gap=200)

    assert dettaglio["lunghezza"] == 1
    assert dettaglio["motivo_stop"] == "stop_scelta"
    assert esteso["moves"] == "e2e4 e7e5"
    assert esteso["lunghezza_soluzione"] == 1


def test_estendi_stop_lato_mio_scarta_anche_avversario(monkeypatch):
    # L'avversario e' forzato, ma la MIA mossa successiva e' ambigua: si scarta
    # anche la risposta avversaria (la soluzione finisce sulla mia mossa precedente).
    board = chess.Board(PUZZLE_BASE["fen"])
    for u in PUZZLE_BASE["moves"].split():
        board.push(chess.Move.from_uci(u))
    # Avversario forzato (gap grande).
    linee_avv, m_avv = _coppia_linee(board, eval_lato=-300, gap=400)
    mappa = {board.fen(): linee_avv}
    board.push(m_avv)
    # Mio turno: gap piccolo -> ambiguo -> stop.
    linee_mio, _ = _coppia_linee(board, eval_lato=300, gap=50)
    mappa[board.fen()] = linee_mio
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18, gap=200)

    assert dettaglio["lunghezza"] == 1
    assert dettaglio["motivo_stop"] == "stop_scelta"
    # La risposta avversaria NON e' stata inclusa.
    assert esteso["moves"] == "e2e4 e7e5"


def test_estendi_stop_posizione_decisa(monkeypatch):
    # Dopo la mia prima mossa sono gia' a +900 senza matto: stop, resta 1 mossa.
    board = chess.Board(PUZZLE_BASE["fen"])
    for u in PUZZLE_BASE["moves"].split():
        board.push(chess.Move.from_uci(u))
    linee, _ = _coppia_linee(board, eval_lato=-900, gap=400)  # eval_mia = +900
    mappa = {board.fen(): linee}
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18, gap=200)

    assert dettaglio["lunghezza"] == 1
    assert dettaglio["motivo_stop"] == "stop_decisa"
    assert esteso["moves"] == "e2e4 e7e5"


def test_estendi_stop_su_matto_immediato():
    # La mia mossa-soluzione e' gia' matto (scholar's mate): resta 1 mossa, a_matto.
    puzzle = {
        "id": "err_matto",
        "fen": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
        "moves": "g8f6 h5f7",   # ...Nf6?? Qxf7#
        "rating": 1000, "themes": "errore",
        "motivo_allenamento": "errore", "fase_allenamento": None,
    }
    # Il motore non viene mai interrogato: la posizione e' gia' matto dopo Qxf7#.
    fake = FakeMotore({})

    esteso, dettaglio = estendi_puzzle(puzzle, fake, profondita=18, gap=200)

    assert dettaglio["lunghezza"] == 1
    assert dettaglio["a_matto"] is True
    assert dettaglio["motivo_stop"] == "matto"
    assert esteso["moves"] == "g8f6 h5f7"
    assert esteso["lunghezza_soluzione"] == 1
    assert fake.analizzati == []   # mai analizzato


def test_estendi_matto_in_due_mosse_arriva_al_matto():
    # Catena che termina con un matto reale (KQ vs K): dopo setup+mia1 il Nero e' in
    # scacco con un'unica risposta forzata (h1h2), poi do matto con Qa1-h8#. La
    # soluzione cresce a 2 mie mosse (mia1 d'attesa + matto) e a_matto e' True.
    fen = "8/8/8/8/8/8/1Q3K1k/8 b - - 0 1"   # prima del setup, Nero al tratto
    setup = "h2h1"                            # mossa (setup) del Nero
    mia1 = "b2a1"                             # mia mossa: scacco con la Donna
    puzzle = {"id": "err_kq", "fen": fen, "moves": f"{setup} {mia1}",
              "rating": 1000, "themes": "errore",
              "motivo_allenamento": "errore", "fase_allenamento": None}

    # Posizione dopo setup+mia1: tocca al Nero, in scacco, unica mossa h1h2.
    b1 = chess.Board(fen)
    b1.push(chess.Move.from_uci(setup))
    b1.push(chess.Move.from_uci(mia1))
    # Linea avversario: subisce matto inevitabile -> forzato (continua).
    linee_avv = [_linea(chess.engine.Mate(-2), "h1h2", "b"),
                 _linea(chess.engine.Mate(-2), "h1h2", "b")]
    mappa = {b1.fen(): linee_avv}
    b1.push(chess.Move.from_uci("h1h2"))
    # Mio turno: Qa1-h8 e' matto -> matto vincente, continua.
    linee_mio = [_linea(chess.engine.Mate(1), "a1h8", "w"),
                 _linea(chess.engine.Cp(100), list(b1.legal_moves)[0].uci(), "w")]
    mappa[b1.fen()] = linee_mio
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(puzzle, fake, profondita=18, gap=200)
    assert dettaglio["a_matto"] is True
    assert dettaglio["motivo_stop"] == "matto"
    assert dettaglio["lunghezza"] == 2
    assert esteso["moves"] == f"{setup} {mia1} h1h2 a1h8"


# =========================================================================
# Gap asimmetrico: soglia diversa per le mie mosse e per l'avversario
# =========================================================================

def test_risolvi_soglie_retrocompat_e_separate():
    # Vecchio gap unico: vale per entrambe.
    assert risolvi_soglie(150, 200, 100) == (150, 150)
    # Nessun gap unico: valgono le due soglie separate.
    assert risolvi_soglie(None, 200, 100) == (200, 100)


def _mappa_una_coppia(puzzle, gap_avv_pos, gap_mio_pos,
                      eval_avv=-300, eval_mio=300):
    """
    Mappa fen->linee per UNA sola coppia (risposta avversaria + mia mossa) dopo
    setup+mia1: il lato avversario ha esattamente gap_avv_pos, il mio gap_mio_pos.
    Le valutazioni restano sotto la soglia "decisa". Dopo la coppia, la posizione
    avversaria successiva e' configurata per FERMARE la catena (gap piccolo ->
    stop_scelta), cosi' il puzzle si chiude pulito a 2 mosse mie. Restituisce
    (mappa, mossa_avv_uci, mossa_mia_uci).
    """
    board = chess.Board(puzzle["fen"])
    for u in puzzle["moves"].split():
        board.push(chess.Move.from_uci(u))
    linee_avv, m_avv = _coppia_linee(board, eval_avv, gap_avv_pos)
    mappa = {board.fen(): linee_avv}
    board.push(m_avv)
    linee_mio, m_mio = _coppia_linee(board, eval_mio, gap_mio_pos)
    mappa[board.fen()] = linee_mio
    board.push(m_mio)
    # Tappo: prossima risposta avversaria con gap piccolo -> stop_scelta.
    linee_stop, _ = _coppia_linee(board, eval_lato=-100, gap=50)
    mappa[board.fen()] = linee_stop
    return mappa, m_avv.uci(), m_mio.uci()


def test_estendi_difesa_avversaria_accettata_con_gap_avv_basso():
    # Difesa avversaria con gap 150: ACCETTATA con gap_avv=100 (150 >= 100), la mia
    # mossa successiva e' nettamente forzata -> la coppia viene tenuta (2 mosse).
    mappa, m_avv, m_mio = _mappa_una_coppia(
        PUZZLE_BASE, gap_avv_pos=150, gap_mio_pos=400)
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18,
                                       gap_mio=200, gap_avv=100)

    assert dettaglio["lunghezza"] == 2
    assert dettaglio["motivo_stop"] == "stop_scelta"
    assert esteso["moves"] == f"e2e4 e7e5 {m_avv} {m_mio}"


def test_estendi_difesa_avversaria_rifiutata_con_gap_avv_alto():
    # Stessa difesa avversaria con gap 150: RIFIUTATA con gap_avv=200 (150 < 200) ->
    # l'avversario ha scelta, la soluzione resta da 1 mossa.
    mappa, _, _ = _mappa_una_coppia(
        PUZZLE_BASE, gap_avv_pos=150, gap_mio_pos=400)
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18,
                                       gap_mio=200, gap_avv=200)

    assert dettaglio["lunghezza"] == 1
    assert dettaglio["motivo_stop"] == "stop_scelta"
    assert esteso["moves"] == "e2e4 e7e5"


def test_estendi_mia_mossa_rifiutata_con_gap_mio_alto():
    # Avversario forzato (gap 400), ma la MIA mossa ha gap 150: RIFIUTATA con
    # gap_mio=200 (150 < 200), pur con gap_avv basso -> si scarta anche la risposta
    # avversaria e la soluzione resta da 1 mossa.
    mappa, _, _ = _mappa_una_coppia(
        PUZZLE_BASE, gap_avv_pos=400, gap_mio_pos=150)
    fake = FakeMotore(mappa)

    esteso, dettaglio = estendi_puzzle(PUZZLE_BASE, fake, profondita=18,
                                       gap_mio=200, gap_avv=100)

    assert dettaglio["lunghezza"] == 1
    assert dettaglio["motivo_stop"] == "stop_scelta"
    assert esteso["moves"] == "e2e4 e7e5"


# =========================================================================
# Modalita' campione con seed
# =========================================================================

def _coda(n):
    return [{"id": "err_%d" % i, "fen": chess.STARTING_FEN,
             "moves": "e2e4 e7e5"} for i in range(n)]


def test_seleziona_campione_rispetta_n_e_totale():
    campione, totale = seleziona_campione(_coda(50), 10)
    assert len(campione) == 10
    assert totale == 50


def test_seleziona_campione_deterministico_con_seed():
    a, _ = seleziona_campione(_coda(50), 12)
    b, _ = seleziona_campione(_coda(50), 12)
    assert [c["id"] for c in a] == [c["id"] for c in b]


def test_seleziona_campione_mescolato_non_primi_in_ordine():
    coda = _coda(60)
    campione, _ = seleziona_campione(coda, 30)
    assert [c["id"] for c in campione] != [c["id"] for c in coda[:30]]


# =========================================================================
# Batch: ripartenza e salvataggio (con FakeMotore)
# =========================================================================

def _setup_batch(monkeypatch, tmp_path, mappa):
    fake = _motore_estendi(monkeypatch, mappa)
    percorso_output = str(tmp_path / "coda_errori_estesa.json")
    percorso_progresso = str(tmp_path / "coda_errori_estesa.progress.json")
    return fake, percorso_output, percorso_progresso


def test_chiave_e_filtro_ripartenza():
    cands = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    assert chiave_puzzle(cands[0]) == "a"
    rimasti = filtra_da_processare(cands, {"a", "c"})
    assert [p["id"] for p in rimasti] == ["b"]


def test_batch_estende_e_salva(monkeypatch, tmp_path):
    # Un puzzle che si ferma subito (avversario con scelta): resta da 1 mossa.
    p = dict(PUZZLE_BASE)
    board = chess.Board(p["fen"])
    for u in p["moves"].split():
        board.push(chess.Move.from_uci(u))
    linee, _ = _coppia_linee(board, eval_lato=-100, gap=50)   # stop_scelta
    mappa = {board.fen(): linee}
    fake, pout, pprog = _setup_batch(monkeypatch, tmp_path, mappa)

    riepilogo = estendi_batch([p], profondita=18, gap=200,
                              percorso_output=pout, percorso_progresso=pprog)

    assert riepilogo["totale"] == 1
    assert riepilogo["totali"] == 1
    assert riepilogo["lung1"] == 1
    assert riepilogo["n_file"] == 1
    assert fake.chiuso is True

    with open(pout, encoding="utf-8") as f:
        estesi = json.load(f)
    assert len(estesi) == 1
    assert estesi[0]["lunghezza_soluzione"] == 1
    assert estesi[0]["moves"] == "e2e4 e7e5"


def test_batch_riparte_e_salta_i_gia_processati(monkeypatch, tmp_path):
    # Due puzzle; uno gia' processato in una corsa precedente: va saltato.
    p0 = {"id": "err_0", "fen": chess.STARTING_FEN, "moves": "e2e4 e7e5",
          "rating": 1200, "themes": "errore",
          "motivo_allenamento": "errore", "fase_allenamento": None}
    p1 = {"id": "err_1", "fen": chess.STARTING_FEN, "moves": "d2d4 d7d5",
          "rating": 1200, "themes": "errore",
          "motivo_allenamento": "errore", "fase_allenamento": None}

    # Il motore finto conosce SOLO la posizione di p1: se provasse a estendere p0
    # (gia' fatto) andrebbe in KeyError.
    board1 = chess.Board(p1["fen"])
    for u in p1["moves"].split():
        board1.push(chess.Move.from_uci(u))
    linee1, _ = _coppia_linee(board1, eval_lato=-100, gap=50)   # stop_scelta
    mappa = {board1.fen(): linee1}
    fake, pout, pprog = _setup_batch(monkeypatch, tmp_path, mappa)

    # Pre-seed: una corsa precedente ha gia' esteso p0.
    esteso0 = costruisci_esteso(p0, ["e2e4", "e7e5"], n_mie=1)
    with open(pout, "w", encoding="utf-8") as f:
        json.dump([esteso0], f)
    stato_pre = componi_stato({"err_0"},
                              {"totali": 1, "lung1": 1, "lung2": 0,
                               "lung3": 0, "matti": 0},
                              gap=200, profondita=18)
    with open(pprog, "w", encoding="utf-8") as f:
        json.dump(stato_pre, f)

    riepilogo = estendi_batch([p0, p1], profondita=18, gap=200,
                              percorso_output=pout, percorso_progresso=pprog)

    # p0 saltato: la sua posizione (dopo e2e4 e7e5) non e' mai stata analizzata,
    # mentre quella di p1 (dopo d2d4 d7d5) si'.
    board0 = chess.Board(p0["fen"])
    for u in p0["moves"].split():
        board0.push(chess.Move.from_uci(u))
    assert board0.fen() not in fake.analizzati
    assert board1.fen() in fake.analizzati
    # Contatori cumulativi: 1 (ripreso) + 1 (nuovo) = 2.
    assert riepilogo["totali"] == 2
    assert riepilogo["lung1"] == 2

    with open(pout, encoding="utf-8") as f:
        estesi = json.load(f)
    assert [e["id"] for e in estesi] == ["err_0", "err_1"]

    ripresa = carica_progresso(pout, pprog)
    assert ripresa is not None
    _, stato = ripresa
    assert set(stato["processati"]) == {"err_0", "err_1"}


def test_batch_ricomincia_ignora_il_progresso(monkeypatch, tmp_path):
    p0 = {"id": "err_0", "fen": chess.STARTING_FEN, "moves": "e2e4 e7e5",
          "rating": 1200, "themes": "errore",
          "motivo_allenamento": "errore", "fase_allenamento": None}
    board = chess.Board(p0["fen"])
    for u in p0["moves"].split():
        board.push(chess.Move.from_uci(u))
    linee, _ = _coppia_linee(board, eval_lato=-100, gap=50)
    mappa = {board.fen(): linee}
    fake, pout, pprog = _setup_batch(monkeypatch, tmp_path, mappa)

    with open(pout, "w", encoding="utf-8") as f:
        json.dump([{"vecchio": True}], f)
    stato_pre = componi_stato({"err_0"},
                              {"totali": 1, "lung1": 1, "lung2": 0,
                               "lung3": 0, "matti": 0},
                              gap=200, profondita=18)
    with open(pprog, "w", encoding="utf-8") as f:
        json.dump(stato_pre, f)

    riepilogo = estendi_batch([p0], profondita=18, gap=200, ricomincia=True,
                              percorso_output=pout, percorso_progresso=pprog)

    # Riparte da zero: p0 viene riesteso, i contatori non includono la corsa prima.
    assert riepilogo["totali"] == 1
    assert riepilogo["lung1"] == 1
    with open(pout, encoding="utf-8") as f:
        estesi = json.load(f)
    assert len(estesi) == 1
    assert estesi[0]["id"] == "err_0"
