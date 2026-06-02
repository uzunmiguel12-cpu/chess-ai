"""
Modulo arricchimento (Fase 3) - aggiunge le categorie alle partite analizzate.

Legge i file di analisi grezza da data/analisi/ (prodotti dal motore in Fase 2),
passa ogni mossa attraverso categorizza_mossa (gravita + fase), e salva il
risultato arricchito in data/categorie/.

Tiene separati i due stadi: l'analisi grezza (costosa, richiede Stockfish) e
le categorie (rigenerabili in un attimo se cambiano le soglie).

Uso:  python arricchisci.py
"""

import os
import json
import glob
import logging

from categorizza import categorizza_mossa

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

# Cartelle: l'analisi grezza in entrata, le categorie in uscita.
CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)
CARTELLA_CATEGORIE = os.path.join(
    os.path.dirname(__file__), "..", "data", "categorie"
)


def arricchisci_partita(dato_partita):
    """
    Dato il contenuto di una partita analizzata (dizionario con 'mosse'),
    RESTITUISCE lo stesso dato con ogni mossa arricchita di gravita/fase.
    Mantiene i metadati (bianco, nero, risultato).
    """
    arricchito = dict(dato_partita)  # copia dei metadati
    arricchito["mosse"] = [categorizza_mossa(m) for m in dato_partita["mosse"]]
    return arricchito


def arricchisci_tutte(cartella_in=CARTELLA_ANALISI, cartella_out=CARTELLA_CATEGORIE):
    """
    Legge tutti i file di analisi in data/analisi/, li arricchisce con le
    categorie, e salva i risultati in data/categorie/ con lo stesso nome.

    RESTITUISCE il numero di file arricchiti.
    """
    if not os.path.isdir(cartella_in):
        logger.error("Cartella analisi non trovata: %s", cartella_in)
        return 0

    os.makedirs(cartella_out, exist_ok=True)

    file_analisi = sorted(glob.glob(os.path.join(cartella_in, "*.json")))
    logger.info("Trovati %d file da arricchire", len(file_analisi))

    arricchiti = 0
    for percorso_in in file_analisi:
        nome = os.path.basename(percorso_in)
        with open(percorso_in, "r", encoding="utf-8") as f:
            dato = json.load(f)

        dato_arricchito = arricchisci_partita(dato)

        percorso_out = os.path.join(cartella_out, nome)
        with open(percorso_out, "w", encoding="utf-8") as f:
            json.dump(dato_arricchito, f, indent=2, ensure_ascii=False)

        logger.info("Arricchito: %s", nome)
        arricchiti += 1

    logger.info("Fatto. File arricchiti: %d", arricchiti)
    return arricchiti


if __name__ == "__main__":
    n = arricchisci_tutte()
    print()
    print(f"Partite arricchite con le categorie: {n}")
    print(f"Risultati in: data/categorie/")
    print()
