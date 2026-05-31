"""
Parser PGN (Fase 1).

Funzioni:
- estrai_dati_partita: metadati della PRIMA partita di un file
- estrai_mosse: mosse della PRIMA partita, nel formato del contratto Mossa
- estrai_tutte_le_partite: legge TUTTE le partite di un file (metadati + mosse)
- salva_mosse_json / salva_partite_json: salvataggio in data/

Uso:
  python parser.py partita_esempio.pgn      (una partita)
  python parser.py partite_multiple.pgn     (piu' partite)
"""

import sys
import os
import json
import logging
import chess
import chess.pgn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("engine")

CARTELLA_DATI = os.path.join(os.path.dirname(__file__), "..", "data")


def _leggi_prima_partita(percorso_file):
    with open(percorso_file, "r", encoding="utf-8") as f:
        return chess.pgn.read_game(f)


def _mosse_da_partita(partita):
    """Data una partita gia' letta, restituisce la lista delle sue mosse."""
    board = partita.board()
    mosse = []
    for mossa in partita.mainline_moves():
        mosse.append({
            "uci": mossa.uci(),
            "san": board.san(mossa),
            "fen_before": board.fen(),
        })
        board.push(mossa)
    return mosse


def _metadati_da_partita(partita):
    """Data una partita gia' letta, restituisce i suoi metadati."""
    numero_mosse = sum(1 for _ in partita.mainline_moves())
    return {
        "bianco": partita.headers.get("White", "Sconosciuto"),
        "nero": partita.headers.get("Black", "Sconosciuto"),
        "risultato": partita.headers.get("Result", "?"),
        "numero_mosse": numero_mosse,
    }


def estrai_dati_partita(percorso_file):
    """Metadati della PRIMA partita del file, o None se vuoto."""
    logger.info("Apro il file PGN: %s", percorso_file)
    partita = _leggi_prima_partita(percorso_file)
    if partita is None:
        logger.error("Nessuna partita trovata nel file")
        return None
    logger.info("Metadati letti correttamente")
    return _metadati_da_partita(partita)


def estrai_mosse(percorso_file):
    """Mosse della PRIMA partita del file, o None se vuoto."""
    logger.info("Estraggo le mosse da: %s", percorso_file)
    partita = _leggi_prima_partita(percorso_file)
    if partita is None:
        logger.error("Nessuna partita trovata nel file")
        return None
    mosse = _mosse_da_partita(partita)
    logger.info("Estratte %d mosse", len(mosse))
    return mosse


def estrai_tutte_le_partite(percorso_file):
    """
    Legge TUTTE le partite di un file PGN. Restituisce una lista; ogni
    elemento e' un dizionario con metadati e mosse della partita:
        {"bianco", "nero", "risultato", "numero_mosse", "mosse": [...]}

    Funziona richiamando read_game in un ciclo: legge una partita alla volta
    finche' il file non finisce (read_game restituisce None).
    """
    logger.info("Leggo tutte le partite da: %s", percorso_file)
    partite = []

    with open(percorso_file, "r", encoding="utf-8") as f:
        while True:
            partita = chess.pgn.read_game(f)
            if partita is None:
                break  # niente piu' partite: usciamo dal ciclo
            dati = _metadati_da_partita(partita)
            dati["mosse"] = _mosse_da_partita(partita)
            partite.append(dati)

    logger.info("Lette %d partite", len(partite))
    return partite


def salva_mosse_json(mosse, nome_file):
    """Salva una lista di mosse in data/. Restituisce il percorso."""
    os.makedirs(CARTELLA_DATI, exist_ok=True)
    percorso = os.path.join(CARTELLA_DATI, nome_file)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(mosse, f, indent=2, ensure_ascii=False)
    logger.info("Mosse salvate in: %s", percorso)
    return percorso


def salva_partite_json(partite, nome_file):
    """Salva tutte le partite in data/. Restituisce il percorso."""
    os.makedirs(CARTELLA_DATI, exist_ok=True)
    percorso = os.path.join(CARTELLA_DATI, nome_file)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(partite, f, indent=2, ensure_ascii=False)
    logger.info("Partite salvate in: %s", percorso)
    return percorso


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python parser.py <file.pgn>")
        sys.exit(1)

    percorso = sys.argv[1]
    nome_base = os.path.splitext(os.path.basename(percorso))[0]

    partite = estrai_tutte_le_partite(percorso)
    print()
    print(f"Trovate {len(partite)} partite nel file:")
    for i, p in enumerate(partite, start=1):
        print(f"  {i}. {p['bianco']} vs {p['nero']}  "
              f"({p['risultato']}, {p['numero_mosse']} semimosse)")
    print()

    if partite:
        file_salvato = salva_partite_json(partite, nome_base + "_partite.json")
        print(f"Salvato in: {file_salvato}")
        print()
