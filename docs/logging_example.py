"""
Esempio di configurazione del logging per il progetto chess-ai.

Questo file e' un MODELLO da copiare quando si scrivono i moduli veri.
Non fa parte della logica dell'applicazione: mostra solo come configurare
e usare il logging in modo uniforme.

Per provarlo:  python logging_example.py
"""

import logging

# Configurazione standard del logging, uguale per tutti i moduli.
# Il formato e':  data e ora | livello | nome modulo | messaggio
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Ogni modulo crea il proprio logger col proprio nome.
# Qui usiamo "engine" come esempio; nei moduli veri sara' "ml", "rag", ecc.
logger = logging.getLogger("engine")


def esempio():
    """Mostra i tre livelli di log che si usano nel progetto."""
    logger.info("Avvio analisi partita")
    logger.info("Analizzate 50 posizioni")
    logger.warning("Partita senza tag Date, proseguo lo stesso")
    logger.error("Impossibile contattare Stockfish")


if __name__ == "__main__":
    esempio()
