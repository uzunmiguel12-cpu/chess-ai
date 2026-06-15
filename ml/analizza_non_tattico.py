"""
Modulo di SOLA MISURAZIONE (T3) - sola lettura, NIENTE Stockfish, NIENTE file in
output. Scompone la categoria "non_tattico" degli errori per decidere se vale la
pena aggiungere nuovi tipi tattici (T2: deviazione, attrazione, scoperta, ...).

PERCHE'.  Dopo il fix di arricchisci.py il sistema classifica l'errore come una
TATTICA MANCATA: il tipo si calcola sulla MOSSA MIGLIORE (best_move_uci), non
sulla mia. Un errore e' "non_tattico" quando rileva_tipo_tattico (ml/tattica.py)
applicato alla BEST move da' None (la mossa migliore non crea alcun pattern noto:
pezzo_in_presa / forchetta / inchiodatura / infilata). Questo modulo misura
quanto di quel non_tattico VERO sia in realta' tattica non ancora coperta dai 4
pattern (input per T2) e quanto invece sia "muro" posizionale. T3 e' quindi
COERENTE col profilo: misura la stessa popolazione che il sistema etichetta.

DATI.  Legge data/analisi/*.json (gli stessi di estrai_errori.py /
converti_vantaggio.py), riusando le loro utility per individuare le MIE partite
(mio_colore) e le MIE mosse (turno_da_fen). Ogni mossa ha: fen (posizione PRIMA),
move_uci (la mia mossa), best_move_uci (mossa migliore Stockfish), centipawn_loss,
eval_prima, eval_dopo, san.

ERRORI GRAVI.  Stessa soglia del profilo (ml/profilo.py: GRAVITA_ERRORE =
{"mistake", "blunder"}), cioe' centipawn_loss > 100. Per allineamento riuso
classifica_gravita di ml/categorizza.py invece di replicare i numeri.

ESCLUSIONE BULLET.  I file il cui nome inizia per "bullet" sono esclusi (come nel
punto 6 e nella diagnosi conversione): in bullet un errore e' spesso il tempo che
scade, non un buco tattico.

CATEGORIE (tutte STIME euristiche, non classificazioni certe). Per ogni mio errore
grave che e' un non_tattico VERO (rileva_tipo_tattico sulla BEST move da' None):
  - "probabile_tattica_non_coperta": la BEST move CATTURA materiale (o da' scacco)
    ma NON e' uno dei 4 pattern noti. => candidata a un nuovo tipo tattico (T2).
  - "probabile_posizionale": la BEST move NON cattura e non da' scacco; il
    guadagno e' posizionale. => il "muro", non allenabile coi puzzle tattici.
  - "incerto": best move mancante/illegale o non valutabile.

NOTA. La vecchia categoria "tattica_riconoscibile_mancata" (best move = pattern
gia' noto) NON esiste piu': dopo il fix quei casi sono gia' etichettati col loro
tipo e quindi NON sono piu' non_tattico, percio' non entrano nemmeno qui.

Uso:  python ml/analizza_non_tattico.py
"""

import os
import sys
import json
import glob
import logging
from collections import Counter

import chess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

# Riuso le utility gia' esistenti, come fa converti_vantaggio.py con estrai_errori.
# Il modulo gira come script da ml/ (python ml/analizza_non_tattico.py) e in quel
# caso ml/ e' su sys.path, quindi gli import "piatti" funzionano. Fallback prudente
# nel caso (raro) in cui non lo fossero.
from tattica import rileva_tipo_tattico

try:
    from estrai_errori import mio_colore, turno_da_fen
    from converti_vantaggio import e_bullet
    from categorizza import classifica_gravita
except Exception:  # pragma: no cover - solo fallback se gli import piatti falliscono
    from ml.tattica import rileva_tipo_tattico  # noqa: F811
    from ml.estrai_errori import mio_colore, turno_da_fen
    from ml.converti_vantaggio import e_bullet
    from ml.categorizza import classifica_gravita

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)

# Errore "grave" = stessa soglia del profilo (ml/profilo.py): mistake o blunder,
# cioe' centipawn_loss > 100. Tengo le etichette qui per documentare l'allineamento.
GRAVITA_ERRORE = {"mistake", "blunder"}

# Le categorie della scomposizione (ordine di stampa). Misurano solo il
# non_tattico VERO (best move non tattica): la vecchia "tattica_riconoscibile_mancata"
# e' sparita perche' quei casi non sono piu' non_tattico (li etichetta il sistema).
CATEGORIE = (
    "probabile_tattica_non_coperta",
    "probabile_posizionale",
    "incerto",
)


def e_errore_grave(centipawn_loss):
    """True se il centipawn loss e' un errore grave (mistake/blunder), come il profilo."""
    return classifica_gravita(centipawn_loss) in GRAVITA_ERRORE


def fen_dopo_mossa(fen, uci):
    """
    Applica la mossa `uci` alla posizione `fen` e restituisce la FEN risultante.
    Restituisce None se la mossa e' mancante, illegale o comunque non applicabile
    (gestione con try/except richiesta per le mosse strane).
    """
    if not uci:
        return None
    try:
        board = chess.Board(fen)
        board.push_uci(uci)
        return board.fen()
    except Exception:
        return None


def tipo_tattico_best_mossa(mossa):
    """
    Riproduce la classificazione REALE del sistema (stessa logica di
    arricchisci._aggiungi_tipo_tattico): un errore e' una TATTICA MANCATA, quindi
    il tipo si calcola dalla MOSSA MIGLIORE (best_move_uci), non dalla mia.

    Ricostruisce la FEN dopo la best move e vi applica rileva_tipo_tattico, col
    colore di chi DOVEVA giocare la best (= io, board.turn della posizione di
    partenza). Restituisce il tipo noto, oppure None se la best move e'
    mancante/illegale o non crea alcun pattern: in quel caso l'errore e'
    "non_tattico" VERO (esattamente come lo etichetta il sistema).
    """
    fen = mossa["fen"]
    best_uci = mossa.get("best_move_uci")
    fen_best = fen_dopo_mossa(fen, best_uci)
    if fen_best is None:
        return None
    colore = chess.Board(fen).turn  # chi DOVEVA giocare la best = io
    return rileva_tipo_tattico(fen, fen_best, colore, best_uci)


def best_cattura_o_scacco(fen, best_uci):
    """
    Per la best move: (cattura, scacco) booleani.
      - cattura: la best move cattura materiale (inclusa la presa en passant);
      - scacco : dopo la best move l'avversario e' sotto scacco.
    Restituisce None se la best move e' mancante/illegale/non valutabile.
    """
    if not best_uci:
        return None
    try:
        board = chess.Board(fen)
        mossa = chess.Move.from_uci(best_uci)
        if mossa not in board.legal_moves:
            return None
        cattura = board.is_capture(mossa)
        board.push(mossa)
        scacco = board.is_check()
        return (cattura, scacco)
    except Exception:
        return None


def classifica_non_tattico(mossa):
    """
    Classifica un mio errore grave che e' un non_tattico VERO: la BEST move NON e'
    un pattern noto (questo e' gia' garantito a monte da tipo_tattico_best_mossa,
    che restituisce None). Resta solo da capire CHE genere di non_tattico sia,
    guardando la best move. Restituisce la categoria:
      - "incerto": best move mancante/illegale o non valutabile;
      - "probabile_tattica_non_coperta": la best cattura materiale o da' scacco
        (ma non e' uno dei 4 pattern) => candidata a un nuovo tipo tattico (T2);
      - "probabile_posizionale": la best non cattura e non da' scacco => il "muro".

    STIMA euristica: "cattura materiale" non garantisce tattica e viceversa.
    """
    fen = mossa["fen"]
    best = mossa.get("best_move_uci")

    # La best cattura materiale o da' scacco? (None se mancante/illegale -> incerto)
    info = best_cattura_o_scacco(fen, best)
    if info is None:
        return "incerto"
    cattura, scacco = info
    if cattura or scacco:
        return "probabile_tattica_non_coperta"

    # Niente cattura, niente scacco -> guadagno solo posizionale (il "muro").
    return "probabile_posizionale"


def _nuovo_riepilogo():
    """Struttura vuota dei conteggi."""
    return {
        "errori_gravi_non_bullet": 0,   # miei errori gravi (non bullet) totali
        "non_tattici": 0,               # di cui non_tattico VERO (best non tattica)
        "categorie": Counter(),         # scomposizione del non_tattico
        "partite_bullet_escluse": 0,
        "file_saltati": 0,              # non gioco io / illeggibili
    }


def scomponi_non_tattici(mosse_non_tattiche):
    """
    Dato un elenco di mosse gia' filtrate (miei errori gravi che sono non_tattici
    VERI, cioe' best move non tattica), restituisce la scomposizione:
      {"categorie": Counter}.

    Funzione pura (niente IO): usata sia dall'aggregatore su file sia dai test.
    """
    categorie = Counter()
    for mossa in mosse_non_tattiche:
        categorie[classifica_non_tattico(mossa)] += 1
    return {"categorie": categorie}


def analizza_cartella(cartella=CARTELLA_ANALISI):
    """
    Scorre tutte le analisi e produce il riepilogo della scomposizione.

    Per ogni MIA partita non bullet, per ogni MIA mossa che e' un errore grave:
    conta l'errore; se e' un non_tattico VERO (rileva_tipo_tattico sulla BEST move
    da' None, come fa il sistema dopo il fix) lo classifica nelle categorie.
    """
    rie = _nuovo_riepilogo()

    file_analisi = sorted(glob.glob(os.path.join(cartella, "*.json")))
    if not file_analisi:
        logger.warning("Nessun file di analisi trovato in: %s", cartella)
        return rie

    mosse_non_tattiche = []  # raccolgo per scomporle in blocco (funzione pura)

    for percorso in file_analisi:
        # Esclusione bullet prima di leggere (la cadenza si deduce dal nome).
        if e_bullet(percorso):
            rie["partite_bullet_escluse"] += 1
            continue

        try:
            with open(percorso, "r", encoding="utf-8") as f:
                dato = json.load(f)
        except (OSError, json.JSONDecodeError):
            rie["file_saltati"] += 1
            continue

        colore = mio_colore(dato)
        if colore is None:
            # Non gioco questa partita: la salto del tutto.
            rie["file_saltati"] += 1
            continue

        for mossa in dato.get("mosse", []):
            # Una mossa e' MIA se il turno nel FEN corrisponde al mio colore.
            if turno_da_fen(mossa["fen"]) != colore:
                continue
            if not e_errore_grave(mossa["centipawn_loss"]):
                continue

            rie["errori_gravi_non_bullet"] += 1

            # Se la BEST move e' gia' un pattern noto, il sistema l'ha etichettata:
            # NON e' un non_tattico VERO, quindi la salto (allineamento al profilo).
            if tipo_tattico_best_mossa(mossa) is not None:
                continue

            rie["non_tattici"] += 1
            mosse_non_tattiche.append(mossa)

    scomposizione = scomponi_non_tattici(mosse_non_tattiche)
    rie["categorie"] = scomposizione["categorie"]
    return rie


def _pct(parte, totale):
    """Percentuale robusta: 0.0 se il totale e' zero (evita divisioni per zero)."""
    return (100.0 * parte / totale) if totale else 0.0


def _stampa_riepilogo(rie):
    """Stampa a schermo la scomposizione (numeri assoluti + percentuali)."""
    tot_gravi = rie["errori_gravi_non_bullet"]
    non_tatt = rie["non_tattici"]

    print()
    print("=== Scomposizione del 'non_tattico' (SOLA MISURAZIONE, T3) ===")
    print()
    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']} "
          f"(in bullet l'errore e' spesso il tempo, non la tattica)")
    print(f"  File saltati (non gioco io / illeggibili): {rie['file_saltati']}")
    print()
    print(f"  Miei errori gravi non-bullet (mistake+blunder): {tot_gravi}")
    print(f"  di cui 'non_tattico' VERO (best move non tattica): {non_tatt}  "
          f"({_pct(non_tatt, tot_gravi):.1f}% degli errori gravi)")
    print()

    print("  Scomposizione del 'non_tattico' VERO (STIME sulla best move):")
    print(f"    {'categoria':<32} {'n':>6} {'%':>8}")
    print(f"    {'-'*32} {'-'*6:>6} {'-'*8:>8}")
    for cat in CATEGORIE:
        n = rie["categorie"].get(cat, 0)
        print(f"    {cat:<32} {n:>6} {_pct(n, non_tatt):>7.1f}%")
    print()

    print("  NOTA DI ONESTA': T3 e' ora COERENTE col profilo: classifica sulla BEST")
    print("  move, come arricchisci.py, quindi misura la stessa popolazione che il")
    print("  sistema etichetta come 'non_tattico'. Serve a stimare quanta parte di")
    print("  quel non_tattico VERO sia tattica non ancora coperta (input per T2).")
    print("  Restano STIME euristiche: 'cattura materiale' non garantisce una tattica")
    print("  (puo' essere una ricattura tranquilla) e una tattica vera puo' non")
    print("  catturare nulla (deviazione, attrazione, scacco posizionale).")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_cartella()

    if riepilogo["errori_gravi_non_bullet"] == 0:
        print("\nNessun mio errore grave non-bullet trovato "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_riepilogo(riepilogo)
