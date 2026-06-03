"""
Utility (Fase 4 / rag) - decomprime il file dei puzzle di Lichess (.zst).

Il file lichess_db_puzzle.csv.zst e' compresso in Zstandard. Questo script lo
decomprime "a flusso" (a pezzi), senza caricarlo tutto in memoria, e mostra
quanti megabyte ha scritto man mano.

Uso:  python decomprimi_puzzle.py ..\\data\\lichess_db_puzzle.csv.zst ..\\data\\lichess_db_puzzle.csv
"""

import os
import sys
import logging
import zstandard as zstd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")


def decomprimi(percorso_in, percorso_out):
    """
    Decomprime un file .zst in un file di testo, leggendo e scrivendo a blocchi.
    RESTITUISCE il numero di byte scritti.
    """
    if not os.path.exists(percorso_in):
        logger.error("File compresso non trovato: %s", percorso_in)
        return None

    dimensione_in = os.path.getsize(percorso_in)
    logger.info("File compresso: %.1f MB", dimensione_in / 1024 / 1024)

    scritti = 0
    dctx = zstd.ZstdDecompressor()
    with open(percorso_in, "rb") as fin, open(percorso_out, "wb") as fout:
        # stream_reader legge il compresso a pezzi e li decomprime al volo.
        with dctx.stream_reader(fin) as reader:
            while True:
                blocco = reader.read(16384)  # 16 KB per volta
                if not blocco:
                    break
                fout.write(blocco)
                scritti += len(blocco)
                # progresso ogni ~50 MB
                if scritti % (50 * 1024 * 1024) < 16384:
                    logger.info("  scritti %.0f MB...", scritti / 1024 / 1024)

    logger.info("Fatto. File decompresso: %.1f MB in %s",
                scritti / 1024 / 1024, percorso_out)
    return scritti


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python decomprimi_puzzle.py <file.zst> <file_out.csv>")
        sys.exit(1)

    n = decomprimi(sys.argv[1], sys.argv[2])
    if n is None:
        sys.exit(1)
    print()
    print(f"Decompressione completata: {n / 1024 / 1024:.1f} MB")
    print(f"File pronto: {sys.argv[2]}")
    print()
