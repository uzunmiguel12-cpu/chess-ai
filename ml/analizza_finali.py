# ============================================================================
# ESITO (punto 5 — tecnica di finale): DIAGNOSTICA ✅ — il PRIMO "si'" del filone
# posizionale, dopo cinque "no" (re-esposto, natura-best, aperta/chiusa, pedoni-deboli
# + il muro generale). A differenza di quelli, qui il segnale REGGE.
# ----------------------------------------------------------------------------
# Domanda: tra gli errori posizionali IN FINALE, sbaglio di piu' in un TIPO di finale?
# Metodo: TASSO (errori posizionali / mosse) per tipo, non volume. Bullet escluso.
# Risultato (misurato + verificato a campione, controllo-fase incluso):
#   finale_torre  3.4% (3443 mosse)  <- PEGGIORE, robusto
#   finale_minori 3.3% (821)
#   finale_pedoni 2.5% (471)
#   finale_misto  1.9% (2616)
#   finale_donna  0.9% (3020)  <- migliore
#   rapporto max/min 3.63x, i due estremi entrambi su migliaia di mosse (non fragili).
# Perche' e' vero e non frequenza: il TASSO normalizza il volume; torre e' anche il
# finale piu' giocato MA ci sbaglio di piu' a parita' di occasioni. Coerente col punto 5:
# donna = calcolo tattico (gia' allenato), torre = tecnica posizionale (il vero margine).
#
# PORTATO IN PIPELINE (strada snella): conta_pezzi/classifica_finale spostate in
# ml/finali.py (una sola versione, questo script le re-importa); tassi_finali_per_tipo
# agganciata a costruisci_profilo -> campo profilo["finali_per_tipo"]; esposto nel report
# come sezione "studio_fasi" (denominatore proprio, separata dal piano tattico) con
# rimando attivabile al tema finale_di_torre (rookEndgame, 54k puzzle alla fascia).
# NOTA: qui lo script esclude il bullet a livello file (data/analisi); la pipeline lo
# esclude al call-site in profilo.py. Vedi DA_FARE.md 5i. Script tenuto come prova.
# ============================================================================
"""
Modulo di SOLA MISURAZIONE - sola lettura: NON tocca data/, NON scrive alcuno
stato, NON salva file, NON costruisce nulla. Sul modello di
ml/analizza_pedonideboli.py e ml/analizza_apertachiusa.py.

SCOPO.  Rispondere a UNA domanda con un TASSO onesto (non un volume): tra i miei
errori posizionali IN FINALE, sbaglio di piu' (in PROPORZIONE) in un TIPO di
finale specifico?  Questo decide se la tecnica di finale e' DIAGNOSTICABILE per
tipo (i tassi divergono) o e' un altro MURO / troppo FRAGILE (tassi simili o
classi troppo piccole).  Non costruisce niente: solo misura e mette i numeri in
chiaro.  Pista suggerita dall'ESITO di analizza_posizionale.py (finale = 17.2%
degli errori posizionali, quasi tutto torre+re): qui la scomponiamo per tipo.

AMBITO.  SOLO le posizioni in fase == 'finale', usando la STESSA determinazione
di fase gia' nel progetto (ml/categorizza.py: classifica_fase, < 4 pezzi diversi
da pedoni/re -> finale). Non la reinvento. Bullet escluso come sempre.

CLASSIFICAZIONE tipo_finale [DATO, dal conteggio pezzi nel FEN con python-chess].
Conta i pezzi di ENTRAMBI i colori esclusi i due re (e' il materiale sulla
scacchiera che definisce il finale). Con
  donne  = donne (bianche + nere)
  torri  = torri (bianche + nere)
  minori = alfieri + cavalli (bianchi + neri)
le REGOLE, in ordine di precedenza (DICHIARATE in testa, ristampate in output):
  - finale_donna   = donne >= 1            (almeno una donna presente, comunque)
  - finale_pedoni  = donne=0, torri=0, minori=0   (nessun pezzo, solo pedoni)
  - finale_torre   = donne=0, minori=0, torri>=1  (solo torri + pedoni)
  - finale_minori  = donne=0, torri=0, minori>=1  (solo alfieri/cavalli + pedoni)
  - finale_misto   = tutto il resto (es. torre + minore, piu' pezzi pesanti)

MISURA (il cuore: TASSO, non volume) - SOLO su posizioni in fase finale.
  - Per OGNI mia mossa non-bullet IN FINALE classifico il tipo_finale: sono i
    DENOMINATORI (quante mosse totali gioco in ciascun tipo di finale).
  - Marco quali di quelle mosse sono ERRORI POSIZIONALI PURI riusando ESATTAMENTE
    il filtro di ml/analizza_posizionale.py (e_posizionale_puro): i NUMERATORI.
  - Per ciascun tipo stampo mosse_tot [DATO], errori_pos [DATO] e il
    TASSO = errori/mosse * 100 [DATO], piu' la distribuzione grezza dei tipi.

IL NUMERO CHE DECIDE: il confronto fra i TASSI (stessa soglia di nettezza degli
altri script: rapporto max/min >= 1.50x sui soli tipi con >= MIN_MOSSE mosse).
Un tipo nettamente piu' alto -> DIAGNOSTICA. Tassi simili -> INERTE. Classi sotto
MIN_MOSSE segnalate come 'fragile' (non ci grido diagnostica sopra).

CAMPIONI (controllo anti-T3): per ciascun tipo 5 FEN di esempio, presi da PARTITE
DIVERSE quando possibile, col conteggio pezzi (donne/torri/alfieri/cavalli) che
ha prodotto la classificazione, per verifica a occhio.

Uso:  python ml/analizza_finali.py
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

# Riuso le utility gia' esistenti (come fanno analizza_pedonideboli.py e
# analizza_apertachiusa.py). Lo script gira da ml/ e in quel caso ml/ e' su
# sys.path: gli import "piatti" funzionano. Fallback prudente se non lo fossero.
try:
    from estrai_errori import (
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista,
    )
    from converti_vantaggio import e_bullet
    from analizza_posizionale import e_posizionale_puro
    from categorizza import classifica_fase
    # conta_pezzi, classifica_finale e MIN_MOSSE vivono ora in ml/finali.py (UNA
    # sola versione): li importo cosi' lo script gira identico e la classificazione
    # non puo' divergere dal profilo.
    from finali import conta_pezzi, classifica_finale, MIN_MOSSE
except Exception:  # pragma: no cover - solo fallback se gli import piatti falliscono
    from ml.estrai_errori import (  # noqa: F811
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista,
    )
    from ml.converti_vantaggio import e_bullet
    from ml.analizza_posizionale import e_posizionale_puro
    from ml.categorizza import classifica_fase
    from ml.finali import conta_pezzi, classifica_finale, MIN_MOSSE

CARTELLA_ANALISI = os.path.join(
    os.path.dirname(__file__), "..", "data", "analisi"
)

# --- SOGLIE DEL VERDETTO (dichiarate, identiche agli altri script) ------------
# MIN_MOSSE e' importato da ml/finali.py (unica definizione, per non divergere).
SOGLIA_NETTEZZA = 1.5  # rapporto max/min dei tassi oltre cui la divergenza e' netta

# Ordine di stampa dei tipi di finale.
TIPI = (
    "finale_pedoni", "finale_torre", "finale_minori", "finale_donna",
    "finale_misto",
)


# ----------------------------------------------------------------------------
# Classificazione tipo_finale [DATO]: conta_pezzi e classifica_finale sono ora in
# ml/finali.py (importate sopra) - stessa logica, una sola versione.
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# Aggregazione (sola lettura)
# ----------------------------------------------------------------------------

def _nuovo_riepilogo():
    """Struttura vuota dei conteggi."""
    return {
        "mosse_totali": Counter(),          # DENOMINATORE: mie mosse non-bullet in finale per tipo
        "errori_posizionali": Counter(),    # NUMERATORE: errori posizionali puri per tipo
        # Campioni: per tipo lista di (fen, dettaglio). Provo a prenderli da
        # partite DIVERSE (campioni_partite tiene le partite gia' usate per quel tipo).
        "campioni": defaultdict(list),
        "campioni_partite": defaultdict(set),
        "campioni_riserva": defaultdict(list),  # ripiego se le partite distinte finiscono
        "partite_bullet_escluse": 0,
        "file_saltati": 0,                  # non gioco io / illeggibili
        "mosse_non_finale": 0,              # mie mosse non-bullet fuori dal finale (scartate)
    }


def _aggiungi_campione(rie, tipo, partita, fen, dettaglio):
    """Tiene fino a 5 campioni per tipo, preferendo partite diverse."""
    campione = (fen, dettaglio)
    if len(rie["campioni"][tipo]) < 5 and partita not in rie["campioni_partite"][tipo]:
        rie["campioni"][tipo].append(campione)
        rie["campioni_partite"][tipo].add(partita)
    elif len(rie["campioni_riserva"][tipo]) < 5:
        rie["campioni_riserva"][tipo].append(campione)


def analizza_cartella(cartella=CARTELLA_ANALISI):
    """
    Scorre tutte le analisi (SOLA LETTURA). Per ogni mia mossa non-bullet IN
    FINALE classifica il tipo di finale (denominatore) e marca se e' un errore
    posizionale puro (numeratore). Le mosse fuori dal finale sono scartate.
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

            # AMBITO: solo fase finale (stessa determinazione del progetto).
            if classifica_fase(mossa["fen"]) != "finale":
                rie["mosse_non_finale"] += 1
                continue

            tipo, dettaglio = classifica_finale(mossa["fen"])
            rie["mosse_totali"][tipo] += 1
            _aggiungi_campione(rie, tipo, partita, mossa["fen"], dettaglio)

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

def _stampa_regole():
    print("  REGOLE DELLA CLASSIFICAZIONE (dichiarate, dal conteggio pezzi nel FEN):")
    print("    conteggi: donne / torri / minori(=alfieri+cavalli), ENTRAMBI i colori,")
    print("    esclusi i due re. In ordine di precedenza:")
    print("      finale_donna   = donne >= 1")
    print("      finale_pedoni  = donne=0, torri=0, minori=0")
    print("      finale_torre   = donne=0, minori=0, torri>=1")
    print("      finale_minori  = donne=0, torri=0, minori>=1")
    print("      finale_misto   = tutto il resto (es. torre + minore, piu' pezzi pesanti)")
    print()


def _stampa_distribuzione_grezza(mosse_totali):
    """Quante mie mosse in finale cadono in ciascun tipo (bilanciamento)."""
    totale = sum(mosse_totali.values())
    print("  DISTRIBUZIONE GREZZA DEI TIPI DI FINALE [DATO]")
    print("  (le mie mosse non-bullet in finale sono bilanciate fra i tipi o no?)")
    print(f"    {'tipo':<15} {'mosse':>8} {'%':>8}")
    print(f"    {'-'*15} {'-'*8:>8} {'-'*8:>8}")
    for tipo in TIPI:
        n = mosse_totali.get(tipo, 0)
        print(f"    {tipo:<15} {n:>8} {_pct(n, totale):>7.1f}%")
    print(f"    {'TOTALE':<15} {totale:>8}")
    print()


def _stampa_tassi(mosse_totali, errori_posizionali):
    """Il cuore: TASSO = errori/mosse per tipo (il numero che decide)."""
    print("  TASSO DI ERRORE POSIZIONALE PER TIPO DI FINALE [DATO]  (il numero che decide)")
    print(f"    {'tipo':<15} {'mosse_tot':>10} {'errori_pos':>11} {'TASSO':>9}  nota")
    print(f"    {'-'*15} {'-'*10:>10} {'-'*11:>11} {'-'*9:>9}")
    tassi = {}
    for tipo in TIPI:
        mosse = mosse_totali.get(tipo, 0)
        errori = errori_posizionali.get(tipo, 0)
        tasso = _pct(errori, mosse)
        tassi[tipo] = (mosse, errori, tasso)
        nota = "fragile (< MIN_MOSSE)" if mosse < MIN_MOSSE else ""
        print(f"    {tipo:<15} {mosse:>10} {errori:>11} {tasso:>8.2f}%  {nota}")
    print()
    return tassi


def _stampa_verdetto(tassi):
    """
    Confronto fra i tassi -> tecnica di finale DIAGNOSTICA per tipo o INERTE/FRAGILE.
    Stessa soglia di nettezza e stesso MIN_MOSSE degli altri script: non grido
    diagnostica su classi piccole.
    """
    validi = {t: v for t, v in tassi.items() if v[0] >= MIN_MOSSE and v[2] > 0}
    fragili = [t for t, v in tassi.items() if 0 < v[0] < MIN_MOSSE]

    print("  --- IL NUMERO CHE DECIDE: confronto fra i tassi ---")
    if fragili:
        print(f"    Tipi FRAGILI (sotto {MIN_MOSSE} mosse, esclusi dal confronto): "
              f"{', '.join(fragili)}")
    if len(validi) < 2:
        print("    Non ci sono abbastanza tipi con dati sufficienti "
              f"(>= {MIN_MOSSE} mosse e tasso > 0) per un confronto onesto.")
        print("    VERDETTO: INERTE/FRAGILE su questo campione (indeterminato).")
        print()
        return

    tasso_max = max(validi.values(), key=lambda v: v[2])
    tasso_min = min(validi.values(), key=lambda v: v[2])
    tipo_max = [t for t, v in validi.items() if v == tasso_max][0]
    tipo_min = [t for t, v in validi.items() if v == tasso_min][0]
    rapporto = tasso_max[2] / tasso_min[2] if tasso_min[2] else float("inf")

    print(f"    Tasso piu' ALTO : {tipo_max:<14} {tasso_max[2]:.2f}%")
    print(f"    Tasso piu' BASSO: {tipo_min:<14} {tasso_min[2]:.2f}%")
    print(f"    Rapporto max/min: {rapporto:.2f}x  "
          f"(soglia di nettezza dichiarata: {SOGLIA_NETTEZZA:.2f}x)")
    print()
    if rapporto >= SOGLIA_NETTEZZA:
        print("    VERDETTO: DIAGNOSTICA. Tra i finali, sbaglio (in proporzione) di piu'")
        print(f"    nel tipo '{tipo_max}' che nel tipo '{tipo_min}'. La tecnica di finale")
        print("    SI scompone per tipo -> puo' servire a mirare l'allenamento.")
    else:
        print("    VERDETTO: INERTE. I tassi sono simili tra i tipi di finale: il TIPO di")
        print("    finale e' CALCOLABILE ma NON discrimina dove sbaglio. Un altro muro:")
        print("    misurabile != utile. La tecnica di finale non si mira per tipo qui.")
    print()


def _formatta_dettaglio(dettaglio):
    """Riga compatta col conteggio pezzi che ha prodotto la classificazione."""
    return (f"donne={dettaglio['donne']}  torri={dettaglio['torri']}  "
            f"alfieri={dettaglio['alfieri']}  cavalli={dettaglio['cavalli']}")


def _stampa_campioni(rie):
    """Per ciascun tipo 5 FEN (da partite diverse se possibile) + conteggio pezzi."""
    print("  CAMPIONI per verifica manuale (controllo anti-T3) [DATO]")
    print("  (5 FEN per tipo, da partite diverse quando possibile; conta i pezzi a occhio)")
    print()
    for tipo in TIPI:
        esempi = list(rie["campioni"].get(tipo, []))
        # Ripiego: completa a 5 con la riserva (anche stessa partita) senza duplicare.
        if len(esempi) < 5:
            visti = {fen for fen, _ in esempi}
            for c in rie["campioni_riserva"].get(tipo, []):
                if len(esempi) >= 5:
                    break
                if c[0] not in visti:
                    esempi.append(c)
                    visti.add(c[0])
        print(f"    --- {tipo}  ({len(esempi)} esempi mostrati) ---")
        if not esempi:
            print("      (nessun esempio su questo campione)")
        for fen, dettaglio in esempi:
            print(f"      {_formatta_dettaglio(dettaglio)}")
            print(f"        fen: {fen}")
        print()


def _stampa_riepilogo(rie):
    """Stampa l'intera misurazione (denominatori, tassi, verdetto, campioni)."""
    print()
    print("=== TIPI DI FINALE: tasso di errore posizionale (SOLA MISURAZIONE) ===")
    print()
    _stampa_regole()
    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']} "
          f"(in bullet l'errore e' spesso il tempo, non la posizione)")
    print(f"  File saltati (non gioco io / illeggibili): {rie['file_saltati']}")
    print(f"  Mie mosse non-bullet FUORI dal finale (scartate dall'ambito): "
          f"{rie['mosse_non_finale']}")
    print()
    print("  LEGENDA: [DATO] = tutto e' calcolo certo dalla posizione (conteggi e tassi).")
    print("           Ambito: solo fase == finale (classifica_fase del progetto, < 4 pezzi).")
    print()

    _stampa_distribuzione_grezza(rie["mosse_totali"])
    tassi = _stampa_tassi(rie["mosse_totali"], rie["errori_posizionali"])
    _stampa_verdetto(tassi)
    _stampa_campioni(rie)

    print("  NOTA DI ONESTA': i conteggi e i tassi sono [DATO] (calcolo certo). Il numero")
    print("  che conta NON e' il volume di errori per tipo, ma il TASSO (errori/mosse):")
    print("  solo il tasso dice se sbaglio DI PIU' a parita' di occasioni in un tipo di")
    print("  finale. I tipi sotto MIN_MOSSE sono 'fragili' e non fanno verdetto.")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_cartella()

    if sum(riepilogo["mosse_totali"].values()) == 0:
        print("\nNessuna mia mossa non-bullet in finale trovata "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_riepilogo(riepilogo)
