"""
Modulo puzzle (Fase 4) - genera puzzle dalle TUE partite.

Un puzzle e' una posizione dove hai sbagliato (mistake o blunder) + la mossa
giusta che Stockfish suggeriva. Scorre le partite arricchite in data/categorie/,
estrae gli errori del giocatore indicato e li impacchetta come esercizi
"trova la mossa migliore".

I puzzle possono essere filtrati per fase (es. la tua debolezza, il mediogioco)
e per tipo tattico (es. solo le forchette mancate).

Uso:
    python puzzle.py "MigueL_uz"
    python puzzle.py "MigueL_uz" --fase mediogioco
    python puzzle.py "MigueL_uz" --tipo forchetta
"""

import os
import sys
import json
import glob
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

CARTELLA_CATEGORIE = os.path.join(
    os.path.dirname(__file__), "..", "data", "categorie"
)

GRAVITA_PUZZLE = {"mistake", "blunder"}


def _normalizza(nome):
    return nome.strip().lower()


def _mosse_del_giocatore(dato_partita, nome_norm):
    """Mosse giocate dal giocatore in questa partita (pari=Bianco, dispari=Nero)."""
    bianco = _normalizza(dato_partita.get("bianco", ""))
    nero = _normalizza(dato_partita.get("nero", ""))
    if nome_norm == bianco:
        colore_pari = True
    elif nome_norm == nero:
        colore_pari = False
    else:
        return []
    risultato = []
    for i, mossa in enumerate(dato_partita["mosse"]):
        e_del_giocatore = (i % 2 == 0) if colore_pari else (i % 2 == 1)
        if e_del_giocatore:
            risultato.append(mossa)
    return risultato


def genera_puzzle(nome, cartella=CARTELLA_CATEGORIE, fase=None, tipo_tattico=None):
    """
    Genera la lista dei puzzle per il giocatore indicato.

    Filtri opzionali:
      - fase: "apertura" | "mediogioco" | "finale"
      - tipo_tattico: "pezzo_in_presa" | "forchetta" | "inchiodatura" | "infilata"

    RESTITUISCE una lista di dizionari-puzzle, ognuno con:
      fen, soluzione (best_move_uci), tua_mossa, gravita, fase, tipo_tattico,
      partita (file di provenienza).
    Scarta gli errori senza soluzione (best_move_uci mancante).
    """
    nome_norm = _normalizza(nome)
    if not os.path.isdir(cartella):
        logger.error("Cartella categorie non trovata: %s", cartella)
        return []

    file_partite = sorted(glob.glob(os.path.join(cartella, "*.json")))
    puzzle = []

    for percorso in file_partite:
        with open(percorso, "r", encoding="utf-8") as f:
            dato = json.load(f)
        for mossa in _mosse_del_giocatore(dato, nome_norm):
            if mossa.get("gravita") not in GRAVITA_PUZZLE:
                continue
            soluzione = mossa.get("best_move_uci")
            if not soluzione:
                continue  # niente soluzione -> non e' un puzzle valido
            if fase is not None and mossa.get("fase") != fase:
                continue
            if tipo_tattico is not None and mossa.get("tipo_tattico") != tipo_tattico:
                continue
            puzzle.append({
                "fen": mossa["fen"],
                "soluzione": soluzione,
                "tua_mossa": mossa.get("san"),
                "gravita": mossa.get("gravita"),
                "fase": mossa.get("fase"),
                "tipo_tattico": mossa.get("tipo_tattico"),
                "partita": os.path.basename(percorso),
            })

    logger.info("Generati %d puzzle per '%s' (fase=%s, tipo=%s)",
                len(puzzle), nome, fase, tipo_tattico)
    return puzzle


def _parse_args(argv):
    """Parsing semplice: nome obbligatorio, --fase e --tipo opzionali."""
    if not argv:
        return None, None, None
    nome = argv[0]
    fase = None
    tipo = None
    i = 1
    while i < len(argv) - 1:
        if argv[i] == "--fase":
            fase = argv[i + 1]
        elif argv[i] == "--tipo":
            tipo = argv[i + 1]
        i += 2
    return nome, fase, tipo


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python puzzle.py "Nome" [--fase mediogioco] [--tipo forchetta]')
        sys.exit(1)

    nome, fase, tipo = _parse_args(sys.argv[1:])
    puzzle = genera_puzzle(nome, fase=fase, tipo_tattico=tipo)

    if not puzzle:
        print("\nNessun puzzle trovato con questi filtri.\n")
        sys.exit(0)

    print()
    print(f"=== {len(puzzle)} puzzle per {nome} ===")
    if fase:
        print(f"    (filtro fase: {fase})")
    if tipo:
        print(f"    (filtro tipo: {tipo})")
    print()
    # Mostriamo i primi 5 come anteprima.
    for i, p in enumerate(puzzle[:5], 1):
        print(f"Puzzle {i} - da {p['partita']} ({p['fase']}, {p['gravita']})")
        print(f"  Posizione: {p['fen']}")
        print(f"  Tu giocasti: {p['tua_mossa']}  |  Mossa giusta: {p['soluzione']}")
        if p['tipo_tattico']:
            print(f"  Tema tattico: {p['tipo_tattico']}")
        print()
    if len(puzzle) > 5:
        print(f"... e altri {len(puzzle) - 5} puzzle.")
    print()
