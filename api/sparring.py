"""
Router SPARRING (sezione /sparring del frontend): partita contro un bot a livelli
con analisi posizionale in tempo reale dopo ogni mossa dell'utente.

Architettura (stateless: lo stato della partita vive nel frontend, qui arriva la FEN):

  POST /sparring/mossa      -> valuta la mossa dell'utente (engine + feature +
                               modello ML) e risponde con la mossa del bot
  POST /sparring/mossa-bot  -> solo la mossa del bot (quando l'utente ha il Nero
                               e il bot deve aprire)
  GET  /sparring/livelli    -> livelli disponibili (Skill Level Stockfish)

Diagnosi della mossa (stessa filosofia di ml/analizza_posizionale.py):
  - cp_loss [DATO] dal confronto engine prima/dopo (profondita' ridotta, realtime);
  - le prime MOSSE_TEORIA mosse non vengono diagnosticate (teoria d'apertura),
    MA un blunder >=300cp viene comunque segnalato;
  - TATTICA se la confutazione e' forzante (catture/scacchi nella PV, swing
    materiale) o cp_loss >= 300 -> la tattica la spiega gia' Stockfish;
  - POSIZIONALE altrimenti: si riportano le feature peggiorate (spiegazione
    deterministica [DATO]) + il rischio stimato dal modello ML [STIMA].

MODELLO DI RISCHIO (S3, promosso con misura [DATO] +0.0099 AUC a parita' di split):
  1a scelta: RETE NEURALE (data/rete_posizionale.pt, richiede torch) — AUC 0.7095;
  fallback:  GBM (data/modello_posizionale.joblib) — AUC 0.6996;
  senza entrambi: il pannello funziona lo stesso, senza campo rischio.
Il PRINCIPIO resta: la rete RILEVA, le spiegazioni restano deterministiche.

Il motore e' lo stesso stockfish.exe di engine/bin (override con env STOCKFISH_PATH,
utile nei sandbox non-Windows).
"""

import os
import shutil
import sys
import logging
import threading

import chess
import chess.engine
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("sparring")

# --- import dai moduli del progetto (ml/ e ml/rete/) ---------------------------
_QUI = os.path.dirname(os.path.abspath(__file__))
_ML = os.path.join(_QUI, "..", "ml")
_RETE = os.path.join(_ML, "rete")
for _p in (_ML, _RETE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from caratteristiche_posizionali import (          # noqa: E402
    estrai_caratteristiche, FEATURE_SIMMETRICHE, DESCRIZIONI, materiale,
)

PERCORSO_STOCKFISH = os.environ.get(
    "STOCKFISH_PATH",
    os.path.join(_QUI, "..", "engine", "bin", "stockfish.exe"),
)
PERCORSO_GBM = os.path.join(_QUI, "..", "data", "modello_posizionale.joblib")
PERCORSO_RETE = os.path.join(_QUI, "..", "data", "rete_posizionale.pt")

PROFONDITA_ANALISI = 12      # realtime: basso = risposta ~1s
SOGLIA_ERRORE_CP = 50
SOGLIA_TATTICA_CP = 300
PUNTEGGIO_MATTO = 10000
CLIP_CP = 1000
MOSSE_TEORIA = 5             # prime N mosse: niente diagnosi (teoria d'apertura)

LIVELLI = [
    {"id": "principiante", "nome": "Principiante", "skill": 2},
    {"id": "facile",       "nome": "Facile",       "skill": 5},
    {"id": "medio",        "nome": "Medio",        "skill": 8},
    {"id": "forte",        "nome": "Forte",        "skill": 13},
    {"id": "massimo",      "nome": "Massimo",      "skill": 20},
]
SKILL_PER_ID = {l["id"]: l["skill"] for l in LIVELLI}

router = APIRouter(prefix="/sparring", tags=["sparring"])

# --- motore condiviso (un processo, protetto da lock) -------------------------
_motore = None
_lock = threading.Lock()


def _apri_motore():
    global _motore
    if _motore is None:
        if not (os.path.exists(PERCORSO_STOCKFISH) or shutil.which(PERCORSO_STOCKFISH)):
            raise RuntimeError(f"Stockfish non trovato: {PERCORSO_STOCKFISH}")
        logger.info("Sparring: avvio Stockfish da %s", PERCORSO_STOCKFISH)
        _motore = chess.engine.SimpleEngine.popen_uci(PERCORSO_STOCKFISH)
    return _motore


# --- modello di rischio: rete neurale se possibile, altrimenti GBM -------------
_ml = None


def _carica_ml():
    """Ritorna {"tipo": "rete"|"gbm", ...} oppure {} se nessun modello e' caricabile."""
    global _ml
    if _ml is not None:
        return _ml
    # 1a scelta: rete neurale (S3)
    if os.path.exists(PERCORSO_RETE):
        try:
            import torch
            from modello import RetePosizionale
            ckpt = torch.load(PERCORSO_RETE, map_location="cpu")
            rete = RetePosizionale(ckpt["canali"], ckpt["blocchi"])
            rete.load_state_dict(ckpt["stato"])
            rete.eval()
            _ml = {"tipo": "rete", "rete": rete, "torch": torch,
                   "auc": ckpt.get("auc_val")}
            logger.info("Sparring: rete neurale caricata (AUC val: %s)", _ml["auc"])
            return _ml
        except Exception as e:
            logger.warning("Sparring: rete non caricata (%s), provo il GBM", e)
    # fallback: GBM (S1/S2)
    if os.path.exists(PERCORSO_GBM):
        try:
            import joblib
            g = joblib.load(PERCORSO_GBM)
            _ml = {"tipo": "gbm", "modello": g["modello"], "colonne": g["colonne"],
                   "auc": g.get("auc_test")}
            logger.info("Sparring: GBM caricato (AUC test: %s)", _ml["auc"])
            return _ml
        except Exception as e:
            logger.warning("Sparring: nessun modello di rischio caricato: %s", e)
    _ml = {}
    return _ml


def _punteggio_cp(pov_score):
    s = pov_score.score(mate_score=PUNTEGGIO_MATTO)
    return max(-CLIP_CP, min(CLIP_CP, s))


def _confutazione_forzante(board_dopo, pv):
    """True se la PV dell'avversario e' una sequenza forzante (tattica)."""
    if not pv:
        return False
    b = board_dopo.copy()
    mat_prima = materiale(b, chess.WHITE) - materiale(b, chess.BLACK)
    forzanti = 0
    for mv in pv[:4]:
        if b.is_capture(mv) or b.gives_check(mv):
            forzanti += 1
        b.push(mv)
    mat_dopo = materiale(b, chess.WHITE) - materiale(b, chess.BLACK)
    return abs(mat_dopo - mat_prima) > 1 or forzanti >= 3


def _feature_peggiorate(f_prima, f_dopo, muove_bianco, massimo=3):
    segno = 1 if muove_bianco else -1
    peggiori = []
    for chiave, descrizione in DESCRIZIONI.items():
        delta = segno * (f_dopo[chiave] - f_prima[chiave])
        if delta < 0:
            peggiori.append({"feature": chiave, "descrizione": descrizione,
                             "delta": delta})
    peggiori.sort(key=lambda x: x["delta"])
    return peggiori[:massimo]


def _rischio_ml(fen, mossa_uci, f_prima, f_dopo, muove_bianco, eval_prima):
    """Probabilita' [STIMA] che la mossa sia un errore posizionale.
    Ritorna (probabilita', nome_modello) oppure (None, None)."""
    ml = _carica_ml()
    if not ml:
        return None, None
    if ml["tipo"] == "rete":
        from tensori import codifica, normalizza_eval
        torch = ml["torch"]
        piani = torch.from_numpy(codifica(fen, mossa_uci)).unsqueeze(0)
        ev = torch.tensor([[normalizza_eval(eval_prima)]])
        with torch.no_grad():
            p = torch.sigmoid(ml["rete"](piani, ev)).item()
        return round(float(p), 3), "rete"
    # GBM sulle feature
    riga = {}
    segno = 1 if muove_bianco else -1
    for k in f_prima:
        if k in FEATURE_SIMMETRICHE:
            riga[f"pre_{k}"] = f_prima[k]
            riga[f"d_{k}"] = f_dopo[k] - f_prima[k]
        else:
            riga[f"pre_{k}"] = segno * f_prima[k]
            riga[f"d_{k}"] = segno * (f_dopo[k] - f_prima[k])
    riga["eval_prima"] = eval_prima
    riga["muove_bianco"] = int(muove_bianco)
    import pandas as pd
    X = pd.DataFrame([riga])[ml["colonne"]]
    return round(float(ml["modello"].predict_proba(X)[0, 1]), 3), "gbm"


def _mossa_bot(board, skill):
    """Chiede al motore la mossa del bot al livello dato."""
    motore = _apri_motore()
    motore.configure({"Skill Level": skill})
    # tempo breve: il bot deve rispondere subito; la forza la regola lo skill
    risultato = motore.play(board, chess.engine.Limit(time=0.4))
    return risultato.move


def _stato_partita(board):
    if board.is_checkmate():
        return "scacco_matto"
    if board.is_stalemate():
        return "stallo"
    if board.is_insufficient_material() or board.can_claim_draw():
        return "patta"
    return "in_corso"


class MossaRichiesta(BaseModel):
    fen: str                 # posizione PRIMA della mossa dell'utente
    mossa_uci: str
    livello: str = "medio"
    con_bot: bool = True     # False = solo analisi (es. ripasso)


class MossaBotRichiesta(BaseModel):
    fen: str
    livello: str = "medio"


@router.get("/livelli")
def livelli():
    ml = _carica_ml()
    return {"livelli": LIVELLI, "profondita_analisi": PROFONDITA_ANALISI,
            "mosse_teoria": MOSSE_TEORIA,
            "modello_rischio": ml.get("tipo"), "auc_modello": ml.get("auc")}


@router.post("/mossa-bot")
def mossa_bot(req: MossaBotRichiesta):
    board = chess.Board(req.fen)
    skill = SKILL_PER_ID.get(req.livello, 8)
    with _lock:
        mv = _mossa_bot(board, skill)
    san = board.san(mv)
    board.push(mv)
    return {"mossa_bot": mv.uci(), "san_bot": san, "fen": board.fen(),
            "stato": _stato_partita(board)}


@router.post("/mossa")
def mossa(req: MossaRichiesta):
    board = chess.Board(req.fen)
    try:
        mv = chess.Move.from_uci(req.mossa_uci)
    except ValueError:
        return {"errore": "mossa non valida"}
    if mv not in board.legal_moves:
        return {"errore": "mossa illegale"}

    muove_bianco = board.turn == chess.WHITE
    in_teoria = board.fullmove_number <= MOSSE_TEORIA
    f_prima = estrai_caratteristiche(board)
    limite = chess.engine.Limit(depth=PROFONDITA_ANALISI)

    with _lock:
        motore = _apri_motore()
        motore.configure({"Skill Level": 20})            # analisi a piena forza
        info_prima = motore.analyse(board, limite)
        eval_prima = _punteggio_cp(info_prima["score"].pov(board.turn))

        san = board.san(mv)
        board.push(mv)
        f_dopo = estrai_caratteristiche(board)

        info_dopo = motore.analyse(board, limite)
        eval_dopo = -_punteggio_cp(info_dopo["score"].pov(board.turn))
        pv = info_dopo.get("pv", [])

        cp_loss = max(0, eval_prima - eval_dopo)
        tattica = (cp_loss >= SOGLIA_TATTICA_CP
                   or (cp_loss >= SOGLIA_ERRORE_CP and _confutazione_forzante(board, pv)))

        tipo = "ok"
        spiegazioni = []
        rischio, modello_rischio = None, None
        if in_teoria and cp_loss < SOGLIA_TATTICA_CP:
            tipo = "teoria"    # niente diagnosi sulle prime mosse (ma i blunder si')
        elif cp_loss >= SOGLIA_ERRORE_CP:
            if tattica:
                tipo = "tattico"
            else:
                tipo = "posizionale"
                spiegazioni = _feature_peggiorate(f_prima, f_dopo, muove_bianco)
        if not in_teoria:
            rischio, modello_rischio = _rischio_ml(
                req.fen, req.mossa_uci, f_prima, f_dopo, muove_bianco, eval_prima)

        stato = _stato_partita(board)
        risposta_bot = None
        if req.con_bot and stato == "in_corso":
            skill = SKILL_PER_ID.get(req.livello, 8)
            mv_bot = _mossa_bot(board, skill)
            san_bot = board.san(mv_bot)
            board.push(mv_bot)
            risposta_bot = {"mossa_bot": mv_bot.uci(), "san_bot": san_bot}
            stato = _stato_partita(board)

    return {
        "san": san,
        "cp_loss": cp_loss,
        "eval_prima": eval_prima,
        "eval_dopo": eval_dopo,
        "tipo": tipo,                       # ok | teoria | tattico | posizionale
        "spiegazioni": spiegazioni,         # [DATO] feature peggiorate
        "rischio_ml": rischio,              # [STIMA] probabilita' modello (o None)
        "modello_rischio": modello_rischio, # "rete" | "gbm" | None
        "bot": risposta_bot,
        "fen": board.fen(),
        "stato": stato,
    }
