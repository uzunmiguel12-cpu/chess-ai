"""
Modulo tattica (Fase 3) - riconoscimento del tipo tattico degli errori.

Tipi riconosciuti:
- "pezzo_in_presa": dopo la mossa, un pezzo di chi ha mosso e' catturabile con
  guadagno di materiale (Static Exchange Evaluation > 0).
- "forchetta": dopo la mossa, l'avversario ha una mossa che porta un suo pezzo
  ad attaccare contemporaneamente >=2 pezzi di valore, senza perdere il pezzo.

Usa una SEE costruita su misura (python-chess non ne offre una pronta).

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
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 100000,
}

# Pezzi che contano come bersaglio di una forchetta (da cavallo in su, piu' il re).
PEZZI_BERSAGLIO = {chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING}


def _guadagno_cattura(board, casa, colore):
    """
    Static Exchange Evaluation su una casa: guadagno netto (centipawn) se
    'colore' inizia a catturare li', con gioco ottimale di entrambi.
    """
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
    guadagno = valore_preda - _guadagno_cattura(nuova, casa, not colore)
    return max(0, guadagno)


def trova_pezzo_in_presa(board, colore_vittima):
    """
    Restituisce la casa del pezzo piu' prezioso del colore_vittima che
    l'avversario puo' catturare con guadagno (SEE > 0), o None.
    """
    avversario = not colore_vittima
    peggiore_casa = None
    peggiore_valore = 0
    for casa in chess.SQUARES:
        pezzo = board.piece_at(casa)
        if pezzo is None or pezzo.color != colore_vittima:
            continue
        if not board.attackers(avversario, casa):
            continue
        if _guadagno_cattura(board, casa, avversario) > 0:
            if VALORE_PEZZO[pezzo.piece_type] > peggiore_valore:
                peggiore_valore = VALORE_PEZZO[pezzo.piece_type]
                peggiore_casa = casa
    return peggiore_casa


def trova_forchetta(board, colore_vittima):
    """
    Cerca se l'avversario del colore_vittima ha una MOSSA che crea una forchetta:
    un suo pezzo che, dopo la mossa, attacca >=2 pezzi di valore del colore_vittima,
    senza essere immediatamente catturabile con perdita (il pezzo forchettante
    non deve valere piu' di quanto si rischi perdendolo).

    RESTITUISCE True se trova una forchetta possibile.
    """
    avversario = not colore_vittima
    board_av = board.copy(stack=False)
    board_av.turn = avversario  # generiamo le mosse dell'avversario

    for mossa in board_av.legal_moves:
        dopo = board_av.copy(stack=False)
        dopo.push(mossa)
        casa_arrivo = mossa.to_square
        pezzo_mosso = dopo.piece_at(casa_arrivo)
        if pezzo_mosso is None:
            continue

        # Quali pezzi di valore della vittima attacca il pezzo appena mosso?
        bersagli = 0
        for casa_att in dopo.attacks(casa_arrivo):
            bersaglio = dopo.piece_at(casa_att)
            if (bersaglio is not None and bersaglio.color == colore_vittima
                    and bersaglio.piece_type in PEZZI_BERSAGLIO):
                bersagli += 1

        if bersagli >= 2:
            # Il pezzo forchettante non deve essere catturabile gratis: se la
            # vittima puo' riprenderlo guadagnandoci, non e' una vera forchetta.
            perdita = _guadagno_cattura(dopo, casa_arrivo, colore_vittima)
            if perdita < VALORE_PEZZO[pezzo_mosso.piece_type]:
                return True
    return False


def rileva_tipo_tattico(fen_dopo_la_mossa, colore_che_ha_mosso):
    """
    Dato lo stato DOPO una mossa e il colore di chi l'ha giocata, RESTITUISCE
    un'etichetta di tipo tattico, o None.

    Priorita': prima il pezzo in presa (errore piu' diretto), poi la forchetta.
    """
    board = chess.Board(fen_dopo_la_mossa)

    if trova_pezzo_in_presa(board, colore_che_ha_mosso) is not None:
        return "pezzo_in_presa"
    if trova_forchetta(board, colore_che_ha_mosso):
        return "forchetta"
    return None


if __name__ == "__main__":
    casi = [
        ("Torre indifesa attaccata",
         "3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1", chess.WHITE, "pezzo_in_presa"),
        ("Forchetta di cavallo (donna+torre)",
         "Q3R3/8/n6k/8/8/8/8/7K b - - 0 1", chess.WHITE, "forchetta"),
        ("Posizione iniziale",
         chess.STARTING_FEN, chess.WHITE, None),
    ]
    print()
    print("Esempi di rilevamento tipo tattico:")
    print()
    for descr, fen, colore, atteso in casi:
        ris = rileva_tipo_tattico(fen, colore)
        ok = "OK" if ris == atteso else "DIVERSO"
        print(f"  [{ok}] {descr:38} -> {ris}")
    print()
