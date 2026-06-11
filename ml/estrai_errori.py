"""
Modulo estrazione errori - SOLA LETTURA, NON usa Stockfish.

Legge tutti i file data/analisi/*.json (prodotti da engine/analisi_database.py),
estrae le posizioni in cui ho sbagliato IO (username "MigueL_uz", confronto
case-insensitive) e conta quanti candidati-puzzle ci sono a diverse soglie di
centipawn loss.

Per evitare puzzle "finti" applica un filtro di sanita': scarta le posizioni in
cui ero gia' perso a fondo o gia' stravincente (e i mate-score fasulli).

I candidati con centipawn_loss >= 200 vengono salvati in
data/candidati_errori.json.

Uso:  python ml/estrai_errori.py
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

# Mio username su Lichess (confronto sempre case-insensitive).
USERNAME = "MigueL_uz"

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)
PERCORSO_OUTPUT = os.path.join(
    os.path.dirname(__file__), "..", "data", "candidati_errori.json"
)

# Soglie di centipawn loss su cui contare i candidati.
SOGLIE = [100, 200, 300]
# Soglia minima per salvare un candidato su file.
SOGLIA_SALVATAGGIO = 200

# Confini del filtro di sanita' (centipawn, dal MIO punto di vista).
LIMITE_PERSO = -700      # sotto questo ero gia' perso a fondo
LIMITE_VINCENTE = 700    # sopra questo gia' vincevo facile
SOGLIA_MATTO = 100000    # |eval| >= di questo e' un mate-score (fasullo per ora)


def _normalizza(nome):
    """Normalizza un nome per il confronto case-insensitive."""
    return nome.strip().lower()


def mio_colore(dato_partita, nome=USERNAME):
    """
    Determina il mio colore nella partita confrontando i nomi (case-insensitive).
    Restituisce "w" se gioco col Bianco, "b" se col Nero, None se non gioco.
    """
    nome_norm = _normalizza(nome)
    if _normalizza(dato_partita.get("bianco", "")) == nome_norm:
        return "w"
    if _normalizza(dato_partita.get("nero", "")) == nome_norm:
        return "b"
    return None


def turno_da_fen(fen):
    """Estrae il turno dal FEN (secondo token): "w" tocca al Bianco, "b" al Nero."""
    parti = fen.split()
    return parti[1] if len(parti) >= 2 else None


def eval_dal_mio_punto_di_vista(eval_prima, sono_bianco):
    """
    Normalizza eval_prima (centipawn, vista Bianco) dal MIO punto di vista:
    se sono Nero la inverto di segno. Positivo = sto meglio io.
    """
    return eval_prima if sono_bianco else -eval_prima


def posizione_contesa(eval_mia):
    """
    Filtro di sanita': True se la posizione e' "contesa", cioe' non ero gia'
    perso a fondo ne' gia' stravincente, e non e' un mate-score fasullo.
    """
    if abs(eval_mia) >= SOGLIA_MATTO:
        return False
    return LIMITE_PERSO <= eval_mia <= LIMITE_VINCENTE


def cadenza_da_nome(nome_file):
    """Deduce la cadenza dal nome file: "bullet" se inizia per bullet, altrimenti "altro"."""
    return "bullet" if os.path.basename(nome_file).lower().startswith("bullet") else "altro"


def raccogli_candidati(cartella=CARTELLA_ANALISI):
    """
    Scorre tutti i file di analisi e raccoglie le mie mosse che superano il
    filtro di sanita'.

    RESTITUISCE la coppia (candidati, scartati):
      - candidati: lista di dizionari (una per mossa mia "contesa"), con tutti i
        campi utili per il salvataggio e il conteggio;
      - scartati: quante mie mosse sono state escluse dal filtro di sanita'.
    """
    candidati = []
    scartati = 0

    file_analisi = sorted(glob.glob(os.path.join(cartella, "*.json")))
    if not file_analisi:
        logger.warning("Nessun file di analisi trovato in: %s", cartella)
        return candidati, scartati

    for percorso in file_analisi:
        with open(percorso, "r", encoding="utf-8") as f:
            dato = json.load(f)

        colore = mio_colore(dato)
        if colore is None:
            # Non gioco questa partita: la salto del tutto.
            continue

        nome_file = os.path.basename(percorso)
        cadenza = cadenza_da_nome(nome_file)
        sono_bianco = (colore == "w")

        for indice, mossa in enumerate(dato.get("mosse", [])):
            # Una mossa e' MIA se il turno nel FEN corrisponde al mio colore.
            if turno_da_fen(mossa["fen"]) != colore:
                continue

            eval_mia = eval_dal_mio_punto_di_vista(mossa["eval_prima"], sono_bianco)

            # Filtro di sanita': scarto le posizioni non contese.
            if not posizione_contesa(eval_mia):
                scartati += 1
                continue

            candidati.append({
                "fen": mossa["fen"],
                "mossa_giocata_uci": mossa["move_uci"],
                "soluzione_uci": mossa.get("best_move_uci"),
                "san_giocata": mossa.get("san"),
                "centipawn_loss": mossa["centipawn_loss"],
                "eval_mia_prima": eval_mia,
                "fonte_file": nome_file,
                "indice_mossa": indice,
                "cadenza": cadenza,
            })

    return candidati, scartati


def conta_per_soglia(candidati, soglie=SOGLIE):
    """
    Conta i candidati per ogni soglia di centipawn loss, divisi bullet/altro e
    totale. Restituisce un dizionario:
      {"bullet": {soglia: n, ...}, "altro": {...}, "totale": {...}}
    """
    conteggi = {
        "bullet": {s: 0 for s in soglie},
        "altro": {s: 0 for s in soglie},
        "totale": {s: 0 for s in soglie},
    }
    for c in candidati:
        cadenza = c["cadenza"]
        for s in soglie:
            if c["centipawn_loss"] >= s:
                conteggi[cadenza][s] += 1
                conteggi["totale"][s] += 1
    return conteggi


def salva_candidati(candidati, percorso=PERCORSO_OUTPUT, soglia=SOGLIA_SALVATAGGIO):
    """
    Salva i candidati con centipawn_loss >= soglia su file JSON.
    Restituisce quanti candidati sono stati salvati.
    """
    da_salvare = [c for c in candidati if c["centipawn_loss"] >= soglia]
    os.makedirs(os.path.dirname(percorso), exist_ok=True)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(da_salvare, f, indent=2, ensure_ascii=False)
    return len(da_salvare)


def _stampa_tabella(conteggi, scartati, soglie=SOGLIE):
    """Stampa a schermo una tabella chiara dei conteggi per soglia."""
    print()
    print("=== Candidati-puzzle per soglia di centipawn loss ===")
    print()
    print(f"  {'Soglia':<8} {'Bullet':>8} {'Altro':>8} {'Totale':>8}")
    print(f"  {'-' * 8} {'-' * 8:>8} {'-' * 8:>8} {'-' * 8:>8}")
    for s in soglie:
        etichetta = f">={s}"
        print(f"  {etichetta:<8} {conteggi['bullet'][s]:>8} "
              f"{conteggi['altro'][s]:>8} {conteggi['totale'][s]:>8}")
    print()
    print(f"  Posizioni scartate dal filtro di sanita': {scartati}")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    candidati, scartati = raccogli_candidati()

    if not candidati and scartati == 0:
        print("\nNessuna posizione mia trovata (controlla username e cartella analisi).\n")
        sys.exit(0)

    conteggi = conta_per_soglia(candidati)
    _stampa_tabella(conteggi, scartati)

    n_salvati = salva_candidati(candidati)
    logger.info("Salvati %d candidati in %s", n_salvati, PERCORSO_OUTPUT)
    print(f"Salvati {n_salvati} candidati (centipawn_loss >= {SOGLIA_SALVATAGGIO}) "
          f"in data/candidati_errori.json")
    print()
