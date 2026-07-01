"""
Orchestratore della pipeline dati (flusso A) - chess-ai.

Esegue in sequenza i passi che oggi lanci a mano:
  1) analisi Stockfish delle partite   (engine/analisi_database.py)  [LENTO, locale, incrementale]
  2) arricchimento con le categorie     (ml/arricchisci.py)          [veloce, rigenerabile]
  3) riepilogo del profilo aggiornato   (ml/profilo.py)              [sola lettura]

NON riavvia il backend: quello lo fai con  scripts\\riavvia_backend.bat  (scelta separata),
cosi' questo script non tocca mai il processo del server.

Il passo 1 e' INCREMENTALE: analisi_database.py salta le partite gia' analizzate (un file
JSON per partita in data/analisi/), quindi rilanciarlo e' sicuro e veloce: analizza solo il
nuovo. Il passo 2 rigenera data/categorie/ da zero (e' veloce, e' voluto).

Uso (dalla radice del progetto, con la venv attiva):
    python scripts\\aggiorna_pipeline.py
    python scripts\\aggiorna_pipeline.py --pgn data\\mie_partite.pgn --pgn data\\bullet.pgn
    python scripts\\aggiorna_pipeline.py --giocatore MigueL_uz --profondita 15

Note oneste (scope "Core"):
  - NON scarica le partite (il download resta manuale) e NON deduplica: analizza i PGN che
    gli passi cosi' come sono.
  - NON esegue i test: dopo, verifica a mano con  python -m pytest ml api -q
  - Il bullet e' incluso nell'analisi (data\\bullet.pgn) perche' il profilo tattico lo usa;
    le diagnosi che escludono il bullet lo fanno gia' a valle, nel codice. Se non vuoi il
    bullet, passa solo --pgn data\\mie_partite.pgn.
"""

import argparse
import os
import subprocess
import sys
import time

# La radice del progetto e' la cartella che contiene questo file diviso "scripts".
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PGN analizzati di default: quelli che esistono davvero fra questi due.
PGN_DEFAULT = [
    os.path.join("data", "mie_partite.pgn"),
    os.path.join("data", "bullet.pgn"),
]

# Nome del giocatore per il riepilogo del profilo. Coerente col backend
# (api/server.py usa la stessa variabile d'ambiente, default "MigueL_uz").
GIOCATORE_DEFAULT = os.environ.get("CHESS_PLAYER", "MigueL_uz")


def _esegui(descrizione, argv, cwd):
    """
    Lancia un sottoprocesso mostrando cosa fa e quanto ci mette. Se fallisce,
    stampa un messaggio chiaro e RESTITUISCE False (lo script si ferma li').
    Usa sys.executable: cosi' resta nella stessa venv con cui e' stato avviato.
    """
    print(f"\n=== {descrizione} ===")
    print(f"    comando: {' '.join(argv)}   (in {cwd})")
    inizio = time.time()
    esito = subprocess.run([sys.executable, *argv], cwd=cwd)
    durata = time.time() - inizio
    if esito.returncode != 0:
        print(f"!!! FALLITO ({descrizione}) - codice {esito.returncode}, dopo {durata:.1f}s")
        return False
    print(f"    ok in {durata:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(description="Pipeline dati chess-ai (flusso A, scope Core)")
    parser.add_argument(
        "--pgn", action="append", default=None,
        help="Percorso di un PGN da analizzare (ripetibile). Default: mie_partite.pgn + bullet.pgn se esistono.",
    )
    parser.add_argument(
        "--giocatore", default=GIOCATORE_DEFAULT,
        help=f"Nome del giocatore per il riepilogo profilo (default: {GIOCATORE_DEFAULT}).",
    )
    parser.add_argument(
        "--profondita", type=int, default=15,
        help="Profondita' Stockfish per l'analisi (default: 15, come il resto del progetto).",
    )
    args = parser.parse_args()

    engine_dir = os.path.join(RADICE, "engine")
    ml_dir = os.path.join(RADICE, "ml")

    # Quali PGN? Se non specificati, prendiamo quelli che ESISTONO davvero.
    if args.pgn:
        pgn_relativi = args.pgn
    else:
        pgn_relativi = [p for p in PGN_DEFAULT if os.path.exists(os.path.join(RADICE, p))]

    if not pgn_relativi:
        print("Nessun PGN da analizzare. Passa --pgn <percorso> oppure metti i file in data/.")
        return 1

    print("Pipeline dati chess-ai (flusso A) - scope Core, NIENTE restart del backend.")
    print(f"Radice progetto : {RADICE}")
    print(f"Giocatore       : {args.giocatore}")
    print(f"Profondita'     : {args.profondita}")
    print(f"PGN da analizzare: {', '.join(pgn_relativi)}")

    # --- Passo 1: analisi Stockfish (incrementale) su ogni PGN ---
    for pgn in pgn_relativi:
        pgn_abs = pgn if os.path.isabs(pgn) else os.path.join(RADICE, pgn)
        if not os.path.exists(pgn_abs):
            print(f"!!! PGN non trovato, salto: {pgn_abs}")
            continue
        ok = _esegui(
            f"Passo 1 - analisi Stockfish: {pgn}",
            ["analisi_database.py", pgn_abs, str(args.profondita)],
            cwd=engine_dir,
        )
        if not ok:
            return 1

    # --- Passo 2: arricchimento (rigenera data/categorie/) ---
    if not _esegui("Passo 2 - arricchimento categorie", ["arricchisci.py"], cwd=ml_dir):
        return 1

    # --- Passo 3: riepilogo del profilo (sola lettura) ---
    if not _esegui(
        "Passo 3 - riepilogo profilo",
        ["profilo.py", args.giocatore],
        cwd=ml_dir,
    ):
        return 1

    print("\n=== Pipeline completata ===")
    print("Prossimo passo (a mano, come da tua scelta):")
    print("  1) riavvia il backend:   scripts\\riavvia_backend.bat")
    print("  2) verifica i test:      python -m pytest ml api -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
