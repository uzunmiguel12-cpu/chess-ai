"""
Modulo tattica (Fase 3) - riconoscimento del tipo tattico degli errori.

Tipi riconosciuti (in ordine di priorita'):
- "pezzo_in_presa": dopo la mossa un pezzo di chi ha mosso e' catturabile con
  guadagno (Static Exchange Evaluation > 0).
- "forchetta": l'avversario ha una mossa che porta un suo pezzo ad attaccare
  >=2 pezzi di valore, senza perdere il pezzo.
- "scoperta": la mossa produce uno SCACCO DI SCOPERTA, cioe' togliendo di mezzo
  il pezzo mosso si scopre lo scacco di un proprio pezzo a lungo raggio.
- "inchiodatura": la mossa CREA un'inchiodatura su un proprio pezzo che prima
  non era inchiodato.

Usa una SEE costruita su misura e il metodo is_pinned di python-chess.

Uso (dimostrativo):  python tattica.py
"""

import logging
import chess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

VALORE_PEZZO = {
    chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 100000,
}
PEZZI_BERSAGLIO = {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING}
# Pezzi che attaccano "in linea" e possono quindi infilzare.
PEZZI_LINEA = {chess.BISHOP, chess.ROOK, chess.QUEEN}


def _guadagno_cattura(board, casa, colore):
    """Static Exchange Evaluation su una casa: guadagno netto per 'colore'."""
    attaccanti = board.attackers(colore, casa)
    if not attaccanti:
        return 0
    preda = board.piece_at(casa)
    if preda is None:
        return 0
    casa_attaccante = min(
        attaccanti, key=lambda sq: VALORE_PEZZO[board.piece_at(sq).piece_type]
    )
    valore_preda = VALORE_PEZZO[preda.piece_type]
    nuova = board.copy(stack=False)
    pezzo_attaccante = nuova.piece_at(casa_attaccante)
    nuova.remove_piece_at(casa_attaccante)
    nuova.remove_piece_at(casa)
    nuova.set_piece_at(casa, pezzo_attaccante)
    return max(0, valore_preda - _guadagno_cattura(nuova, casa, not colore))


def trova_pezzo_in_presa(board, colore_vittima):
    """Casa del pezzo piu' prezioso del colore_vittima catturabile con guadagno, o None."""
    avversario = not colore_vittima
    peggiore_casa = None
    peggiore_valore = 0
    for casa in chess.SQUARES:
        pezzo = board.piece_at(casa)
        if pezzo is None or pezzo.color != colore_vittima:
            continue
        if pezzo.piece_type == chess.KING:
            continue  # il re non e' un pezzo "in presa": lo scacco e' altra cosa
        if not board.attackers(avversario, casa):
            continue
        if _guadagno_cattura(board, casa, avversario) > 0:
            if VALORE_PEZZO[pezzo.piece_type] > peggiore_valore:
                peggiore_valore = VALORE_PEZZO[pezzo.piece_type]
                peggiore_casa = casa
    return peggiore_casa


def trova_forchetta(board, colore_vittima):
    """True se l'avversario ha una mossa che forchetta >=2 pezzi di valore."""
    avversario = not colore_vittima
    board_av = board.copy(stack=False)
    board_av.turn = avversario
    for mossa in board_av.legal_moves:
        dopo = board_av.copy(stack=False)
        dopo.push(mossa)
        casa_arrivo = mossa.to_square
        pezzo_mosso = dopo.piece_at(casa_arrivo)
        if pezzo_mosso is None:
            continue
        bersagli = 0
        for casa_att in dopo.attacks(casa_arrivo):
            bersaglio = dopo.piece_at(casa_att)
            if (bersaglio is not None and bersaglio.color == colore_vittima
                    and bersaglio.piece_type in PEZZI_BERSAGLIO):
                bersagli += 1
        if bersagli >= 2:
            perdita = _guadagno_cattura(dopo, casa_arrivo, colore_vittima)
            if perdita < VALORE_PEZZO[pezzo_mosso.piece_type]:
                return True
    return False


def _pezzi_inchiodati(board, colore):
    """Insieme delle case dei pezzi di 'colore' attualmente inchiodati."""
    inchiodati = set()
    for casa in chess.SQUARES:
        p = board.piece_at(casa)
        if p is not None and p.color == colore and board.is_pinned(colore, casa):
            inchiodati.add(casa)
    return inchiodati


def inchiodatura_creata(board_prima, board_dopo, colore_che_muove):
    """
    True se dopo la mossa c'e' un pezzo di 'colore_che_muove' inchiodato che
    PRIMA non lo era: l'inchiodatura e' conseguenza della mossa.
    """
    prima = _pezzi_inchiodati(board_prima, colore_che_muove)
    dopo = _pezzi_inchiodati(board_dopo, colore_che_muove)
    return len(dopo - prima) > 0


def scoperta_creata(board_prima, board_dopo, mossa_uci, colore_che_muove):
    """
    True se la mossa ha prodotto uno SCACCO DI SCOPERTA: dopo la mossa il re
    avversario e' sotto scacco da un mio pezzo a lungo raggio (alfiere/torre/donna)
    DIVERSO dal pezzo che ho mosso, la cui linea verso il re era bloccata PRIMA dal
    pezzo che ho spostato.

    Ci limitiamo di proposito allo SCACCO di scoperta (non la scoperta generica che
    vince materiale): e' la forma netta e priva di falsi positivi.

    Differenziale prima/dopo, come inchiodatura_creata: lo scacco deve essere
    CONSEGUENZA della mossa.
    """
    avversario = not colore_che_muove

    # 1. Dopo la mossa il re avversario DEVE essere sotto scacco (altrimenti non e'
    #    uno scacco di scoperta, e qui ci limitiamo a quello).
    if not board_dopo.is_check() or board_dopo.turn != avversario:
        return False
    casa_re = board_dopo.king(avversario)
    if casa_re is None:
        return False

    # 2. Casa di ARRIVO del pezzo mosso.
    casa_arrivo = chess.Move.from_uci(mossa_uci).to_square

    # 3. Chi da' scacco DOPO la mossa: le case dei miei pezzi che attaccano il re.
    attaccanti = board_dopo.attackers(colore_che_muove, casa_re)

    # 4. E' scoperta se esiste un attaccante a lungo raggio DIVERSO dal pezzo mosso:
    #    il pezzo mosso si e' tolto di mezzo e ha scoperto lo scacco di un altro pezzo.
    #    (Se l'unico che da' scacco e' proprio quello mosso -> scacco diretto, NON
    #    di scoperta.)
    for casa_att in attaccanti:
        if casa_att == casa_arrivo:
            continue
        pezzo = board_dopo.piece_at(casa_att)
        if pezzo is None or pezzo.piece_type not in PEZZI_LINEA:
            continue
        # 5. Sicurezza extra contro i falsi positivi: PRIMA della mossa quel pezzo
        #    NON doveva gia' dare scacco (lo scacco e' conseguenza della mossa).
        if casa_att in board_prima.attackers(colore_che_muove, casa_re):
            continue
        return True
    return False


def _direzione(da_sq, a_sq):
    """Passo unitario (df, dr) da da_sq verso a_sq se sono in linea retta, o None."""
    df = chess.square_file(a_sq) - chess.square_file(da_sq)
    dr = chess.square_rank(a_sq) - chess.square_rank(da_sq)
    if df == 0 and dr == 0:
        return None
    if df == 0:
        return (0, 1 if dr > 0 else -1)
    if dr == 0:
        return (1 if df > 0 else -1, 0)
    if abs(df) == abs(dr):
        return (1 if df > 0 else -1, 1 if dr > 0 else -1)
    return None


def _primo_pezzo_dietro(board, casa_attaccante, casa_davanti):
    """Primo pezzo che sta DIETRO casa_davanti, proseguendo dalla linea
    attaccante->davanti. Restituisce (casa, pezzo) o None."""
    dirz = _direzione(casa_attaccante, casa_davanti)
    if dirz is None:
        return None
    df, dr = dirz
    f = chess.square_file(casa_davanti) + df
    r = chess.square_rank(casa_davanti) + dr
    while 0 <= f < 8 and 0 <= r < 8:
        sq = chess.square(f, r)
        p = board.piece_at(sq)
        if p is not None:
            return (sq, p)
        f += df
        r += dr
    return None


def trova_infilata(board, colore_vittima):
    """
    True se i pezzi del colore_vittima sono in un'infilata: un pezzo nemico in
    linea attacca un pezzo di valore, e DIETRO (stessa linea) c'e' un altro
    pezzo della vittima di valore minore o uguale.
    """
    avversario = not colore_vittima
    for casa_att in chess.SQUARES:
        attaccante = board.piece_at(casa_att)
        if attaccante is None or attaccante.color != avversario:
            continue
        if attaccante.piece_type not in PEZZI_LINEA:
            continue
        for casa_davanti in board.attacks(casa_att):
            davanti = board.piece_at(casa_davanti)
            if davanti is None or davanti.color != colore_vittima:
                continue
            if davanti.piece_type == chess.PAWN:
                continue
            dietro = _primo_pezzo_dietro(board, casa_att, casa_davanti)
            if dietro is None:
                continue
            casa_dietro, pezzo_dietro = dietro
            if pezzo_dietro.color != colore_vittima:
                continue
            if pezzo_dietro.piece_type == chess.PAWN:
                continue
            if VALORE_PEZZO[davanti.piece_type] >= VALORE_PEZZO[pezzo_dietro.piece_type]:
                return True
    return False


def rileva_tipo_tattico(fen_prima, fen_dopo, colore_che_ha_mosso, mossa_uci=None):
    """
    Dato lo stato PRIMA e DOPO una mossa e il colore di chi l'ha giocata,
    RESTITUISCE un'etichetta di tipo tattico, o None.

    Priorita': pezzo in presa, poi forchetta, poi scoperta, poi inchiodatura
    creata, poi infilata. pezzo_in_presa e forchetta restano prioritari perche'
    geometricamente certi; lo scacco di scoperta e' spesso fortissimo ma lo
    teniamo dopo per coerenza con la priorita' esistente.

    mossa_uci serve SOLO alla scoperta (differenziale che richiede la mossa): se
    non viene passata, la scoperta non viene valutata (gli altri pattern restano).
    """
    board_prima = chess.Board(fen_prima)
    board_dopo = chess.Board(fen_dopo)

    if trova_pezzo_in_presa(board_dopo, colore_che_ha_mosso) is not None:
        return "pezzo_in_presa"
    if trova_forchetta(board_dopo, colore_che_ha_mosso):
        return "forchetta"
    if mossa_uci and scoperta_creata(
            board_prima, board_dopo, mossa_uci, colore_che_ha_mosso):
        return "scoperta"
    if inchiodatura_creata(board_prima, board_dopo, colore_che_ha_mosso):
        return "inchiodatura"
    if trova_infilata(board_dopo, colore_che_ha_mosso):
        return "infilata"
    return None


if __name__ == "__main__":
    casi = [
        ("Torre indifesa attaccata",
         "8/8/8/8/8/8/8/4K3 w - - 0 1", "3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1",
         chess.WHITE, "pezzo_in_presa", None),
        ("Forchetta di cavallo",
         "8/8/8/8/8/8/8/4K3 w - - 0 1", "Q3R3/8/n6k/8/8/8/8/7K b - - 0 1",
         chess.WHITE, "forchetta", None),
        ("Scacco di scoperta (Ne4-c5 scopre Re1)",
         "4k3/8/8/8/4N3/8/8/K3R3 w - - 0 1",
         "4k3/8/8/2N5/8/8/8/K3R3 b - - 0 1",
         chess.WHITE, "scoperta", "e4c5"),
        ("Inchiodatura creata (Ng1-e2)",
         "4r3/8/8/8/8/8/8/4K1N1 w - - 0 1", "4r3/8/8/8/8/8/4N3/4K3 b - - 0 1",
         chess.WHITE, "inchiodatura", None),
        ("Posizione iniziale dopo e4",
         chess.STARTING_FEN,
         "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
         chess.WHITE, None, "e2e4"),
    ]
    print()
    print("Esempi di rilevamento tipo tattico:")
    print()
    for descr, fp, fd, colore, atteso, uci in casi:
        ris = rileva_tipo_tattico(fp, fd, colore, uci)
        ok = "OK" if ris == atteso else "DIVERSO"
        print(f"  [{ok}] {descr:32} -> {ris}")
    print()
