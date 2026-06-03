"""
Modulo costruzione database puzzle (Fase 4 / rag).

Legge il CSV dei puzzle di Lichess e li carica in un database SQLite, creando
poi gli indici che rendono veloci le ricerche per Elo e per tema.

SQLite e' un database in un singolo file, gia' incluso in Python: nessun server,
nessuna installazione. Dopo questo passo, le ricerche sui ~6 milioni di puzzle
diventano quasi istantanee.

Si esegue UNA volta sola (qualche minuto). Dopo, il CSV non serve piu'.

Uso:  python costruisci_db.py ..\\data\\lichess_db_puzzle.csv ..\\data\\puzzle.db
"""

import os
import sys
import csv
import sqlite3
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")

# Permettiamo campi CSV molto lunghi (alcune sequenze di mosse lo sono).
csv.field_size_limit(10 * 1024 * 1024)


def costruisci(percorso_csv, percorso_db):
    """
    Crea (o ricrea) il database SQLite dei puzzle a partire dal CSV.
    RESTITUISCE il numero di puzzle caricati.
    """
    if not os.path.exists(percorso_csv):
        logger.error("CSV non trovato: %s", percorso_csv)
        return None

    # Se il db esiste gia', lo rimuoviamo per ripartire pulito.
    if os.path.exists(percorso_db):
        os.remove(percorso_db)
        logger.info("Database precedente rimosso")

    conn = sqlite3.connect(percorso_db)
    cur = conn.cursor()

    # Creiamo la tabella. Teniamo i temi come testo (li cercheremo per contenuto).
    cur.execute("""
        CREATE TABLE puzzle (
            id TEXT PRIMARY KEY,
            fen TEXT NOT NULL,
            moves TEXT NOT NULL,
            rating INTEGER,
            popularity INTEGER,
            nb_plays INTEGER,
            themes TEXT,
            game_url TEXT
        )
    """)

    logger.info("Carico i puzzle dal CSV (puo' richiedere qualche minuto)...")
    inseriti = 0
    with open(percorso_csv, "r", encoding="utf-8", newline="") as f:
        lettore = csv.DictReader(f)
        lotto = []
        for riga in lettore:
            # alcune righe potrebbero avere campi mancanti: gestiamo con .get
            try:
                lotto.append((
                    riga["PuzzleId"],
                    riga["FEN"],
                    riga["Moves"],
                    int(riga["Rating"]) if riga.get("Rating") else None,
                    int(riga["Popularity"]) if riga.get("Popularity") else None,
                    int(riga["NbPlays"]) if riga.get("NbPlays") else None,
                    riga.get("Themes", ""),
                    riga.get("GameUrl", ""),
                ))
            except (ValueError, KeyError):
                continue  # riga malformata: la saltiamo

            # Inseriamo a lotti di 50000 per efficienza.
            if len(lotto) >= 50000:
                cur.executemany(
                    "INSERT OR IGNORE INTO puzzle VALUES (?,?,?,?,?,?,?,?)", lotto)
                inseriti += len(lotto)
                logger.info("  inseriti %d puzzle...", inseriti)
                lotto = []
        # ultimo lotto
        if lotto:
            cur.executemany(
                "INSERT OR IGNORE INTO puzzle VALUES (?,?,?,?,?,?,?,?)", lotto)
            inseriti += len(lotto)

    conn.commit()

    # Indici per ricerche veloci: per rating, e per temi.
    logger.info("Creo gli indici (rating, temi)...")
    cur.execute("CREATE INDEX idx_rating ON puzzle(rating)")
    cur.execute("CREATE INDEX idx_themes ON puzzle(themes)")
    conn.commit()
    conn.close()

    logger.info("Fatto. Puzzle caricati: %d", inseriti)
    return inseriti


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python costruisci_db.py <file.csv> <file.db>")
        sys.exit(1)
    n = costruisci(sys.argv[1], sys.argv[2])
    if n is None:
        sys.exit(1)
    print()
    print(f"Database creato con {n} puzzle: {sys.argv[2]}")
    print("Ora il CSV non serve piu' e puoi cancellarlo per liberare spazio.")
    print()
