"""
Utility (Fase 4) - estrae i rating del giocatore per cadenza dalle partite.

Legge un PGN e, per il giocatore indicato, raggruppa le partite per cadenza
(bullet / blitz / rapid / classical, secondo le soglie di Chess.com) e mostra:
- quante partite per cadenza
- il rating medio delle partite piu' RECENTI in quella cadenza

Serve a scegliere, guardando i numeri veri, quale Elo usare come riferimento
per la fascia di difficolta' dei puzzle.

Uso:  python estrai_elo.py ..\\data\\mie_partite.pgn "MigueL_uz"
"""

import sys
import logging
import chess.pgn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")


def _categoria_cadenza(time_control):
    """
    Classifica la cadenza dal tag TimeControl (secondi base, eventualmente
    con incremento tipo '600+5'). Soglie stile Chess.com sui secondi base:
      < 180   -> bullet
      < 600   -> blitz
      < 1800  -> rapid
      >=1800  -> classical
    """
    if not time_control or time_control == "-":
        return "sconosciuta"
    base = time_control.split("+")[0]
    try:
        secondi = int(base)
    except ValueError:
        return "sconosciuta"
    if secondi < 180:
        return "bullet"
    if secondi < 600:
        return "blitz"
    if secondi < 1800:
        return "rapid"
    return "classical"


def estrai_rating_per_cadenza(percorso_pgn, nome, n_recenti=20):
    """
    RESTITUISCE un dizionario: cadenza -> {partite, rating_medio_recenti}.
    Il rating recente e' la media dei rating del giocatore nelle ultime
    n_recenti partite di quella cadenza (le piu' in fondo al file).
    """
    nome_norm = nome.strip().lower()
    # per ogni cadenza accumuliamo la lista dei rating in ordine di apparizione
    rating_per_cadenza = {}

    with open(percorso_pgn, "r", encoding="utf-8") as f:
        while True:
            partita = chess.pgn.read_game(f)
            if partita is None:
                break
            h = partita.headers
            bianco = h.get("White", "").strip().lower()
            nero = h.get("Black", "").strip().lower()

            if nome_norm == bianco:
                elo = h.get("WhiteElo", "")
            elif nome_norm == nero:
                elo = h.get("BlackElo", "")
            else:
                continue

            try:
                elo = int(elo)
            except (ValueError, TypeError):
                continue

            cad = _categoria_cadenza(h.get("TimeControl", ""))
            rating_per_cadenza.setdefault(cad, []).append(elo)

    # Costruiamo il riepilogo: numero partite + media degli ultimi n_recenti.
    riepilogo = {}
    for cad, lista in rating_per_cadenza.items():
        recenti = lista[-n_recenti:]
        media = round(sum(recenti) / len(recenti)) if recenti else 0
        riepilogo[cad] = {
            "partite": len(lista),
            "rating_recente": media,
        }
    return riepilogo


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Uso: python estrai_elo.py <file.pgn> "Nome"')
        sys.exit(1)

    riepilogo = estrai_rating_per_cadenza(sys.argv[1], sys.argv[2])
    if not riepilogo:
        print(f"\nNessuna partita trovata per '{sys.argv[2]}'.\n")
        sys.exit(1)

    print()
    print(f"=== Rating per cadenza di {sys.argv[2]} ===")
    print(f"(rating recente = media delle ultime 20 partite di quella cadenza)")
    print()
    print(f"  {'cadenza':12} {'partite':>8} {'rating recente':>16}")
    print(f"  {'-'*12} {'-'*8} {'-'*16}")
    # ordiniamo per numero di partite, decrescente
    for cad in sorted(riepilogo, key=lambda c: riepilogo[c]["partite"], reverse=True):
        d = riepilogo[cad]
        print(f"  {cad:12} {d['partite']:>8} {d['rating_recente']:>16}")
    print()
