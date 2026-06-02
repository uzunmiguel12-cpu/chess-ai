"""
Modulo tattica (Fase 3) - riconoscimento del tipo tattico degli errori.

Primo tipo implementato: "pezzo_in_presa" (hanging piece).
Dopo una mossa, controlla se la posizione lascia un pezzo del giocatore che
ha appena mosso catturabile dall'avversario con guadagno di materiale.

Usa una Static Exchange Evaluation (SEE) costruita su misura: simula la catena
ottimale di catture su una casa e calcola il bilancio di materiale. python-chess
non offre una SEE pronta, quindi la implementiamo coi suoi mattoni (attackers).

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

# Valori dei pezzi in centipawn. Il re ha valore enorme: non si "scambia".
VALORE_PEZZO = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 100000,
}


def _guadagno_cattura(board, casa, colore):
    """
    Static Exchange Evaluation su una singola casa.

    Calcola il guadagno netto di materiale (in centipawn) se 'colore' inizia
    a catturare sulla 'casa', assumendo che entrambi i lati giochino in modo
    ottimale e catturino solo finche' conviene.

    Funziona ricorsivamente: si cattura sempre con l'attaccante di minor valore,
    poi si lascia rispondere l'avversario; ogni lato puo' fermarsi (da cui il
    max(0, ...)), perche' nessuno e' obbligato a una cattura svantaggiosa.
    """
    attaccanti = board.attackers(colore, casa)
    if not attaccanti:
        return 0
    preda = board.piece_at(casa)
    if preda is None:
        return 0

    # Cattura ottimale: con il pezzo attaccante di minor valore.
    casa_attaccante = min(
        attaccanti, key=lambda sq: VALORE_PEZZO[board.piece_at(sq).piece_type]
    )
    valore_preda = VALORE_PEZZO[preda.piece_type]

    # Simuliamo la cattura su una copia della scacchiera.
    nuova = board.copy(stack=False)
    pezzo_attaccante = nuova.piece_at(casa_attaccante)
    nuova.remove_piece_at(casa_attaccante)
    nuova.remove_piece_at(casa)
    nuova.set_piece_at(casa, pezzo_attaccante)

    # Guadagno = valore catturato meno quanto l'avversario recupera rispondendo.
    guadagno = valore_preda - _guadagno_cattura(nuova, casa, not colore)
    return max(0, guadagno)


def trova_pezzo_in_presa(board, colore_vittima):
    """
    Controlla se il 'colore_vittima' ha almeno un pezzo che l'avversario puo'
    catturare guadagnando materiale (SEE > 0).

    RESTITUISCE la casa del pezzo in presa di valore piu' alto (per segnalare
    l'errore piu' grave), oppure None se nessun pezzo e' in presa.
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
        guadagno = _guadagno_cattura(board, casa, avversario)
        if guadagno > 0 and VALORE_PEZZO[pezzo.piece_type] > peggiore_valore:
            peggiore_valore = VALORE_PEZZO[pezzo.piece_type]
            peggiore_casa = casa

    return peggiore_casa


def rileva_tipo_tattico(fen_dopo_la_mossa, colore_che_ha_mosso):
    """
    Dato lo stato DOPO una mossa e il colore di chi l'ha giocata, RESTITUISCE
    un'etichetta di tipo tattico, o None se non rileva nulla di noto.

    Per ora riconosce solo "pezzo_in_presa": chi ha mosso ha lasciato un proprio
    pezzo catturabile con guadagno dall'avversario.
    """
    board = chess.Board(fen_dopo_la_mossa)
    casa_in_presa = trova_pezzo_in_presa(board, colore_che_ha_mosso)
    if casa_in_presa is not None:
        return "pezzo_in_presa"
    return None


if __name__ == "__main__":
    casi = [
        ("Torre indifesa attaccata",
         "3rk3/8/8/3R4/8/8/8/5K2 b - - 0 1", chess.WHITE, "pezzo_in_presa"),
        ("Torre difesa da pari (scambio)",
         "3rk3/8/8/3R4/8/8/8/3R1K2 b - - 0 1", chess.WHITE, None),
        ("Posizione iniziale",
         chess.STARTING_FEN, chess.WHITE, None),
    ]
    print()
    print("Esempi di rilevamento tipo tattico:")
    print()
    for descr, fen, colore, atteso in casi:
        ris = rileva_tipo_tattico(fen, colore)
        ok = "OK" if ris == atteso else "DIVERSO"
        print(f"  [{ok}] {descr:35} -> {ris}")
    print()
