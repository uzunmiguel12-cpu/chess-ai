"""
Modulo di SOLA MISURAZIONE - sola lettura: NON tocca data/categorie/, NON scrive
alcuno stato, NON salva file, NON genera puzzle. Sul modello di
ml/analizza_non_tattico.py e ml/converti_vantaggio.py.

ESITO DELLA MISURAZIONE (Punto 5g, gia' concluso - questo script e' tenuto come
prova, NON e' lavoro in sospeso).  Denominatore misurato: 1352 errori posizionali
puri = 32.1% degli errori gravi non-bullet (4214).  Segnali VERI [DATO]: fase
(apertura 46.4% / mediogioco 36.5% / finale 17.2%) e tipo di pezzo.  Segnali
BUTTATI, le euristiche [STIMA] smentite a campione: "re esposto" (marcava esposto
~65% dei casi, non discrimina) e "natura della best" (43.9% finisce in "altro":
guarda la geometria, non l'idea).  VERDETTO: il posizionale d'apertura/mediogioco
NON e' scomponibile in diagnosi allenabili con regole semplici. Un "no" dimostrato
con misura + verifica a campione. Unica pista non esclusa (non verificata): tecnica
di FINALE (17.2%, quasi tutto torre+re).  Vedi anche ml/analizza_aperture.py.

SCOPO.  Scomporre gli ERRORI POSIZIONALI PURI per capire se contengono pattern
ricorrenti (es. "sbaglio sempre a non spingere un pedone in mediogioco", "lascio
il mio re esposto"). E' una diagnosi a monte: serve a decidere SE valga la pena
costruire un allenamento posizionale, guardando i numeri veri.

ERRORE POSIZIONALE PURO.  Una MIA mossa e' tenuta solo se TUTTE queste valgono:
  - centipawn_loss >= 200 (errore grave);
  - cadenza != bullet (in bullet l'errore e' spesso il tempo, non la posizione);
  - la BEST move (best_move_uci) NON cattura (nessun pezzo sulla casa d'arrivo,
    en passant incluso), NON da' scacco, NON e' promozione;
  - la BEST move NON e' una tattica gia' riconosciuta da ml/tattica.py
    (forchetta, inchiodatura, infilata, pezzo_in_presa, scoperta): riuso
    rileva_tipo_tattico, non riscrivo la logica.
Filtro di sanita' identico a estrai_errori.py: scarto le posizioni oltre +-700cp
e i mate-score fasulli (gia' perso a fondo / gia' stravincente / matto annunciato).

Cosi' resta SOLO il "muro" posizionale: la best move e' un miglioramento tranquillo
(uno sviluppo, una spinta, una torre su colonna) e la mia mossa l'ha mancato.

METRICHE per ogni errore tenuto (marcate [DATO] o [STIMA]):
  - fase                 [DATO]  apertura/mediogioco/finale dal materiale (categorizza).
  - tipo_pezzo_best      [DATO]  pezzo sulla casa di PARTENZA della best (pedone..re).
  - natura_best          [STIMA] spinta_pedone / sviluppo / torre_su_colonna / altro.
  - mio_re_esposto       [STIMA] scudo di pedoni davanti al MIO re < 2 -> esposto.
  - re_avversario_esposto[STIMA] idem sul re avversario.
  - entita_perdita       [DATO]  200-300 / 300-500 / >500.

OUTPUT a terminale (italiano), niente file:
  - denominatore: quanti errori posizionali puri, su quanti errori gravi non-bullet
    totali (la quota %);
  - distribuzione per ciascun segnale singolo;
  - due incroci: fase x tipo_pezzo_best, fase x mio_re_esposto;
  - QUOTA NON CARATTERIZZATA: natura_best="altro" E nessuno dei due re esposto
    (il "residuo del residuo": cio' che le euristiche non spiegano);
  - per ogni categoria principale (natura_best) un CAMPIONE di 5 esempi
    (fen + best in SAN + cl) per la verifica manuale.

Uso:  python ml/analizza_posizionale.py
"""

import os
import sys
import json
import glob
import logging
from collections import Counter, defaultdict

import chess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

# Riuso le utility gia' esistenti (come fanno analizza_non_tattico.py e
# converti_vantaggio.py). Lo script gira da ml/ (python ml/analizza_posizionale.py)
# e in quel caso ml/ e' su sys.path: gli import "piatti" funzionano. Fallback
# prudente nel caso (raro) in cui non lo fossero.
from tattica import rileva_tipo_tattico

try:
    from estrai_errori import (
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista, posizione_contesa,
        SOGLIA_MATTO,
    )
    from converti_vantaggio import e_bullet
    from categorizza import classifica_fase
except Exception:  # pragma: no cover - solo fallback se gli import piatti falliscono
    from ml.tattica import rileva_tipo_tattico  # noqa: F811
    from ml.estrai_errori import (
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista, posizione_contesa,
        SOGLIA_MATTO,
    )
    from ml.converti_vantaggio import e_bullet
    from ml.categorizza import classifica_fase

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)

# Soglia che qualifica una mia mossa come errore GRAVE (e candidato posizionale).
SOGLIA_ERRORE = 200

# Nomi italiani dei tipi di pezzo (per tipo_pezzo_best).
NOMI_PEZZO = {
    chess.PAWN: "pedone", chess.KNIGHT: "cavallo", chess.BISHOP: "alfiere",
    chess.ROOK: "torre", chess.QUEEN: "donna", chess.KING: "re",
}

# Ordine di stampa delle categorie di natura_best (le "categorie principali").
NATURE = ("spinta_pedone", "sviluppo", "torre_su_colonna", "altro")


# ----------------------------------------------------------------------------
# Filtro "errore posizionale puro"
# ----------------------------------------------------------------------------

def fen_dopo_mossa(fen, uci):
    """FEN risultante dall'applicare `uci` a `fen`, o None se mancante/illegale."""
    if not uci:
        return None
    try:
        board = chess.Board(fen)
        board.push_uci(uci)
        return board.fen()
    except Exception:
        return None


def best_speciale(fen, best_uci):
    """
    Per la BEST move restituisce la terna (cattura, scacco, promozione), oppure
    None se la best e' mancante/illegale.
      - cattura  : la best cattura materiale (board.is_capture gestisce l'en passant,
                   cioe' la cattura senza pezzo sulla casa d'arrivo);
      - scacco   : la best da' scacco (board.gives_check);
      - promozione: la best e' una promozione (campo promotion della mossa UCI).
    Una best "speciale" (uno qualunque True) NON e' un errore posizionale puro.
    """
    if not best_uci:
        return None
    try:
        board = chess.Board(fen)
        mossa = chess.Move.from_uci(best_uci)
        if mossa not in board.legal_moves:
            return None
        return (board.is_capture(mossa), board.gives_check(mossa),
                mossa.promotion is not None)
    except Exception:
        return None


def best_e_tattica(fen, best_uci):
    """
    True se la BEST move crea un pattern tattico noto a ml/tattica.py (forchetta,
    inchiodatura, infilata, pezzo_in_presa, scoperta). Riuso rileva_tipo_tattico:
    ricostruisco la FEN dopo la best e la valuto col colore di chi DOVEVA giocarla
    (= io, board.turn della posizione di partenza), come fa arricchisci.py.
    Se la best e' mancante/illegale -> False (non e' classificabile come tattica).
    """
    fen_best = fen_dopo_mossa(fen, best_uci)
    if fen_best is None:
        return False
    colore = chess.Board(fen).turn  # chi DOVEVA giocare la best = io
    return rileva_tipo_tattico(fen, fen_best, colore, best_uci) is not None


def posizione_sana(mossa, eval_mia):
    """
    Filtro di sanita' di estrai_errori.py (posizione_contesa: scarta oltre +-700cp
    e i mate-score) applicato all'eval PRIMA, piu' il taglio dei mate-score anche
    nell'eval DOPO. posizione_contesa guarda solo eval_prima, quindi una mossa che
    cammina DENTRO un matto annunciato passerebbe il filtro pur avendo un
    centipawn_loss fasullo (es. 100488). Scarto esplicitamente questi mate-score,
    come chiede il filtro (".. e i mate-score").
    """
    if not posizione_contesa(eval_mia):
        return False
    if abs(mossa["eval_dopo"]) >= SOGLIA_MATTO:
        return False
    return True


def e_posizionale_puro(mossa, eval_mia):
    """
    True se la mossa (gia' MIA, non bullet) e' un errore posizionale puro:
    cl >= SOGLIA_ERRORE, posizione sana (sanita'), best non speciale
    (cattura/scacco/promozione) e best non tattica nota.
    """
    if mossa["centipawn_loss"] < SOGLIA_ERRORE:
        return False
    if not posizione_sana(mossa, eval_mia):
        return False
    fen = mossa["fen"]
    best = mossa.get("best_move_uci")
    speciale = best_speciale(fen, best)
    if speciale is None or any(speciale):
        return False
    if best_e_tattica(fen, best):
        return False
    return True


def e_grave_contesa(mossa, eval_mia):
    """
    Denominatore: True se la mossa e' un errore GRAVE in posizione sana
    (cl >= SOGLIA_ERRORE e sanita' ok). Stessa base da cui peschiamo i posizionali
    puri, cosi' la quota % e' un confronto omogeneo.
    """
    return mossa["centipawn_loss"] >= SOGLIA_ERRORE and posizione_sana(mossa, eval_mia)


# ----------------------------------------------------------------------------
# Metriche per ogni errore tenuto
# ----------------------------------------------------------------------------

def tipo_pezzo_best(fen, best_uci):
    """[DATO] Tipo del pezzo sulla casa di PARTENZA della best (pedone..re), o None."""
    board = chess.Board(fen)
    mossa = chess.Move.from_uci(best_uci)
    pezzo = board.piece_at(mossa.from_square)
    return NOMI_PEZZO.get(pezzo.piece_type) if pezzo else None


def natura_best(fen, best_uci):
    """
    [STIMA] Natura grezza della best move, in ordine di precedenza:
      - "spinta_pedone"   : muove un pedone;
      - "sviluppo"        : muove un pezzo dalla sua traversa di PARTENZA
                            (traversa 1 col Bianco, traversa 8 col Nero);
      - "torre_su_colonna": muove una torre cambiando colonna;
      - "altro"           : nessuno dei precedenti.
    """
    board = chess.Board(fen)
    mossa = chess.Move.from_uci(best_uci)
    pezzo = board.piece_at(mossa.from_square)
    if pezzo is None:
        return "altro"
    if pezzo.piece_type == chess.PAWN:
        return "spinta_pedone"
    traversa_partenza = 0 if pezzo.color == chess.WHITE else 7
    if chess.square_rank(mossa.from_square) == traversa_partenza:
        return "sviluppo"
    if (pezzo.piece_type == chess.ROOK
            and chess.square_file(mossa.from_square)
            != chess.square_file(mossa.to_square)):
        return "torre_su_colonna"
    return "altro"


def re_esposto(fen, colore):
    """
    [STIMA] True se il re di `colore` e' esposto: meno di 2 pedoni dello stesso
    colore nelle (max 3) case una traversa DAVANTI al re - colonna del re piu' le
    due adiacenti; sul bordo sono 2 case. "Davanti" dipende dal colore (il Bianco
    avanza verso traverse maggiori, il Nero verso le minori). Se il re e'
    sull'ultima traversa non c'e' scudo davanti -> esposto.
    Restituisce None se il re non e' sulla scacchiera (FEN anomala).
    """
    board = chess.Board(fen)
    casa_re = board.king(colore)
    if casa_re is None:
        return None
    colonna = chess.square_file(casa_re)
    traversa = chess.square_rank(casa_re)
    avanti = 1 if colore == chess.WHITE else -1
    traversa_davanti = traversa + avanti

    pedoni = 0
    if 0 <= traversa_davanti < 8:
        for dc in (-1, 0, 1):
            c = colonna + dc
            if 0 <= c < 8:
                sq = chess.square(c, traversa_davanti)
                p = board.piece_at(sq)
                if p is not None and p.piece_type == chess.PAWN and p.color == colore:
                    pedoni += 1
    return pedoni < 2


def entita_perdita(centipawn_loss):
    """[DATO] Fascia di entita' della perdita: '200-300' / '300-500' / '>500'."""
    if centipawn_loss < 300:
        return "200-300"
    if centipawn_loss < 500:
        return "300-500"
    return ">500"


def best_san(fen, best_uci):
    """SAN della best move dalla posizione `fen` (per i campioni), o l'UCI grezzo."""
    try:
        board = chess.Board(fen)
        return board.san(chess.Move.from_uci(best_uci))
    except Exception:
        return best_uci or "?"


def calcola_segnali(mossa):
    """
    Calcola tutte le metriche per un errore posizionale puro. `colore` e' il colore
    di chi DOVEVA giocare la best (= io): il MIO re e' quello, l'avversario l'altro.
    """
    fen = mossa["fen"]
    best = mossa["best_move_uci"]
    colore = chess.Board(fen).turn
    return {
        "fen": fen,
        "cl": mossa["centipawn_loss"],
        "best_san": best_san(fen, best),
        "fase": classifica_fase(fen),                      # [DATO]
        "tipo_pezzo_best": tipo_pezzo_best(fen, best),     # [DATO]
        "natura_best": natura_best(fen, best),             # [STIMA]
        "mio_re_esposto": re_esposto(fen, colore),         # [STIMA]
        "re_avversario_esposto": re_esposto(fen, not colore),  # [STIMA]
        "entita_perdita": entita_perdita(mossa["centipawn_loss"]),  # [DATO]
    }


# ----------------------------------------------------------------------------
# Aggregazione
# ----------------------------------------------------------------------------

def _nuovo_riepilogo():
    """Struttura vuota dei conteggi."""
    return {
        "errori_gravi_non_bullet": 0,   # denominatore: cl>=200 in posizione contesa
        "posizionali_puri": 0,          # numeratore
        "partite_bullet_escluse": 0,
        "file_saltati": 0,              # non gioco io / illeggibili
        "segnali": [],                  # un dict di metriche per ogni posizionale puro
    }


def analizza_cartella(cartella=CARTELLA_ANALISI):
    """
    Scorre tutte le analisi (sola lettura) e raccoglie i segnali degli errori
    posizionali puri, oltre al denominatore degli errori gravi non-bullet.
    """
    rie = _nuovo_riepilogo()

    file_analisi = sorted(glob.glob(os.path.join(cartella, "*.json")))
    if not file_analisi:
        logger.warning("Nessun file di analisi trovato in: %s", cartella)
        return rie

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
            rie["file_saltati"] += 1
            continue

        sono_bianco = (colore == "w")
        for mossa in dato.get("mosse", []):
            # Una mossa e' MIA se il turno nel FEN corrisponde al mio colore.
            if turno_da_fen(mossa["fen"]) != colore:
                continue

            eval_mia = eval_dal_mio_punto_di_vista(mossa["eval_prima"], sono_bianco)
            if not e_grave_contesa(mossa, eval_mia):
                continue
            rie["errori_gravi_non_bullet"] += 1

            if not e_posizionale_puro(mossa, eval_mia):
                continue
            rie["posizionali_puri"] += 1
            rie["segnali"].append(calcola_segnali(mossa))

    return rie


def _pct(parte, totale):
    """Percentuale robusta: 0.0 se il totale e' zero (evita divisioni per zero)."""
    return (100.0 * parte / totale) if totale else 0.0


def _bool_label(v):
    """Etichetta leggibile per i segnali booleani (con None -> 'n/d')."""
    if v is None:
        return "n/d"
    return "esposto" if v else "protetto"


# ----------------------------------------------------------------------------
# Stampa
# ----------------------------------------------------------------------------

def _stampa_legenda():
    print()
    print("LEGENDA: [DATO] = ricavato direttamente (calcolo certo dalla posizione)")
    print("         [STIMA] = euristica grezza, da verificare a occhio")
    print()


def _stampa_distribuzione_singola(titolo, contatore, totale, marca):
    """Stampa una distribuzione di un singolo segnale (valore -> n, %)."""
    print(f"  Distribuzione per {titolo}  {marca}")
    print(f"    {'valore':<22} {'n':>6} {'%':>8}")
    print(f"    {'-'*22} {'-'*6:>6} {'-'*8:>8}")
    for valore, n in sorted(contatore.items(), key=lambda kv: (-kv[1], str(kv[0]))):
        print(f"    {str(valore):<22} {n:>6} {_pct(n, totale):>7.1f}%")
    print()


def _stampa_incrocio(titolo, righe, colonne, tabella, totale):
    """Stampa un incrocio 2D (righe x colonne) con i conteggi."""
    print(f"  Incrocio {titolo}")
    intestazione = "    " + f"{'':<13}" + "".join(f"{c:>16}" for c in colonne) + f"{'tot':>8}"
    print(intestazione)
    print("    " + "-" * (13 + 16 * len(colonne) + 8))
    for r in righe:
        tot_riga = sum(tabella[r].get(c, 0) for c in colonne)
        celle = "".join(f"{tabella[r].get(c, 0):>16}" for c in colonne)
        print(f"    {r:<13}{celle}{tot_riga:>8}")
    print(f"    (totale errori posizionali puri classificati: {totale})")
    print()


def _stampa_campioni(segnali):
    """Per ogni natura_best stampa un campione di 5 esempi (fen + best SAN + cl)."""
    per_natura = defaultdict(list)
    for s in segnali:
        per_natura[s["natura_best"]].append(s)

    print("  CAMPIONI per categoria principale (natura_best) - 5 esempi ciascuna")
    print("  (per la verifica manuale: incolla la FEN su una scacchiera)")
    print()
    for natura in NATURE:
        esempi = per_natura.get(natura, [])
        if not esempi:
            continue
        print(f"    --- {natura}  ({len(esempi)} casi) ---")
        for s in esempi[:5]:
            print(f"      best={s['best_san']:<7} cl={s['cl']:>4}  re_mio={_bool_label(s['mio_re_esposto']):<8} "
                  f"fase={s['fase']}")
            print(f"        fen: {s['fen']}")
        print()


def _stampa_riepilogo(rie):
    """Stampa l'intera diagnosi posizionale (numeri assoluti + percentuali)."""
    tot_gravi = rie["errori_gravi_non_bullet"]
    posiz = rie["posizionali_puri"]
    segnali = rie["segnali"]

    print()
    print("=== Scomposizione degli ERRORI POSIZIONALI PURI (SOLA MISURAZIONE) ===")
    _stampa_legenda()

    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']} "
          f"(in bullet l'errore e' spesso il tempo, non la posizione)")
    print(f"  File saltati (non gioco io / illeggibili): {rie['file_saltati']}")
    print()
    print("  DENOMINATORE")
    print(f"    Miei errori gravi non-bullet (cl >= {SOGLIA_ERRORE}, posizione contesa): {tot_gravi}")
    print(f"    di cui ERRORI POSIZIONALI PURI (best tranquilla, non tattica): {posiz}  "
          f"({_pct(posiz, tot_gravi):.1f}%)")
    print()

    if posiz == 0:
        print("  Nessun errore posizionale puro: niente da scomporre.\n")
        return

    # Distribuzioni per singolo segnale.
    print("  --- Distribuzioni per singolo segnale ---")
    print()
    _stampa_distribuzione_singola(
        "fase", Counter(s["fase"] for s in segnali), posiz, "[DATO]")
    _stampa_distribuzione_singola(
        "tipo_pezzo_best", Counter(s["tipo_pezzo_best"] for s in segnali), posiz, "[DATO]")
    _stampa_distribuzione_singola(
        "natura_best", Counter(s["natura_best"] for s in segnali), posiz, "[STIMA]")
    _stampa_distribuzione_singola(
        "mio_re_esposto", Counter(_bool_label(s["mio_re_esposto"]) for s in segnali),
        posiz, "[STIMA]")
    _stampa_distribuzione_singola(
        "re_avversario_esposto",
        Counter(_bool_label(s["re_avversario_esposto"]) for s in segnali), posiz, "[STIMA]")
    _stampa_distribuzione_singola(
        "entita_perdita", Counter(s["entita_perdita"] for s in segnali), posiz, "[DATO]")

    # Incrocio 1: fase x tipo_pezzo_best.
    print("  --- Incroci ---")
    print()
    fasi = ["apertura", "mediogioco", "finale"]
    pezzi = ["pedone", "cavallo", "alfiere", "torre", "donna", "re"]
    tab1 = defaultdict(Counter)
    for s in segnali:
        tab1[s["fase"]][s["tipo_pezzo_best"]] += 1
    _stampa_incrocio("fase x tipo_pezzo_best  [DATO x DATO]", fasi, pezzi, tab1, posiz)

    # Incrocio 2: fase x mio_re_esposto.
    stati_re = ["esposto", "protetto", "n/d"]
    tab2 = defaultdict(Counter)
    for s in segnali:
        tab2[s["fase"]][_bool_label(s["mio_re_esposto"])] += 1
    _stampa_incrocio("fase x mio_re_esposto  [DATO x STIMA]", fasi, stati_re, tab2, posiz)

    # Quota NON caratterizzata: il "residuo del residuo".
    non_caratt = sum(
        1 for s in segnali
        if s["natura_best"] == "altro"
        and not s["mio_re_esposto"] and not s["re_avversario_esposto"]
    )
    print("  --- QUOTA NON CARATTERIZZATA (il 'residuo del residuo') ---")
    print(f"    natura_best='altro' E nessuno dei due re esposto: {non_caratt}  "
          f"({_pct(non_caratt, posiz):.1f}% dei posizionali puri)")
    print("    Sono gli errori che NESSUNA delle euristiche grezze spiega: la best")
    print("    non e' spinta/sviluppo/torre-su-colonna e i re sono entrambi al riparo.")
    print()

    # Campioni per verifica manuale.
    _stampa_campioni(segnali)

    print("  NOTA DI ONESTA': i segnali [STIMA] sono euristiche grezze. 'natura_best'")
    print("  guarda solo la geometria della best, non il PERCHE' e' migliore; 're")
    print("  esposto' conta i soli pedoni-scudo e ignora pezzi difensori e attaccanti.")
    print("  La QUOTA NON CARATTERIZZATA misura quanto di posizionale ci sfugge ancora.")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_cartella()

    if riepilogo["errori_gravi_non_bullet"] == 0:
        print("\nNessun mio errore grave non-bullet trovato "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_riepilogo(riepilogo)
