"""
Caratteristiche POSIZIONALI di una posizione (Fase 3 — modello posizionale Sparring).

Estrae ~20 feature numeriche da una chess.Board: chiusura, struttura pedonale,
qualita' dei pezzi, sicurezza del re, attivita'. Le feature "diff" sono espresse
come (Bianco - Nero): positive = meglio per il Bianco.

Modulo di SOLA LETTURA della posizione: nessun engine, nessun file, nessuno stato.
Usato da: ml/dataset_posizionale.py (training) e api/sparring.py (realtime).

Uso rapido:
    import chess
    from caratteristiche_posizionali import estrai_caratteristiche
    f = estrai_caratteristiche(chess.Board())
"""

import chess

CENTRO = [chess.D4, chess.E4, chess.D5, chess.E5]
CASE_CHIARE = chess.SquareSet(chess.BB_LIGHT_SQUARES)
CASE_SCURE = chess.SquareSet(chess.BB_DARK_SQUARES)

VALORI_PEZZI = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                chess.ROOK: 5, chess.QUEEN: 9}


# ---------------------------------------------------------------- pedoni

def _pedoni(board, colore):
    return list(board.pieces(chess.PAWN, colore))


def _colonne_con_pedoni(pedoni):
    colonne = {}
    for sq in pedoni:
        colonne.setdefault(chess.square_file(sq), []).append(sq)
    return colonne


def pedoni_bloccati(board):
    """Coppie di pedoni bloccati faccia a faccia (indice di chiusura)."""
    n = 0
    for sq in board.pieces(chess.PAWN, chess.WHITE):
        su = sq + 8
        if su <= 63 and board.piece_at(su) == chess.Piece(chess.PAWN, chess.BLACK):
            n += 1
    return n


def pedoni_doppiati(board, colore):
    colonne = _colonne_con_pedoni(_pedoni(board, colore))
    return sum(len(v) - 1 for v in colonne.values() if len(v) > 1)


def pedoni_isolati(board, colore):
    colonne = _colonne_con_pedoni(_pedoni(board, colore))
    n = 0
    for c in colonne:
        if (c - 1) not in colonne and (c + 1) not in colonne:
            n += len(colonne[c])
    return n


def pedoni_passati(board, colore):
    nemici = _pedoni(board, not colore)
    n = 0
    for sq in _pedoni(board, colore):
        c, t = chess.square_file(sq), chess.square_rank(sq)
        ostacoli = [
            e for e in nemici
            if abs(chess.square_file(e) - c) <= 1
            and ((colore == chess.WHITE and chess.square_rank(e) > t)
                 or (colore == chess.BLACK and chess.square_rank(e) < t))
        ]
        if not ostacoli:
            n += 1
    return n


def pedoni_arretrati(board, colore):
    """Pedone arretrato: nessun pedone amico adiacente allo stesso livello o dietro,
    e la casa di avanzata e' controllata da un pedone nemico."""
    propri = _pedoni(board, colore)
    n = 0
    direzione = 8 if colore == chess.WHITE else -8
    for sq in propri:
        c, t = chess.square_file(sq), chess.square_rank(sq)
        sostegno = any(
            abs(chess.square_file(o) - c) == 1
            and ((colore == chess.WHITE and chess.square_rank(o) <= t)
                 or (colore == chess.BLACK and chess.square_rank(o) >= t))
            for o in propri if o != sq
        )
        avanzata = sq + direzione
        if not sostegno and 0 <= avanzata <= 63:
            attaccanti = board.attackers(not colore, avanzata)
            if any(board.piece_type_at(a) == chess.PAWN for a in attaccanti):
                n += 1
    return n


def isole_di_pedoni(board, colore):
    colonne = sorted(_colonne_con_pedoni(_pedoni(board, colore)).keys())
    if not colonne:
        return 0
    isole = 1
    for a, b in zip(colonne, colonne[1:]):
        if b - a > 1:
            isole += 1
    return isole


def pedoni_protetti(board, colore):
    """Pedoni difesi da un altro pedone (catene)."""
    n = 0
    for sq in _pedoni(board, colore):
        attaccanti = board.attackers(colore, sq)
        if any(board.piece_type_at(a) == chess.PAWN for a in attaccanti):
            n += 1
    return n


# ---------------------------------------------------------------- colonne

def stato_colonne(board):
    """Ritorna (aperte, semiaperte_per_bianco, semiaperte_per_nero)."""
    cb = set(chess.square_file(s) for s in _pedoni(board, chess.WHITE))
    cn = set(chess.square_file(s) for s in _pedoni(board, chess.BLACK))
    aperte = [c for c in range(8) if c not in cb and c not in cn]
    semi_b = [c for c in range(8) if c not in cb and c in cn]
    semi_n = [c for c in range(8) if c in cb and c not in cn]
    return aperte, semi_b, semi_n


def torri_su_colonne_aperte(board, colore):
    aperte, semi_b, semi_n = stato_colonne(board)
    semi = semi_b if colore == chess.WHITE else semi_n
    n = 0
    for sq in board.pieces(chess.ROOK, colore):
        c = chess.square_file(sq)
        if c in aperte:
            n += 2          # colonna aperta vale doppio
        elif c in semi:
            n += 1
    return n


def torri_in_settima(board, colore):
    traversa = 6 if colore == chess.WHITE else 1
    return sum(1 for sq in board.pieces(chess.ROOK, colore)
               if chess.square_rank(sq) == traversa)


# ---------------------------------------------------------------- pezzi minori

def coppia_alfieri(board, colore):
    return 1 if len(board.pieces(chess.BISHOP, colore)) >= 2 else 0


def alfiere_cattivo(board, colore):
    """Somma dei propri pedoni sul colore dei propri alfieri (piu' alto = peggio)."""
    punteggio = 0
    pedoni = chess.SquareSet(board.pieces(chess.PAWN, colore))
    for a in board.pieces(chess.BISHOP, colore):
        stesso_colore = CASE_CHIARE if a in CASE_CHIARE else CASE_SCURE
        punteggio += len(pedoni & stesso_colore)
    return punteggio


def avamposti_cavallo(board, colore):
    """Cavallo in campo avversario, difeso da un pedone, non scacciabile da pedoni."""
    n = 0
    traverse_buone = range(3, 6) if colore == chess.WHITE else range(2, 5)
    for sq in board.pieces(chess.KNIGHT, colore):
        t, c = chess.square_rank(sq), chess.square_file(sq)
        if t not in traverse_buone:
            continue
        difeso = any(board.piece_type_at(a) == chess.PAWN
                     for a in board.attackers(colore, sq))
        scacciabile = False
        for e in _pedoni(board, not colore):
            ec, et = chess.square_file(e), chess.square_rank(e)
            if abs(ec - c) == 1 and ((colore == chess.WHITE and et > t)
                                     or (colore == chess.BLACK and et < t)):
                scacciabile = True
                break
        if difeso and not scacciabile:
            n += 1
    return n


# ---------------------------------------------------------------- re, spazio, mobilita'

def scudo_pedoni_re(board, colore):
    """Pedoni-scudo nelle 3 colonne attorno al re, 1-2 traverse davanti."""
    re = board.king(colore)
    if re is None:
        return 0
    rc, rt = chess.square_file(re), chess.square_rank(re)
    n = 0
    traverse = [rt + 1, rt + 2] if colore == chess.WHITE else [rt - 1, rt - 2]
    for c in range(max(0, rc - 1), min(7, rc + 1) + 1):
        for t in traverse:
            if 0 <= t <= 7 and board.piece_at(chess.square(c, t)) == chess.Piece(chess.PAWN, colore):
                n += 1
    return n


def colonne_aperte_sul_re(board, colore):
    """Colonne aperte/semiaperte per l'avversario adiacenti al re: pericolo."""
    re = board.king(colore)
    if re is None:
        return 0
    aperte, semi_b, semi_n = stato_colonne(board)
    pericolo = set(aperte) | set(semi_n if colore == chess.WHITE else semi_b)
    rc = chess.square_file(re)
    return sum(1 for c in range(max(0, rc - 1), min(7, rc + 1) + 1) if c in pericolo)


def mobilita(board, colore):
    """Case attaccate dai pezzi (non pedoni, non re), escluse quelle occupate da pezzi propri."""
    propri = chess.SquareSet(board.occupied_co[colore])
    totale = 0
    for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        for sq in board.pieces(pt, colore):
            totale += len(board.attacks(sq) - propri)
    return totale


def spazio(board, colore):
    """Case nella meta' avversaria controllate."""
    meta = range(32, 64) if colore == chess.WHITE else range(0, 32)
    return sum(1 for sq in meta if board.is_attacked_by(colore, sq))


def controllo_centro(board, colore):
    return sum(len(board.attackers(colore, sq)) for sq in CENTRO)


def sviluppo(board, colore):
    """Pezzi minori usciti dalla prima traversa (utile in apertura)."""
    base = 0 if colore == chess.WHITE else 7
    fuori = 0
    for pt in (chess.KNIGHT, chess.BISHOP):
        for sq in board.pieces(pt, colore):
            if chess.square_rank(sq) != base:
                fuori += 1
    return fuori


# ---------------------------------------------------------------- fase e materiale

def materiale(board, colore):
    return sum(v * len(board.pieces(pt, colore)) for pt, v in VALORI_PEZZI.items())


def fase_partita(board):
    """1.0 = apertura (tutto il materiale), 0.0 = finale nudo."""
    non_pedoni = sum(
        VALORI_PEZZI[pt] * (len(board.pieces(pt, chess.WHITE)) + len(board.pieces(pt, chess.BLACK)))
        for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
    )
    return round(min(1.0, non_pedoni / 62.0), 3)


# ---------------------------------------------------------------- API principale

def estrai_caratteristiche(board: chess.Board) -> dict:
    """Feature posizionali. Diff = Bianco - Nero (positivo = meglio per il Bianco)."""
    W, B = chess.WHITE, chess.BLACK
    aperte, semi_b, semi_n = stato_colonne(board)

    return {
        # --- globali / simmetriche
        "fase": fase_partita(board),
        "pedoni_bloccati": pedoni_bloccati(board),
        "colonne_aperte": len(aperte),
        "chiusura": pedoni_bloccati(board) * 2 - len(aperte),

        # --- materiale (contesto)
        "materiale_diff": materiale(board, W) - materiale(board, B),

        # --- struttura pedonale (diff: positivo = meglio per il Bianco)
        "doppiati_diff":  pedoni_doppiati(board, B) - pedoni_doppiati(board, W),
        "isolati_diff":   pedoni_isolati(board, B) - pedoni_isolati(board, W),
        "arretrati_diff": pedoni_arretrati(board, B) - pedoni_arretrati(board, W),
        "passati_diff":   pedoni_passati(board, W) - pedoni_passati(board, B),
        "isole_diff":     isole_di_pedoni(board, B) - isole_di_pedoni(board, W),
        "protetti_diff":  pedoni_protetti(board, W) - pedoni_protetti(board, B),

        # --- pezzi
        "coppia_alfieri_diff":  coppia_alfieri(board, W) - coppia_alfieri(board, B),
        "alfiere_cattivo_diff": alfiere_cattivo(board, B) - alfiere_cattivo(board, W),
        "avamposti_diff":       avamposti_cavallo(board, W) - avamposti_cavallo(board, B),
        "torri_aperte_diff":    torri_su_colonne_aperte(board, W) - torri_su_colonne_aperte(board, B),
        "torri_settima_diff":   torri_in_settima(board, W) - torri_in_settima(board, B),

        # --- re
        "scudo_re_diff":    scudo_pedoni_re(board, W) - scudo_pedoni_re(board, B),
        "pericolo_re_diff": colonne_aperte_sul_re(board, B) - colonne_aperte_sul_re(board, W),

        # --- attivita'
        "mobilita_diff": mobilita(board, W) - mobilita(board, B),
        "spazio_diff":   spazio(board, W) - spazio(board, B),
        "centro_diff":   controllo_centro(board, W) - controllo_centro(board, B),
        "sviluppo_diff": sviluppo(board, W) - sviluppo(board, B),
    }


# Feature simmetriche: NON vanno ribaltate per il colore di chi muove
FEATURE_SIMMETRICHE = ("fase", "chiusura", "colonne_aperte", "pedoni_bloccati")

# Descrizioni per il pannello Sparring e i report
DESCRIZIONI = {
    "doppiati_diff": "pedoni doppiati",
    "isolati_diff": "pedoni isolati",
    "arretrati_diff": "pedoni arretrati",
    "passati_diff": "pedoni passati",
    "isole_diff": "isole di pedoni",
    "protetti_diff": "pedoni protetti (catene)",
    "coppia_alfieri_diff": "coppia degli alfieri",
    "alfiere_cattivo_diff": "qualita' degli alfieri (pedoni sul colore dell'alfiere)",
    "avamposti_diff": "avamposti di cavallo",
    "torri_aperte_diff": "torri su colonne aperte/semiaperte",
    "torri_settima_diff": "torri in settima",
    "scudo_re_diff": "scudo di pedoni del re",
    "pericolo_re_diff": "colonne aperte vicino al re",
    "mobilita_diff": "mobilita' dei pezzi",
    "spazio_diff": "spazio",
    "centro_diff": "controllo del centro",
    "sviluppo_diff": "sviluppo",
}

if __name__ == "__main__":
    b = chess.Board()
    for k, v in estrai_caratteristiche(b).items():
        print(f"{k:24s} {v}")
