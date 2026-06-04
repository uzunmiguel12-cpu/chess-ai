"""
Modulo raccomandazione puzzle (Fase 4 / rag).

Collega il profilo di debolezze al database dei puzzle di Lichess: dato un tema
(fase e/o motivo tattico) e una fascia di Elo, pesca dal database i puzzle
adatti su cui allenarsi.

Traduce i nomi italiani delle nostre categorie nei temi inglesi di Lichess:
  fase:   apertura->opening, mediogioco->middlegame, finale->endgame
  motivo: pezzo_in_presa->hangingPiece, forchetta->fork,
          inchiodatura->pin, infilata->skewer

Uso:
    python raccomanda.py ..\\data\\puzzle.db --fase mediogioco
    python raccomanda.py ..\\data\\puzzle.db --fase mediogioco --tema forchetta --elo-min 1050 --elo-max 1250
"""

import os
import sys
import sqlite3
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")

# Traduzione dalle nostre categorie ai temi di Lichess.
FASE_LICHESS = {
    "apertura": "opening",
    "mediogioco": "middlegame",
    "finale": "endgame",
}
MOTIVO_LICHESS = {
    "pezzo_in_presa": "hangingPiece",
    "forchetta": "fork",
    "inchiodatura": "pin",
    "infilata": "skewer",
}


def raccomanda(percorso_db, fase=None, motivo=None,
               elo_min=1050, elo_max=1250, quanti=10, escludi_id=None):
    """
    Pesca dal database puzzle nella fascia di Elo indicata, filtrando per i temi
    corrispondenti a fase e/o motivo tattico.

    RESTITUISCE una lista di dizionari-puzzle (id, fen, moves, rating, themes).
    Ordinati a caso (per varieta'). Esclude gli ID in escludi_id (gia' visti).
    """
    if not os.path.exists(percorso_db):
        logger.error("Database puzzle non trovato: %s", percorso_db)
        return []

    # Costruiamo i filtri sui temi (LIKE perche' i temi sono testo unico).
    condizioni = ["rating BETWEEN ? AND ?"]
    parametri = [elo_min, elo_max]

    if fase is not None:
        tema_fase = FASE_LICHESS.get(fase)
        if tema_fase is None:
            logger.error("Fase sconosciuta: %s", fase)
            return []
        condizioni.append("themes LIKE ?")
        parametri.append(f"%{tema_fase}%")

    if motivo is not None:
        tema_motivo = MOTIVO_LICHESS.get(motivo)
        if tema_motivo is None:
            logger.error("Motivo tattico sconosciuto: %s", motivo)
            return []
        condizioni.append("themes LIKE ?")
        parametri.append(f"%{tema_motivo}%")

    # Escludiamo i puzzle gia' visti (per non riproporli mai).
    if escludi_id:
        segnaposto = ",".join("?" for _ in escludi_id)
        condizioni.append(f"id NOT IN ({segnaposto})")
        parametri.extend(escludi_id)

    # Varieta' SENZA lentezza: invece di ORDER BY RANDOM() su tutta la tabella
    # (lentissimo su milioni di righe), prima limitiamo a un sottoinsieme di
    # candidati, poi mescoliamo solo quelli. ~200x piu' veloce.
    SOTTOINSIEME = 5000
    query = (
        "SELECT id, fen, moves, rating, themes FROM ("
        + "SELECT id, fen, moves, rating, themes FROM puzzle WHERE "
        + " AND ".join(condizioni)
        + f" LIMIT {SOTTOINSIEME}"
        + ") ORDER BY RANDOM() LIMIT ?"
    )
    parametri.append(quanti)

    conn = sqlite3.connect(percorso_db)
    cur = conn.cursor()
    cur.execute(query, parametri)
    righe = cur.fetchall()
    conn.close()

    puzzle = [
        {"id": r[0], "fen": r[1], "moves": r[2], "rating": r[3], "themes": r[4]}
        for r in righe
    ]
    logger.info("Trovati %d puzzle (fase=%s, motivo=%s, Elo %d-%d)",
                len(puzzle), fase, motivo, elo_min, elo_max)
    return puzzle


def _parse_args(argv):
    db = argv[0]
    opzioni = {"fase": None, "motivo": None, "elo_min": 1050, "elo_max": 1250}
    i = 1
    while i < len(argv) - 1:
        if argv[i] == "--fase":
            opzioni["fase"] = argv[i + 1]
        elif argv[i] == "--tema":
            opzioni["motivo"] = argv[i + 1]
        elif argv[i] == "--elo-min":
            opzioni["elo_min"] = int(argv[i + 1])
        elif argv[i] == "--elo-max":
            opzioni["elo_max"] = int(argv[i + 1])
        i += 2
    return db, opzioni


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python raccomanda.py <puzzle.db> [--fase mediogioco] '
              '[--tema forchetta] [--elo-min 1050] [--elo-max 1250]')
        sys.exit(1)

    db, opz = _parse_args(sys.argv[1:])
    puzzle = raccomanda(db, fase=opz["fase"], motivo=opz["motivo"],
                        elo_min=opz["elo_min"], elo_max=opz["elo_max"])

    if not puzzle:
        print("\nNessun puzzle trovato con questi filtri.\n")
        sys.exit(0)

    print()
    print(f"=== {len(puzzle)} puzzle consigliati ===")
    if opz["fase"]:
        print(f"    fase: {opz['fase']}")
    if opz["motivo"]:
        print(f"    tema: {opz['motivo']}")
    print(f"    fascia Elo: {opz['elo_min']}-{opz['elo_max']}")
    print()
    for i, p in enumerate(puzzle, 1):
        print(f"{i}. [{p['rating']}] {p['id']}  temi: {p['themes']}")
    print()
