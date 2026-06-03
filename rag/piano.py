"""
Modulo piano di allenamento (Fase 4) - collega automaticamente profilo e puzzle.

Legge il profilo di debolezze del giocatore e costruisce un PIANO di allenamento:
una sequenza di "blocchi", ognuno mirato a una combinazione motivo-tattico + fase
dove il giocatore sbaglia, ordinati per frequenza dell'errore (prima le debolezze
piu' gravi). Per ogni blocco pesca i puzzle dal database di Lichess.

I blocchi con troppo pochi puzzle disponibili vengono segnalati/saltati.

Unisce ml/ (profilo) e rag/ (raccomandazione sul database puzzle).

Uso:
    python piano.py "MigueL_uz" ..\\data\\puzzle.db
    python piano.py "MigueL_uz" ..\\data\\puzzle.db --elo-min 1050 --elo-max 1250
"""

import os
import sys
import logging

# Il profilo vive nel cassetto ml/: aggiungiamo quel percorso per importarlo.
_QUI = os.path.dirname(os.path.abspath(__file__))
_ML = os.path.join(_QUI, "..", "ml")
if _ML not in sys.path:
    sys.path.insert(0, _ML)

from profilo import costruisci_profilo  # noqa: E402
from raccomanda import raccomanda, FASE_LICHESS, MOTIVO_LICHESS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")

# Un blocco con meno puzzle di questa soglia viene considerato "troppo scarno".
MIN_PUZZLE_BLOCCO = 5


def _combinazioni_per_frequenza(profilo):
    """
    Dal profilo estrae le combinazioni (motivo, fase, conteggio) ordinate per
    conteggio decrescente. Usa tattico_per_fase: per ogni motivo, in ogni fase,
    quante volte e' capitato.
    """
    combinazioni = []
    tattico_per_fase = profilo.get("tattico_per_fase", {})
    for motivo, per_fase in tattico_per_fase.items():
        for fase, conteggio in per_fase.items():
            if conteggio > 0:
                combinazioni.append((motivo, fase, conteggio))
    # ordina per conteggio decrescente (la debolezza piu' frequente prima)
    combinazioni.sort(key=lambda c: c[2], reverse=True)
    return combinazioni


def costruisci_piano(nome, percorso_db, cartella_categorie=None,
                     elo_min=1050, elo_max=1250, puzzle_per_blocco=10,
                     max_blocchi=6):
    """
    Costruisce il piano di allenamento per il giocatore.

    RESTITUISCE un dizionario con:
      - giocatore, debolezza_fase (la fase peggiore per tasso)
      - blocchi: lista ordinata, ognuno con motivo, fase, conteggio_errori,
        n_puzzle, puzzle (lista dal database)
    I blocchi senza abbastanza puzzle nel database vengono saltati (segnalati).
    """
    # 1. Profilo del giocatore.
    if cartella_categorie:
        profilo = costruisci_profilo(nome, cartella_categorie)
    else:
        profilo = costruisci_profilo(nome)
    if profilo is None:
        logger.error("Nessun profilo per '%s'", nome)
        return None

    # 2. Combinazioni motivo+fase ordinate per frequenza.
    combinazioni = _combinazioni_per_frequenza(profilo)
    if not combinazioni:
        logger.warning("Nessuna debolezza tattica rilevata nel profilo")

    # 3. Per ogni combinazione, un blocco di puzzle dal database.
    blocchi = []
    for motivo, fase, conteggio in combinazioni:
        # saltiamo motivi/fasi non mappabili sui temi Lichess
        if motivo not in MOTIVO_LICHESS or fase not in FASE_LICHESS:
            continue
        puzzle = raccomanda(percorso_db, fase=fase, motivo=motivo,
                            elo_min=elo_min, elo_max=elo_max,
                            quanti=puzzle_per_blocco)
        if len(puzzle) < MIN_PUZZLE_BLOCCO:
            logger.info("Blocco %s/%s saltato: solo %d puzzle disponibili",
                        motivo, fase, len(puzzle))
            continue
        blocchi.append({
            "motivo": motivo,
            "fase": fase,
            "conteggio_errori": conteggio,
            "n_puzzle": len(puzzle),
            "puzzle": puzzle,
        })
        if len(blocchi) >= max_blocchi:
            break

    return {
        "giocatore": nome,
        "debolezza_fase": profilo.get("debolezza_principale"),
        "blocchi": blocchi,
    }


def _parse_args(argv):
    nome = argv[0]
    db = argv[1]
    elo_min, elo_max = 1050, 1250
    categorie = None
    i = 2
    while i < len(argv) - 1:
        if argv[i] == "--elo-min":
            elo_min = int(argv[i + 1])
        elif argv[i] == "--elo-max":
            elo_max = int(argv[i + 1])
        elif argv[i] == "--categorie":
            categorie = argv[i + 1]
        i += 2
    return nome, db, elo_min, elo_max, categorie


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Uso: python piano.py "Nome" <puzzle.db> [--elo-min 1050] [--elo-max 1250]')
        sys.exit(1)

    nome, db, elo_min, elo_max, categorie = _parse_args(sys.argv[1:])
    piano = costruisci_piano(nome, db, cartella_categorie=categorie,
                             elo_min=elo_min, elo_max=elo_max)

    if piano is None:
        print(f"\nNessun profilo trovato per '{nome}'.\n")
        sys.exit(1)

    print()
    print(f"=== Piano di allenamento per {piano['giocatore']} ===")
    print(f"Debolezza di fase principale: {piano['debolezza_fase']}")
    print(f"Blocchi nel piano: {len(piano['blocchi'])}")
    print()
    for i, b in enumerate(piano["blocchi"], 1):
        motivo_it = b["motivo"].replace("_", " ")
        print(f"Blocco {i}: {motivo_it} nel {b['fase']}")
        print(f"  (hai sbagliato cosi' {b['conteggio_errori']} volte; "
              f"{b['n_puzzle']} puzzle pronti)")
        # anteprima primi 3 puzzle del blocco
        for p in b["puzzle"][:3]:
            print(f"    - [{p['rating']}] {p['id']}  ({p['themes']})")
        print()
