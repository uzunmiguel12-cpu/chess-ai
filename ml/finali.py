"""
Logica RIUSABILE sui finali (UNA sola versione, per non far divergere il codice).

Questo modulo raccoglie la classificazione del TIPO di finale (dal solo conteggio
pezzi nel FEN) e il calcolo dei TASSI di errore posizionale per tipo di finale.
Nasce dallo script usa-e-getta ml/analizza_finali.py: le funzioni conta_pezzi e
classifica_finale sono state SPOSTATE qui (non duplicate) e lo script le importa,
cosi' la classificazione non puo' divergere fra pipeline (script vs profilo).

REGOLE DELLA CLASSIFICAZIONE (dichiarate, dal conteggio pezzi nel FEN, ENTRAMBI i
colori esclusi i due re; con minori = alfieri + cavalli), in ordine di precedenza:
  - finale_donna   = donne >= 1            (almeno una donna presente, comunque)
  - finale_pedoni  = donne=0, torri=0, minori=0   (nessun pezzo, solo pedoni)
  - finale_torre   = donne=0, minori=0, torri>=1  (solo torri + pedoni)
  - finale_minori  = donne=0, torri=0, minori>=1  (solo alfieri/cavalli + pedoni)
  - finale_misto   = tutto il resto (es. torre + minore, piu' pezzi pesanti)

Il TASSO per tipo (tassi_finali_per_tipo) riusa ESATTAMENTE il filtro "errore
posizionale puro" di ml/analizza_posizionale.py (e_posizionale_puro) e la stessa
determinazione di fase finale (ml/categorizza.py: classifica_fase). Il TASSO ha il
SUO denominatore: le mosse giocate in finale di quel tipo (NON le mosse totali).
"""

import chess
from collections import Counter

# Riuso le utility gia' esistenti (come fanno gli altri script di ml/). Import
# "piatti" quando ml/ e' su sys.path (script eseguito da ml/, o ml/ aggiunto al
# path da chi importa); fallback a ml.* per l'import "a pacchetto".
try:
    from estrai_errori import turno_da_fen, eval_dal_mio_punto_di_vista
    from analizza_posizionale import e_posizionale_puro
    from categorizza import classifica_fase
except Exception:  # pragma: no cover - solo fallback se gli import piatti falliscono
    from ml.estrai_errori import turno_da_fen, eval_dal_mio_punto_di_vista  # noqa: F811
    from ml.analizza_posizionale import e_posizionale_puro
    from ml.categorizza import classifica_fase

# Soglia di robustezza: sotto MIN_MOSSE un tipo di finale e' 'fragile' (troppo
# poche mosse per un tasso attendibile) e NON viene usato per eleggere il peggiore.
# Unica definizione: ml/analizza_finali.py la importa da qui per non divergere.
MIN_MOSSE = 30

# Ordine canonico dei tipi di finale (per output stabile).
TIPI = (
    "finale_pedoni", "finale_torre", "finale_minori", "finale_donna",
    "finale_misto",
)


def conta_pezzi(board):
    """
    [DATO] Conta i pezzi di ENTRAMBI i colori, esclusi i due re, per tipo.
    Restituisce un dict con donne/torri/alfieri/cavalli (il dettaglio anti-T3).
    """
    return {
        "donne": len(board.pieces(chess.QUEEN, chess.WHITE))
        + len(board.pieces(chess.QUEEN, chess.BLACK)),
        "torri": len(board.pieces(chess.ROOK, chess.WHITE))
        + len(board.pieces(chess.ROOK, chess.BLACK)),
        "alfieri": len(board.pieces(chess.BISHOP, chess.WHITE))
        + len(board.pieces(chess.BISHOP, chess.BLACK)),
        "cavalli": len(board.pieces(chess.KNIGHT, chess.WHITE))
        + len(board.pieces(chess.KNIGHT, chess.BLACK)),
    }


def classifica_finale(fen):
    """
    [DATO] Restituisce (tipo, dettaglio) col tipo di finale secondo le REGOLE
    dichiarate in testa, dal solo conteggio pezzi (entrambi i colori, esclusi i re).
    """
    board = chess.Board(fen)
    d = conta_pezzi(board)
    donne = d["donne"]
    torri = d["torri"]
    minori = d["alfieri"] + d["cavalli"]

    if donne >= 1:
        tipo = "finale_donna"
    elif torri == 0 and minori == 0:
        tipo = "finale_pedoni"
    elif minori == 0:            # solo torri (+ pedoni), donne gia' == 0
        tipo = "finale_torre"
    elif torri == 0:             # solo minori (+ pedoni), donne gia' == 0
        tipo = "finale_minori"
    else:
        tipo = "finale_misto"
    return tipo, d


def _pct(parte, totale):
    """Percentuale robusta a 1 decimale: 0.0 se il totale e' zero."""
    return round(100.0 * parte / totale, 1) if totale else 0.0


def tassi_finali_per_tipo(mosse):
    """
    Calcola, per ciascun tipo di finale, mosse_tot / errori_posizionali / tasso su
    una lista di MIE mosse gia' pronte (ognuna col FEN prima della mossa e i campi
    di valutazione: fen, eval_prima, eval_dopo, centipawn_loss, best_move_uci).

    AMBITO: solo le mosse in fase == 'finale' (classifica_fase). Per ciascuna il
    NUMERATORE e' l'errore posizionale puro riusando e_posizionale_puro (stesso
    filtro di analizza_posizionale/analizza_finali: la best e' tranquilla, non
    cattura/scacco/promozione ne' tattica nota, in posizione sana). Il colore dal
    quale valutare (sono_bianco) si ricava dal turno nel FEN: queste sono MIE mosse,
    quindi tocca a me, e il turno del FEN e' il mio colore in quella posizione.

    DENOMINATORE dichiarato: le mosse giocate in finale di quel tipo (NON le mosse
    totali del profilo). E' una misura diversa dal piano tattico e va tenuta separata.

    Restituisce:
      {
        "per_tipo": { tipo: {"mosse", "errori", "tasso", "fragile"} },
        "tipo_peggiore": tipo col tasso piu' alto fra i NON fragili (o None),
        "tasso_peggiore": il relativo tasso (o None),
        "tipo_migliore": tipo col tasso piu' basso fra i NON fragili (o None),
        "min_mosse": MIN_MOSSE,
      }
    """
    mosse_tot = Counter()
    errori = Counter()

    for m in mosse:
        fen = m.get("fen")
        if not fen or classifica_fase(fen) != "finale":
            continue
        tipo, _ = classifica_finale(fen)
        mosse_tot[tipo] += 1

        # Colore dal turno del FEN (mia mossa => il turno e' il mio colore qui).
        sono_bianco = (turno_da_fen(fen) == "w")
        eval_mia = eval_dal_mio_punto_di_vista(m.get("eval_prima", 0), sono_bianco)
        if e_posizionale_puro(m, eval_mia):
            errori[tipo] += 1

    per_tipo = {}
    for tipo in TIPI:
        mt = mosse_tot.get(tipo, 0)
        er = errori.get(tipo, 0)
        per_tipo[tipo] = {
            "mosse": mt,
            "errori": er,
            "tasso": _pct(er, mt),
            "fragile": 0 < mt < MIN_MOSSE,
        }

    # Verdetto: solo i tipi NON fragili (>= MIN_MOSSE mosse) eleggono peggiore/migliore.
    validi = {t: v for t, v in per_tipo.items() if v["mosse"] >= MIN_MOSSE}
    if validi:
        tipo_peggiore = max(validi, key=lambda t: validi[t]["tasso"])
        tipo_migliore = min(validi, key=lambda t: validi[t]["tasso"])
        tasso_peggiore = validi[tipo_peggiore]["tasso"]
    else:
        tipo_peggiore = tipo_migliore = tasso_peggiore = None

    return {
        "per_tipo": per_tipo,
        "tipo_peggiore": tipo_peggiore,
        "tasso_peggiore": tasso_peggiore,
        "tipo_migliore": tipo_migliore,
        "min_mosse": MIN_MOSSE,
    }
