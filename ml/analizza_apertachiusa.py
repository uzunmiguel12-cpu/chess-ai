"""
Modulo di SOLA MISURAZIONE - sola lettura: NON tocca data/, NON scrive alcuno
stato, NON salva file, NON costruisce nulla. Sul modello di
ml/analizza_posizionale.py.

SCOPO.  Rispondere a UNA domanda con un TASSO onesto (non un volume): sbaglio di
piu' (in PROPORZIONE) nelle posizioni CHIUSE, APERTE o semiaperte?  Questo decide
se la feature "aperta/chiusa" e' DIAGNOSTICA (i tassi divergono) o INERTE
(calcolabile ma inutile per l'allenamento, perche' i tassi sono simili).  Non
costruisce niente: solo misura e mette i numeri in chiaro.

CLASSIFICAZIONE aperta/chiusa/semiaperta [STIMA].  Strada B: regole trasparenti,
NIENTE punteggio pesato, calcolate dal solo FEN con python-chess.
  - blocchi_pedonali_centrali: numero di COPPIE bloccanti (ram) sulle colonne
    c,d,e,f. Una coppia bloccante e' un pedone su una casa e il pedone avversario
    sulla casa immediatamente davanti (stessa colonna, traverse adiacenti). Le
    catene diagonali tipo d4-e5 vs d5-e6 si scompongono in coppie frontali (d4/d5
    sulla colonna d, e5/e6 sulla colonna e) e quindi sono gia' contate.
  - colonne_aperte: numero di colonne (a-h) SENZA alcun pedone, di nessun colore.
  - REGOLE (soglie iniziali, DICHIARATE in testa all'output, da raffinare sui
    campioni):
        chiusa     = blocchi_pedonali_centrali >= 2 AND colonne_aperte == 0
        aperta     = colonne_aperte >= 2 AND blocchi_pedonali_centrali <= 1
        semiaperta = tutto il resto

MISURA (il cuore: TASSO, non volume).
  - Per OGNI mia mossa non-bullet in data/analisi/*.json (NON solo gli errori),
    classifico la posizione (fen). Questo costruisce i DENOMINATORI: quante mosse
    totali gioco in ciascun tipo di posizione.
  - Marco quali di quelle mosse sono ERRORI POSIZIONALI PURI riusando ESATTAMENTE
    il filtro di ml/analizza_posizionale.py (e_posizionale_puro: cl>=200, posizione
    sana, best non cattura/scacco/promozione, best non tattica nota). Questi sono i
    NUMERATORI.
  - Per ciascun tipo stampo: mosse_totali [DATO], errori_posizionali [DATO] e il
    TASSO = errori/mosse * 100 [DATO]. Piu' la distribuzione grezza dei tipi.

IL NUMERO CHE DECIDE: il confronto fra i tre TASSI.  Se il tasso nelle chiuse e'
nettamente piu' alto che nelle aperte (o viceversa) -> feature DIAGNOSTICA. Se i
tre tassi sono simili -> feature INERTE, e va detto.

CAMPIONI (controllo anti-T3): per ciascun tipo stampo 5 FEN di esempio + i due
conteggi (blocchi, colonne aperte) che hanno prodotto la classificazione, cosi'
verifichiamo a occhio che una "chiusa" sia davvero chiusa.

Uso:  python ml/analizza_apertachiusa.py
"""

# ============================================================================
# ESITO (punto 5 — feature posizionali diagnostiche): INERTE. Prova di un "no".
# Domanda: la classificazione aperta/chiusa/semiaperta discrimina DOVE sbaglio?
# Metodo: TASSO (errori posizionali / mosse) per tipo, non volume.
# Risultato: aperta 2.34% / chiusa 3.37% / semiaperta 2.29%, rapporto 1.47x (sotto
# soglia 1.50x). E la classe "chiusa" e' fragile (1721 mosse), tasso instabile.
# VERDETTO: INERTE. Calcolabile ma non discrimina gli errori. Le due classi grandi
# (aperta, semiaperta) su migliaia di mosse sono indistinguibili → dove il dato e'
# robusto, la feature non separa. Coerente col muro del punto 5: margine diffuso,
# non strutturale. Script tenuto come prova del "no". Vedi DA_FARE.md 5h.

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

# Riuso le utility gia' esistenti (come fa analizza_posizionale.py). Lo script gira
# da ml/ e in quel caso ml/ e' su sys.path: gli import "piatti" funzionano.
# Fallback prudente nel caso (raro) in cui non lo fossero.
try:
    from estrai_errori import (
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista,
    )
    from converti_vantaggio import e_bullet
    from analizza_posizionale import e_posizionale_puro
except Exception:  # pragma: no cover - solo fallback se gli import piatti falliscono
    from ml.estrai_errori import (  # noqa: F811
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista,
    )
    from ml.converti_vantaggio import e_bullet
    from ml.analizza_posizionale import e_posizionale_puro

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)

# --- SOGLIE DELLA CLASSIFICAZIONE (dichiarate e modificabili) -----------------
# Iniziali, da raffinare guardando i campioni. Stampate in testa all'output.
SOGLIA_BLOCCHI_CHIUSA = 2    # chiusa: blocchi_pedonali_centrali >= questo
SOGLIA_COLONNE_CHIUSA = 0    # chiusa: colonne_aperte == questo
SOGLIA_COLONNE_APERTA = 2    # aperta: colonne_aperte >= questo
SOGLIA_BLOCCHI_APERTA = 1    # aperta: blocchi_pedonali_centrali <= questo

# Colonne centrali su cui si contano i blocchi frontali: c=2, d=3, e=4, f=5.
COLONNE_CENTRALI = (2, 3, 4, 5)

TIPI = ("chiusa", "aperta", "semiaperta")


# ----------------------------------------------------------------------------
# Classificazione aperta/chiusa/semiaperta [STIMA] - solo dal FEN
# ----------------------------------------------------------------------------

def blocchi_pedonali_centrali(board):
    """
    [STIMA-componente] Numero di COPPIE bloccanti (ram) sulle colonne c,d,e,f:
    pedone bianco su (colonna, r) con pedone nero su (colonna, r+1), cioe' i due
    pedoni si fronteggiano sulla stessa colonna a traverse adiacenti e si bloccano.
    Le catene diagonali interbloccate (d4-e5 vs d5-e6) si scompongono in piu' di
    queste coppie frontali e quindi sono gia' incluse nel conteggio.
    """
    n = 0
    for colonna in COLONNE_CENTRALI:
        for r in range(7):  # r..r+1, quindi r arriva fino a 6
            sotto = board.piece_at(chess.square(colonna, r))
            sopra = board.piece_at(chess.square(colonna, r + 1))
            if (sotto is not None and sotto.piece_type == chess.PAWN
                    and sotto.color == chess.WHITE
                    and sopra is not None and sopra.piece_type == chess.PAWN
                    and sopra.color == chess.BLACK):
                n += 1
    return n


def colonne_aperte(board):
    """[STIMA-componente] Colonne (a-h) senza alcun pedone, di nessun colore."""
    n = 0
    for colonna in range(8):
        vuota = True
        for r in range(8):
            p = board.piece_at(chess.square(colonna, r))
            if p is not None and p.piece_type == chess.PAWN:
                vuota = False
                break
        if vuota:
            n += 1
    return n


def classifica_struttura(fen):
    """
    [STIMA] Restituisce (tipo, blocchi, aperte) dove tipo e' uno di
    'chiusa'/'aperta'/'semiaperta' secondo le REGOLE dichiarate in testa.
    """
    board = chess.Board(fen)
    blocchi = blocchi_pedonali_centrali(board)
    aperte = colonne_aperte(board)
    if blocchi >= SOGLIA_BLOCCHI_CHIUSA and aperte == SOGLIA_COLONNE_CHIUSA:
        tipo = "chiusa"
    elif aperte >= SOGLIA_COLONNE_APERTA and blocchi <= SOGLIA_BLOCCHI_APERTA:
        tipo = "aperta"
    else:
        tipo = "semiaperta"
    return tipo, blocchi, aperte


# ----------------------------------------------------------------------------
# Aggregazione (sola lettura)
# ----------------------------------------------------------------------------

def _nuovo_riepilogo():
    """Struttura vuota dei conteggi."""
    return {
        # DENOMINATORE: tutte le mie mosse non-bullet, per tipo di posizione.
        "mosse_totali": Counter(),
        # NUMERATORE: errori posizionali puri, per tipo di posizione.
        "errori_posizionali": Counter(),
        # Campioni per verifica manuale: per tipo, lista di (fen, blocchi, aperte).
        "campioni": defaultdict(list),
        "partite_bullet_escluse": 0,
        "file_saltati": 0,           # non gioco io / illeggibili
    }


def analizza_cartella(cartella=CARTELLA_ANALISI):
    """
    Scorre tutte le analisi (SOLA LETTURA). Per ogni mia mossa non-bullet classifica
    la posizione (denominatore) e marca se e' un errore posizionale puro (numeratore).
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

            tipo, blocchi, aperte = classifica_struttura(mossa["fen"])
            rie["mosse_totali"][tipo] += 1
            if len(rie["campioni"][tipo]) < 5:
                rie["campioni"][tipo].append((mossa["fen"], blocchi, aperte))

            eval_mia = eval_dal_mio_punto_di_vista(mossa["eval_prima"], sono_bianco)
            if e_posizionale_puro(mossa, eval_mia):
                rie["errori_posizionali"][tipo] += 1

    return rie


def _pct(parte, totale):
    """Percentuale robusta: 0.0 se il totale e' zero (evita divisioni per zero)."""
    return (100.0 * parte / totale) if totale else 0.0


# ----------------------------------------------------------------------------
# Stampa
# ----------------------------------------------------------------------------

def _stampa_soglie():
    print("  SOGLIE DELLA CLASSIFICAZIONE (dichiarate, modificabili nel sorgente):")
    print(f"    chiusa     = blocchi_pedonali_centrali >= {SOGLIA_BLOCCHI_CHIUSA} "
          f"AND colonne_aperte == {SOGLIA_COLONNE_CHIUSA}")
    print(f"    aperta     = colonne_aperte >= {SOGLIA_COLONNE_APERTA} "
          f"AND blocchi_pedonali_centrali <= {SOGLIA_BLOCCHI_APERTA}")
    print("    semiaperta = tutto il resto")
    print(f"    (blocchi contati sulle colonne centrali c,d,e,f; colonne aperte su a-h)")
    print()


def _stampa_distribuzione_grezza(mosse_totali):
    """Quante posizioni totali sono chiuse/aperte/semiaperte (bilanciamento)."""
    totale = sum(mosse_totali.values())
    print("  DISTRIBUZIONE GREZZA DEI TIPI [DATO]")
    print("  (le mie posizioni non-bullet sono bilanciate fra i tre tipi o no?)")
    print(f"    {'tipo':<12} {'mosse':>8} {'%':>8}")
    print(f"    {'-'*12} {'-'*8:>8} {'-'*8:>8}")
    for tipo in TIPI:
        n = mosse_totali.get(tipo, 0)
        print(f"    {tipo:<12} {n:>8} {_pct(n, totale):>7.1f}%")
    print(f"    {'TOTALE':<12} {totale:>8}")
    print()


def _stampa_tassi(mosse_totali, errori_posizionali):
    """Il cuore: TASSO = errori/mosse per tipo (il numero che decide)."""
    print("  TASSO DI ERRORE POSIZIONALE PER TIPO [DATO]  (il numero che decide)")
    print(f"    {'tipo':<12} {'mosse_tot':>10} {'errori_pos':>11} {'TASSO':>9}")
    print(f"    {'-'*12} {'-'*10:>10} {'-'*11:>11} {'-'*9:>9}")
    tassi = {}
    for tipo in TIPI:
        mosse = mosse_totali.get(tipo, 0)
        errori = errori_posizionali.get(tipo, 0)
        tasso = _pct(errori, mosse)
        tassi[tipo] = (mosse, errori, tasso)
        print(f"    {tipo:<12} {mosse:>10} {errori:>11} {tasso:>8.2f}%")
    print()
    return tassi


def _stampa_verdetto(tassi):
    """
    Confronto fra i tre tassi -> feature DIAGNOSTICA o INERTE. Soglia di giudizio
    dichiarata: se max/min dei tassi (sui tipi con abbastanza mosse) supera 1.5x
    la divergenza e' netta; altrimenti i tassi sono simili.
    """
    # Considero solo i tipi con un minimo di mosse, per non farmi ingannare dal rumore.
    MIN_MOSSE = 30
    validi = {t: v for t, v in tassi.items() if v[0] >= MIN_MOSSE and v[2] > 0}

    print("  --- IL NUMERO CHE DECIDE: confronto fra i tassi ---")
    if len(validi) < 2:
        print("    Non ci sono abbastanza tipi con dati sufficienti "
              f"(>= {MIN_MOSSE} mosse e tasso > 0) per un confronto onesto.")
        print("    VERDETTO: indeterminato su questo campione.")
        print()
        return

    tasso_max = max(validi.values(), key=lambda v: v[2])
    tasso_min = min(validi.values(), key=lambda v: v[2])
    tipo_max = [t for t, v in validi.items() if v == tasso_max][0]
    tipo_min = [t for t, v in validi.items() if v == tasso_min][0]
    rapporto = tasso_max[2] / tasso_min[2] if tasso_min[2] else float("inf")

    print(f"    Tasso piu' ALTO : {tipo_max:<11} {tasso_max[2]:.2f}%")
    print(f"    Tasso piu' BASSO: {tipo_min:<11} {tasso_min[2]:.2f}%")
    print(f"    Rapporto max/min: {rapporto:.2f}x  (soglia di nettezza dichiarata: 1.50x)")
    print()
    if rapporto >= 1.5:
        print(f"    VERDETTO: feature DIAGNOSTICA. Sbaglio (in proporzione) di piu' nelle")
        print(f"    posizioni '{tipo_max}' che nelle '{tipo_min}'. La distinzione")
        print("    aperta/chiusa separa contesti di errore diversi -> puo' servire.")
    else:
        print("    VERDETTO: feature INERTE. I tre tassi sono simili: la posizione")
        print("    aperta/chiusa e' CALCOLABILE ma NON discrimina dove sbaglio. Va detto:")
        print("    misurabile != utile. Non aggiunge potere diagnostico all'allenamento.")
    print()


def _stampa_campioni(campioni):
    """Per ciascun tipo, 5 FEN + i due conteggi che hanno prodotto la classificazione."""
    print("  CAMPIONI per verifica manuale (controllo anti-T3) [STIMA]")
    print("  (incolla la FEN su una scacchiera e controlla che la classe sia plausibile)")
    print()
    for tipo in TIPI:
        esempi = campioni.get(tipo, [])
        print(f"    --- {tipo}  ({len(esempi)} esempi mostrati) ---")
        if not esempi:
            print("      (nessun esempio su questo campione)")
        for fen, blocchi, aperte in esempi:
            print(f"      blocchi_centrali={blocchi}  colonne_aperte={aperte}")
            print(f"        fen: {fen}")
        print()


def _stampa_riepilogo(rie):
    """Stampa l'intera misurazione (denominatori, tassi, verdetto, campioni)."""
    print()
    print("=== APERTA / CHIUSA / SEMIAPERTA: tasso di errore (SOLA MISURAZIONE) ===")
    print()
    _stampa_soglie()
    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']} "
          f"(in bullet l'errore e' spesso il tempo, non la posizione)")
    print(f"  File saltati (non gioco io / illeggibili): {rie['file_saltati']}")
    print()
    print("  LEGENDA: [STIMA] = classificazione aperta/chiusa (euristica grezza)")
    print("           [DATO]  = i tassi e i conteggi (calcolo certo sui dati)")
    print()

    _stampa_distribuzione_grezza(rie["mosse_totali"])
    tassi = _stampa_tassi(rie["mosse_totali"], rie["errori_posizionali"])
    _stampa_verdetto(tassi)
    _stampa_campioni(rie["campioni"])

    print("  NOTA DI ONESTA': la classificazione e' [STIMA] con regole grezze e soglie")
    print("  iniziali; i campioni servono proprio a smentirla a occhio. Il numero che")
    print("  conta NON e' il volume di errori per tipo, ma il TASSO (errori/mosse): solo")
    print("  il tasso dice se sbaglio DI PIU' in un tipo di posizione a parita' di occasioni.")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_cartella()

    if sum(riepilogo["mosse_totali"].values()) == 0:
        print("\nNessuna mia mossa non-bullet trovata "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_riepilogo(riepilogo)
