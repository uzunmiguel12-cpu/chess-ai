"""
Modulo di SOLA MISURAZIONE - sola lettura: NON tocca data/, NON scrive alcuno
stato, NON salva file, NON costruisce nulla. Sul modello di
ml/analizza_apertachiusa.py.

SCOPO.  Rispondere a UNA domanda con un TASSO onesto (non un volume): sbaglio di
piu' (in PROPORZIONE) quando la MIA struttura pedonale e' debole?  Questo decide
se la feature "pedoni deboli" e' DIAGNOSTICA (i tassi divergono) o INERTE
(calcolabile ma inutile per l'allenamento, perche' i tassi sono simili).  Non
costruisce niente: solo misura e mette i numeri in chiaro.

CLASSIFICAZIONE pedoni deboli [DATO, calcolata dal FEN].  Conta SOLO i pedoni del
LATO CHE MUOVE (il mio): per le mie mosse il turno nel FEN e' il mio colore.
  - isolati  : mio pedone senza alcun mio pedone sulle 2 colonne adiacenti.
  - doppiati : conta le COLONNE con >= 2 miei pedoni (una colonna conta 1, non i
               singoli pedoni).
  - arretrati: mio pedone tale che (a) nessun mio pedone sulle colonne adiacenti e'
               alla sua altezza o piu' indietro (quindi non puo' essere difeso da un
               avanzamento di un vicino), E (b) la casa immediatamente davanti e'
               controllata da un pedone avversario. E' la definizione piu' SENSIBILE
               (vedi NOTA in fondo all'output): implementata con cura.
  pedoni_deboli_tot = isolati + colonne_doppiate + arretrati.

  REGOLE (soglie iniziali, DICHIARATE in testa all'output, raffinabili):
      struttura_sana   = pedoni_deboli_tot == 0
      intermedia       = pedoni_deboli_tot == 1
      struttura_debole = pedoni_deboli_tot >= 2

MISURA (il cuore: TASSO, non volume) - identica a ml/analizza_apertachiusa.py.
  - Per OGNI mia mossa non-bullet classifico la posizione (sana/intermedia/debole):
    sono i DENOMINATORI (quante mosse totali gioco in ciascun tipo).
  - Marco quali sono ERRORI POSIZIONALI PURI riusando ESATTAMENTE il filtro di
    ml/analizza_posizionale.py (e_posizionale_puro): sono i NUMERATORI.
  - Per ciascun tipo stampo mosse_tot [DATO], errori_pos [DATO] e il
    TASSO = errori/mosse * 100 [DATO], piu' la distribuzione grezza dei tipi.

IL NUMERO CHE DECIDE: il confronto fra i tre TASSI (stessa soglia di nettezza di
analizza_apertachiusa.py: rapporto max/min >= 1.50x sui tipi con abbastanza mosse).
Diverge nettamente -> feature DIAGNOSTICA. Tassi simili -> feature INERTE, e va detto.

CAMPIONI (controllo anti-T3): per ciascun tipo 5 FEN di esempio, presi da PARTITE
DIVERSE quando possibile (non i primi 5 della stessa partita), col dettaglio di QUALI
pedoni isolati/doppiati/arretrati hanno prodotto la classificazione. Verifica
particolare sugli 'arretrati'.

Uso:  python ml/analizza_pedonideboli.py
"""

# ============================================================================
# ESITO (punto 5 — feature posizionali diagnostiche): INERTE. Prova di un "no".
# Domanda: quando la MIA struttura pedonale e' debole (isolati/doppiati/arretrati),
# sbaglio di piu'? Metodo: TASSO per tipo (sana/intermedia/debole), non volume.
# Risultato: sana 2.23% / intermedia 2.55% / debole 2.39%, rapporto 1.14x, curva
# NON monotona (debole < intermedia). Denominatori tutti robusti (31k/12k/14k mosse).
# VERDETTO: INERTE, senza margine di dubbio. La curva disordinata smaschera l'assenza
# di segnale: se i pedoni deboli predicessero gli errori, sana<intermedia<debole. La
# sovrapposizione isolato+arretrato gonfia semmai "debole", che sbaglia MENO → il "no"
# e' se possibile piu' sicuro. Script tenuto come prova. Vedi DA_FARE.md 5h

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

# Riuso le utility gia' esistenti (come fa analizza_apertachiusa.py). Lo script gira
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
SOGLIA_DEBOLE = 2     # struttura_debole: pedoni_deboli_tot >= questo
SOGLIA_SANA = 0       # struttura_sana:   pedoni_deboli_tot == questo
# (intermedia = tutto il resto, cioe' pedoni_deboli_tot == 1)

TIPI = ("sana", "intermedia", "debole")

# Per il verdetto: stessa logica di analizza_apertachiusa.py.
MIN_MOSSE = 30        # ignoro i tipi sotto questa soglia (rumore)
SOGLIA_NETTEZZA = 1.5  # rapporto max/min dei tassi oltre cui la divergenza e' netta


# ----------------------------------------------------------------------------
# Classificazione pedoni deboli [DATO] - solo dal FEN, solo il lato che muove
# ----------------------------------------------------------------------------

def conta_pedoni_deboli(board, colore):
    """
    [DATO] Conta i pedoni deboli del solo `colore` (il lato che muove). Restituisce
    (tot, dettaglio) dove dettaglio elenca, per la verifica anti-T3, QUALI pedoni
    sono isolati/arretrati e QUALI colonne sono doppiate.
    """
    pedoni = list(board.pieces(chess.PAWN, colore))
    per_colonna = Counter(chess.square_file(s) for s in pedoni)
    direzione = 1 if colore == chess.WHITE else -1  # avanti = +1 Bianco, -1 Nero

    # isolati: nessun mio pedone sulle due colonne adiacenti.
    isolati = [
        s for s in pedoni
        if per_colonna.get(chess.square_file(s) - 1, 0) == 0
        and per_colonna.get(chess.square_file(s) + 1, 0) == 0
    ]

    # doppiati: COLONNE con >= 2 miei pedoni (la colonna conta 1, non i singoli).
    colonne_doppiate = sorted(f for f, n in per_colonna.items() if n >= 2)

    # arretrati: (a) nessun mio pedone adiacente alla sua altezza o piu' indietro
    # (tutti i vicini sono strettamente avanti, quindi non possono difenderlo
    # avanzando) E (b) la casa davanti e' controllata da un pedone avversario.
    arretrati = []
    for s in pedoni:
        f = chess.square_file(s)
        r = chess.square_rank(s)

        # (a) tutti i miei pedoni adiacenti devono essere strettamente AVANTI.
        a_ok = True
        for af in (f - 1, f + 1):
            if not 0 <= af < 8:
                continue
            for s2 in pedoni:
                if chess.square_file(s2) == af:
                    # "alla sua altezza o piu' indietro" => (r2 - r)*direzione <= 0.
                    if (chess.square_rank(s2) - r) * direzione <= 0:
                        a_ok = False
                        break
            if not a_ok:
                break
        if not a_ok:
            continue

        # (b) la casa immediatamente davanti (f, r+direzione) e' battuta da un
        # pedone avversario, cioe' un pedone nemico su (f-1, r+2*dir) o (f+1, r+2*dir).
        davanti = r + direzione
        if not 0 <= davanti < 8:
            continue
        controllata = False
        er = r + 2 * direzione
        if 0 <= er < 8:
            for ef in (f - 1, f + 1):
                if 0 <= ef < 8:
                    p = board.piece_at(chess.square(ef, er))
                    if (p is not None and p.piece_type == chess.PAWN
                            and p.color != colore):
                        controllata = True
                        break
        if controllata:
            arretrati.append(s)

    tot = len(isolati) + len(colonne_doppiate) + len(arretrati)
    dettaglio = {
        "isolati": [chess.square_name(s) for s in isolati],
        "colonne_doppiate": [chess.FILE_NAMES[f] for f in colonne_doppiate],
        "arretrati": [chess.square_name(s) for s in arretrati],
    }
    return tot, dettaglio


def classifica_struttura(fen):
    """
    [DATO] Restituisce (tipo, tot, dettaglio) con tipo in 'sana'/'intermedia'/'debole'
    secondo le REGOLE dichiarate, contando i soli pedoni del lato che muove.
    """
    board = chess.Board(fen)
    tot, dettaglio = conta_pedoni_deboli(board, board.turn)
    if tot == SOGLIA_SANA:
        tipo = "sana"
    elif tot >= SOGLIA_DEBOLE:
        tipo = "debole"
    else:
        tipo = "intermedia"
    return tipo, tot, dettaglio


# ----------------------------------------------------------------------------
# Aggregazione (sola lettura)
# ----------------------------------------------------------------------------

def _nuovo_riepilogo():
    """Struttura vuota dei conteggi."""
    return {
        "mosse_totali": Counter(),          # DENOMINATORE: mie mosse non-bullet per tipo
        "errori_posizionali": Counter(),    # NUMERATORE: errori posizionali puri per tipo
        # Campioni: per tipo lista di (fen, tot, dettaglio). Provo a prenderli da
        # partite DIVERSE (campioni_partite tiene le partite gia' usate per quel tipo).
        "campioni": defaultdict(list),
        "campioni_partite": defaultdict(set),
        "campioni_riserva": defaultdict(list),  # ripiego se le partite distinte finiscono
        "partite_bullet_escluse": 0,
        "file_saltati": 0,                  # non gioco io / illeggibili
    }


def _aggiungi_campione(rie, tipo, partita, fen, tot, dettaglio):
    """Tiene fino a 5 campioni per tipo, preferendo partite diverse."""
    campione = (fen, tot, dettaglio)
    if len(rie["campioni"][tipo]) < 5 and partita not in rie["campioni_partite"][tipo]:
        rie["campioni"][tipo].append(campione)
        rie["campioni_partite"][tipo].add(partita)
    elif len(rie["campioni_riserva"][tipo]) < 5:
        rie["campioni_riserva"][tipo].append(campione)


def analizza_cartella(cartella=CARTELLA_ANALISI):
    """
    Scorre tutte le analisi (SOLA LETTURA). Per ogni mia mossa non-bullet classifica
    la struttura pedonale (denominatore) e marca se e' un errore posizionale puro
    (numeratore).
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

        partita = os.path.basename(percorso)
        sono_bianco = (colore == "w")
        for mossa in dato.get("mosse", []):
            # Una mossa e' MIA se il turno nel FEN corrisponde al mio colore.
            if turno_da_fen(mossa["fen"]) != colore:
                continue

            tipo, tot, dettaglio = classifica_struttura(mossa["fen"])
            rie["mosse_totali"][tipo] += 1
            _aggiungi_campione(rie, tipo, partita, mossa["fen"], tot, dettaglio)

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
    print(f"    struttura_sana   = pedoni_deboli_tot == {SOGLIA_SANA}")
    print(f"    intermedia       = pedoni_deboli_tot == 1")
    print(f"    struttura_debole = pedoni_deboli_tot >= {SOGLIA_DEBOLE}")
    print("    pedoni_deboli_tot = isolati + colonne_doppiate + arretrati "
          "(solo i pedoni del lato che muove)")
    print()


def _stampa_distribuzione_grezza(mosse_totali):
    """Quante posizioni totali sono sane/intermedie/deboli (bilanciamento)."""
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
    Confronto fra i tre tassi -> feature DIAGNOSTICA o INERTE. Stessa soglia di
    nettezza dichiarata di analizza_apertachiusa.py (rapporto max/min, con MIN_MOSSE
    per non gridare diagnostica su classi piccole).
    """
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
    print(f"    Rapporto max/min: {rapporto:.2f}x  "
          f"(soglia di nettezza dichiarata: {SOGLIA_NETTEZZA:.2f}x)")
    print()
    if rapporto >= SOGLIA_NETTEZZA:
        print("    VERDETTO: feature DIAGNOSTICA. Sbaglio (in proporzione) di piu' nelle")
        print(f"    posizioni '{tipo_max}' che nelle '{tipo_min}'. La debolezza pedonale")
        print("    separa contesti di errore diversi -> puo' servire all'allenamento.")
    else:
        print("    VERDETTO: feature INERTE. I tre tassi sono simili: la debolezza")
        print("    pedonale e' CALCOLABILE ma NON discrimina dove sbaglio. Va detto:")
        print("    misurabile != utile. Non aggiunge potere diagnostico all'allenamento.")
    print()


def _formatta_dettaglio(tot, dettaglio):
    """Riga compatta col dettaglio dei conteggi che hanno prodotto la classificazione."""
    iso = dettaglio["isolati"]
    dop = dettaglio["colonne_doppiate"]
    arr = dettaglio["arretrati"]
    return (f"tot={tot}  | isolati={iso if iso else '-'}  "
            f"colonne_doppiate={dop if dop else '-'}  arretrati={arr if arr else '-'}")


def _stampa_campioni(rie):
    """Per ciascun tipo 5 FEN (da partite diverse se possibile) + dettaglio conteggi."""
    print("  CAMPIONI per verifica manuale (controllo anti-T3) [DATO]")
    print("  (presi da partite diverse quando possibile; verifica gli 'arretrati')")
    print()
    for tipo in TIPI:
        esempi = list(rie["campioni"].get(tipo, []))
        # Ripiego: completa a 5 con la riserva (anche stessa partita) senza duplicare.
        if len(esempi) < 5:
            visti = {fen for fen, _, _ in esempi}
            for c in rie["campioni_riserva"].get(tipo, []):
                if len(esempi) >= 5:
                    break
                if c[0] not in visti:
                    esempi.append(c)
                    visti.add(c[0])
        print(f"    --- {tipo}  ({len(esempi)} esempi mostrati) ---")
        if not esempi:
            print("      (nessun esempio su questo campione)")
        for fen, tot, dettaglio in esempi:
            print(f"      {_formatta_dettaglio(tot, dettaglio)}")
            print(f"        fen: {fen}")
        print()


def _stampa_riepilogo(rie):
    """Stampa l'intera misurazione (denominatori, tassi, verdetto, campioni)."""
    print()
    print("=== PEDONI DEBOLI: tasso di errore posizionale (SOLA MISURAZIONE) ===")
    print()
    _stampa_soglie()
    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']} "
          f"(in bullet l'errore e' spesso il tempo, non la posizione)")
    print(f"  File saltati (non gioco io / illeggibili): {rie['file_saltati']}")
    print()
    print("  LEGENDA: [DATO] = tutto e' calcolo certo dalla posizione (conteggi e tassi).")
    print("           'arretrato' resta la definizione piu' SENSIBILE: vedi NOTA in fondo.")
    print()

    _stampa_distribuzione_grezza(rie["mosse_totali"])
    tassi = _stampa_tassi(rie["mosse_totali"], rie["errori_posizionali"])
    _stampa_verdetto(tassi)
    _stampa_campioni(rie)

    print("  NOTA DI ONESTA': i conteggi sono [DATO] (calcolo certo), ma la DEFINIZIONE di")
    print("  'arretrato' e' la piu' sensibile alle scelte: richiede vicini tutti avanti E")
    print("  casa davanti battuta da un pedone avversario. Un pedone isolato puo' contare")
    print("  anche come arretrato (le categorie si sommano, non si escludono). Il numero")
    print("  che conta NON e' il volume per tipo, ma il TASSO (errori/mosse): solo il tasso")
    print("  dice se sbaglio DI PIU' a parita' di occasioni quando la struttura e' debole.")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_cartella()

    if sum(riepilogo["mosse_totali"].values()) == 0:
        print("\nNessuna mia mossa non-bullet trovata "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_riepilogo(riepilogo)
