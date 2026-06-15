"""
Modulo di SOLA LETTURA: NON tocca data/, NON scrive alcuno stato, NON salva file,
NON genera puzzle. Sul modello di ml/analizza_posizionale.py.

ESITO DELLA MISURAZIONE (Punto 5g, gia' concluso - questo script e' tenuto come
prova, NON e' lavoro in sospeso).  Quota cumulativa top-5 chiave_fen4: BIANCO 18.8%
(sparso, sotto la soglia 25%); NERO 31.0% ma trainato da un solo gruppo
(1.e4 e5 2.Nf3 Nc6, 18.8%) che e' l'apertura piu' GIOCATA, non un buco di teoria.
I campioni confermano: gli errori cadono a mossa 9/12/13 dentro lo stesso "gruppo
d'apertura" -> i gruppi condividono l'INIZIO, NON il pattern d'errore.  VERDETTO:
errori d'apertura SPARSI, un drill per-apertura renderebbe poco. Coerente con
ml/analizza_posizionale.py.

UNA SOLA DOMANDA.  Gli ERRORI POSIZIONALI PURI in APERTURA sono CONCENTRATI su
poche aperture/strutture ricorrenti (-> allenabile) o SPARSI su tante (-> muro,
inutile costruire un drill mirato)?  Qui si CONTA soltanto, non si genera nulla.

ERRORE POSIZIONALE PURO.  Riuso ESATTAMENTE il filtro di ml/analizza_posizionale.py
(importo e_posizionale_puro, NON riscrivo la logica): mia mossa, cl >= 200, cadenza
!= bullet, best che non cattura / non da' scacco / non promuove, best non tattica
nota a ml/tattica.py, filtro di sanita' +-700cp e niente mate-score.  Poi tengo
SOLO gli errori con fase == apertura (classifica_fase).

SEPARAZIONE PER COLORE.  Tutto e' tenuto distinto tra BIANCO e NERO, dove il colore
e' quello della MIA mossa (turno_da_fen == mio_colore), come in analizza_posizionale.

RICOSTRUZIONE DELLA PARTITA.  L'analisi elenca le mosse in ordine dall'inizio (ogni
voce ha la FEN PRIMA della mossa e move_uci).  Ricostruisco la linea dall'inizio
spingendo i move_uci finche' la posizione ricostruita combacia con la FEN attesa.
Se una partita non parte dalla posizione iniziale o perde il filo, i suoi errori
d'apertura sono dichiarati NON ricostruibili -> conteggio "n/d".

DUE CHIAVI DI RAGGRUPPAMENTO (entrambe [DATO], conteggio puro):
  - chiave_sequenza : i primi 3 mezze-mosse della partita in SAN, come stringa
                      (es. "1.e4 e5 2.Nf3"). Caratterizza l'ORDINE delle mosse.
  - chiave_fen4     : il FEN NORMALIZZATO dopo la 4a mezza-mossa = SOLO i primi 4
                      campi (pezzi, tratto, arrocchi, en-passant), SENZA contatori
                      di mossa, cosi' le TRASPOSIZIONI (ordini diversi, stessa
                      posizione) collassano nello stesso gruppo.

OUTPUT a terminale (italiano), separato per BIANCO e NERO:
  - denominatore: errori d'apertura del lato e quanti non ricostruibili (n/d);
  - TOP 10 per chiave_sequenza: gruppo, n, %;
  - TOP 10 per chiave_fen4: gruppo (con una sequenza-esempio leggibile), n, %;
  - QUOTA CUMULATIVA per ENTRAMBE le chiavi: % nei TOP 5 e nei TOP 10 (il numero
    che decide concentrato vs sparso);
  - per i TOP 3 gruppi chiave_fen4 di ciascun lato: campione di 3 esempi
    (fen completa + best in SAN + cl + numero di mossa).

CONTROLLO ANTI-INGANNO.  Confronto la quota cumulativa top-5 di chiave_sequenza
con quella di chiave_fen4.  Se fen4 e' nettamente piu' alta, gli errori erano
TRASPOSIZIONI (stessa posizione raggiunta con ordini diversi) e la verita' e' fen4.

Tutto e' [DATO] (conteggio diretto). Nessun salvataggio su file.

Uso:  python ml/analizza_aperture.py
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

# Riuso le funzioni gia' esistenti (NON riscrivo la logica): il filtro
# "errore posizionale puro" e i suoi helper vengono da analizza_posizionale.py,
# l'iterazione sulle analisi dagli stessi moduli che usa lui. Gli import "piatti"
# funzionano lanciando da ml/; fallback prudente con prefisso ml. .
try:
    from analizza_posizionale import (
        e_posizionale_puro, best_san, CARTELLA_ANALISI, SOGLIA_ERRORE,
    )
    from estrai_errori import (
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista,
    )
    from converti_vantaggio import e_bullet
    from categorizza import classifica_fase
except Exception:  # pragma: no cover - solo fallback se gli import piatti falliscono
    from ml.analizza_posizionale import (  # noqa: F811
        e_posizionale_puro, best_san, CARTELLA_ANALISI, SOGLIA_ERRORE,
    )
    from ml.estrai_errori import (  # noqa: F811
        mio_colore, turno_da_fen, eval_dal_mio_punto_di_vista,
    )
    from ml.converti_vantaggio import e_bullet  # noqa: F811
    from ml.categorizza import classifica_fase  # noqa: F811


# ----------------------------------------------------------------------------
# Ricostruzione della partita dall'inizio e chiavi di raggruppamento
# ----------------------------------------------------------------------------

def _fen4(fen):
    """Normalizzazione: SOLO i primi 4 campi del FEN (pezzi, tratto, arrocchi, e.p.)."""
    return " ".join(fen.split()[:4])


def linea_dall_inizio(mosse):
    """
    [DATO] Ricostruisce la linea della partita dall'inizio usando i move_uci in
    ordine. Restituisce (linea_uci, ricostruibile) dove:
      - linea_uci   : lista dei move_uci spinti finche' la posizione ricostruita
                      combacia (sui primi 4 campi del FEN) con la FEN attesa;
      - ricostruibile: lista bool, una per mossa, True se la posizione PRIMA di
                      quella mossa e' raggiungibile dall'inizio (= il filo regge).
    Appena la posizione ricostruita non combacia o una mossa e' illegale, il filo
    si spezza: da li' in poi tutte le mosse sono dichiarate non ricostruibili.
    """
    board = chess.Board()  # posizione iniziale standard
    linea = []
    ricostruibile = []
    filo = True
    for mossa in mosse:
        if filo and _fen4(board.fen()) == _fen4(mossa["fen"]):
            ricostruibile.append(True)
            try:
                board.push_uci(mossa["move_uci"])
                linea.append(mossa["move_uci"])
            except Exception:
                filo = False  # mossa illegale: il filo si spezza per le successive
        else:
            ricostruibile.append(False)
            filo = False
    return linea, ricostruibile


def _san_primi(linea_uci, n):
    """Lista dei primi `n` mezze-mosse in SAN, replicando la linea dall'inizio."""
    board = chess.Board()
    sans = []
    for u in linea_uci[:n]:
        mv = chess.Move.from_uci(u)
        sans.append(board.san(mv))
        board.push(mv)
    return sans


def _formatta_sequenza(sans):
    """Rende una lista di SAN come stringa leggibile con numeri di mossa: '1.e4 e5 2.Nf3'."""
    pezzi = []
    for i, s in enumerate(sans):
        if i % 2 == 0:
            pezzi.append(f"{i // 2 + 1}.{s}")
        else:
            pezzi.append(s)
    return " ".join(pezzi) if pezzi else "(vuota)"


def chiave_sequenza(linea_uci):
    """[DATO] Primi 3 mezze-mosse in SAN come stringa, o None se la linea e' vuota."""
    if not linea_uci:
        return None
    return _formatta_sequenza(_san_primi(linea_uci, 3))


def chiave_fen4(linea_uci):
    """
    [DATO] FEN normalizzato (primi 4 campi) DOPO la 4a mezza-mossa, o None se la
    linea ricostruibile ha meno di 4 mezze-mosse.
    """
    if len(linea_uci) < 4:
        return None
    board = chess.Board()
    for u in linea_uci[:4]:
        board.push_uci(u)
    return _fen4(board.fen())


def sequenza_esempio_fen4(linea_uci):
    """Sequenza leggibile (primi 4 SAN) che porta al fen4, per le etichette dei gruppi."""
    return _formatta_sequenza(_san_primi(linea_uci, 4))


# ----------------------------------------------------------------------------
# Raccolta (sola lettura)
# ----------------------------------------------------------------------------

def _nuovo_lato():
    """Strutture di conteggio per UN lato (bianco o nero)."""
    return {
        "tot_apertura": 0,        # tutti gli errori posizionali puri d'apertura
        "nd_ricostr": 0,          # non ricostruibili dall'inizio (niente linea)
        "nd_fen4": 0,             # ricostruibili ma linea < 4 mezze-mosse (no fen4)
        "per_sequenza": Counter(),
        "per_fen4": Counter(),
        "seq_esempio_fen4": {},   # chiave_fen4 -> sequenza-esempio leggibile
        "campioni_fen4": defaultdict(list),  # chiave_fen4 -> lista di esempi
    }


def _numero_mossa(fen):
    """[DATO] Numero di mossa (fullmove) letto dalla FEN."""
    try:
        return chess.Board(fen).fullmove_number
    except Exception:
        return None


def analizza_cartella(cartella=CARTELLA_ANALISI):
    """
    Scorre tutte le analisi (sola lettura), tiene solo gli errori posizionali puri
    in apertura e li raggruppa per le due chiavi, separando bianco e nero.
    """
    lati = {"bianco": _nuovo_lato(), "nero": _nuovo_lato()}
    rie = {
        "lati": lati,
        "partite_bullet_escluse": 0,
        "file_saltati": 0,
    }

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

        mosse = dato.get("mosse", [])
        # Ricostruzione una volta sola per partita: la firma d'apertura e' di partita.
        linea, ricostruibile = linea_dall_inizio(mosse)
        k_seq = chiave_sequenza(linea)
        k_fen4 = chiave_fen4(linea)
        seq_esempio = sequenza_esempio_fen4(linea) if linea else None

        nome_lato = "bianco" if colore == "w" else "nero"
        L = lati[nome_lato]
        sono_bianco = (colore == "w")

        for i, mossa in enumerate(mosse):
            # Una mossa e' MIA se il turno nel FEN corrisponde al mio colore.
            if turno_da_fen(mossa["fen"]) != colore:
                continue

            eval_mia = eval_dal_mio_punto_di_vista(mossa["eval_prima"], sono_bianco)
            if not e_posizionale_puro(mossa, eval_mia):
                continue
            if classifica_fase(mossa["fen"]) != "apertura":
                continue

            L["tot_apertura"] += 1

            # Errore non ricostruibile dall'inizio -> n/d (niente raggruppamento).
            if not ricostruibile[i] or k_seq is None:
                L["nd_ricostr"] += 1
                continue

            L["per_sequenza"][k_seq] += 1

            if k_fen4 is None:
                L["nd_fen4"] += 1
                continue

            L["per_fen4"][k_fen4] += 1
            L["seq_esempio_fen4"].setdefault(k_fen4, seq_esempio)
            if len(L["campioni_fen4"][k_fen4]) < 3:
                L["campioni_fen4"][k_fen4].append({
                    "fen": mossa["fen"],
                    "best_san": best_san(mossa["fen"], mossa["best_move_uci"]),
                    "cl": mossa["centipawn_loss"],
                    "n_mossa": _numero_mossa(mossa["fen"]),
                })

    return rie


# ----------------------------------------------------------------------------
# Stampa
# ----------------------------------------------------------------------------

def _pct(parte, totale):
    """Percentuale robusta: 0.0 se il totale e' zero."""
    return (100.0 * parte / totale) if totale else 0.0


def _stampa_legenda():
    print()
    print("LEGENDA: [DATO] = conteggio diretto (nessuna stima, nessuna euristica).")
    print("  chiave_sequenza = primi 3 mezze-mosse in SAN (es. '1.e4 e5 2.Nf3').")
    print("  chiave_fen4     = FEN normalizzato dopo la 4a mezza-mossa (primi 4 campi:")
    print("                    pezzi/tratto/arrocchi/en-passant, SENZA contatori), cosi'")
    print("                    le TRASPOSIZIONI collassano nello stesso gruppo.")
    print("  n/d             = errore d'apertura la cui posizione non e' ricostruibile")
    print("                    dall'inizio con le mosse presenti nell'analisi.")
    print("  La QUOTA CUMULATIVA (TOP 5 / TOP 10) e' il numero che decide:")
    print("  alta = errori CONCENTRATI su poche aperture (allenabile);")
    print("  bassa = errori SPARSI su tante (muro).")
    print()


def _stampa_top(titolo, contatore, totale_lato, marca):
    """Stampa la TOP 10 di una chiave (gruppo, n, %), % sul totale errori del lato."""
    print(f"  TOP 10 per {titolo}  {marca}")
    if not contatore:
        print("    (nessun gruppo)\n")
        return
    print(f"    {'#':>2}  {'n':>4} {'%':>7}  gruppo")
    print(f"    {'-'*2}  {'-'*4} {'-'*7}  {'-'*40}")
    for idx, (gruppo, n) in enumerate(contatore.most_common(10), 1):
        print(f"    {idx:>2}  {n:>4} {_pct(n, totale_lato):>6.1f}%  {gruppo}")
    print()


def _stampa_top_fen4(L, totale_lato):
    """TOP 10 per chiave_fen4 con la sequenza-esempio leggibile accanto al fen."""
    contatore = L["per_fen4"]
    print("  TOP 10 per chiave_fen4 (trasposizioni collassate)  [DATO]")
    if not contatore:
        print("    (nessun gruppo)\n")
        return
    print(f"    {'#':>2}  {'n':>4} {'%':>7}  esempio-sequenza  ->  fen4")
    print(f"    {'-'*2}  {'-'*4} {'-'*7}  {'-'*50}")
    for idx, (fen4, n) in enumerate(contatore.most_common(10), 1):
        esempio = L["seq_esempio_fen4"].get(fen4, "?")
        print(f"    {idx:>2}  {n:>4} {_pct(n, totale_lato):>6.1f}%  {esempio}")
        print(f"            -> {fen4}")
    print()


def _cumulativa(contatore, top_n):
    """Somma dei top_n gruppi piu' numerosi."""
    return sum(n for _, n in contatore.most_common(top_n))


def _stampa_cumulativa(L):
    """
    Quota cumulativa TOP 5 / TOP 10 per ENTRAMBE le chiavi e controllo anti-inganno.
    Le percentuali sono sul numero di errori EFFETTIVAMENTE raggruppabili con quella
    chiave (cosi' il confronto sequenza-vs-fen4 e' omogeneo e leale).
    """
    raggr_seq = sum(L["per_sequenza"].values())
    raggr_fen4 = sum(L["per_fen4"].values())

    seq5 = _pct(_cumulativa(L["per_sequenza"], 5), raggr_seq)
    seq10 = _pct(_cumulativa(L["per_sequenza"], 10), raggr_seq)
    fen5 = _pct(_cumulativa(L["per_fen4"], 5), raggr_fen4)
    fen10 = _pct(_cumulativa(L["per_fen4"], 10), raggr_fen4)

    print("  QUOTA CUMULATIVA (il numero che decide)  [DATO]")
    print(f"    chiave_sequenza  (su {raggr_seq} errori raggruppabili):"
          f"  TOP 5 = {seq5:.1f}%   TOP 10 = {seq10:.1f}%")
    print(f"    chiave_fen4      (su {raggr_fen4} errori raggruppabili):"
          f"  TOP 5 = {fen5:.1f}%   TOP 10 = {fen10:.1f}%")
    print()

    # Controllo anti-inganno: trasposizioni.
    print("  CONTROLLO ANTI-INGANNO (trasposizioni)  [DATO]")
    delta = fen5 - seq5
    if raggr_seq == 0 or raggr_fen4 == 0:
        print("    Dati insufficienti per il confronto.")
    elif delta >= 10.0:
        print(f"    fen4 TOP5 ({fen5:.1f}%) e' NETTAMENTE piu' alta della sequenza "
              f"({seq5:.1f}%), +{delta:.1f}pt:")
        print("    erano TRASPOSIZIONI (ordini di mossa diversi -> stessa posizione).")
        print("    La verita' e' fen4: la concentrazione reale e' quella.")
    elif delta <= -10.0:
        print(f"    sequenza TOP5 ({seq5:.1f}%) e' piu' alta di fen4 ({fen5:.1f}%), "
              f"{delta:.1f}pt: caso raro, le posizioni dopo la 4a si disperdono.")
    else:
        print(f"    sequenza TOP5 ({seq5:.1f}%) ~ fen4 TOP5 ({fen5:.1f}%), "
              f"scarto {delta:+.1f}pt: poche trasposizioni, le due chiavi concordano.")
    print()


def _stampa_campioni_fen4(L):
    """Per i TOP 3 gruppi chiave_fen4: campione di 3 esempi (fen + best SAN + cl + n.mossa)."""
    print("  CAMPIONI dei TOP 3 gruppi chiave_fen4 (verifica manuale)  [DATO]")
    if not L["per_fen4"]:
        print("    (nessun gruppo)\n")
        return
    for idx, (fen4, n) in enumerate(L["per_fen4"].most_common(3), 1):
        esempio = L["seq_esempio_fen4"].get(fen4, "?")
        print(f"    --- gruppo #{idx}: {esempio}  (n={n}) ---")
        print(f"        fen4: {fen4}")
        for s in L["campioni_fen4"].get(fen4, []):
            nm = s["n_mossa"] if s["n_mossa"] is not None else "?"
            print(f"        mossa {nm}: best={s['best_san']:<7} cl={s['cl']:>4}")
            print(f"          fen: {s['fen']}")
        print()


def _stampa_lato(nome, L):
    """Stampa l'intero blocco di un lato (denominatore, top, cumulativa, campioni)."""
    tot = L["tot_apertura"]
    print("=" * 74)
    print(f"  LATO: {nome.upper()}  (colore della MIA mossa)")
    print("=" * 74)
    print()
    print("  DENOMINATORE  [DATO]")
    print(f"    Errori posizionali puri in APERTURA: {tot}")
    print(f"    di cui NON ricostruibili dall'inizio (n/d): {L['nd_ricostr']}  "
          f"({_pct(L['nd_ricostr'], tot):.1f}%)")
    print(f"    di cui ricostruibili ma linea < 4 mezze-mosse (no fen4): {L['nd_fen4']}")
    print()

    if tot == 0:
        print("  Nessun errore d'apertura per questo lato: niente da raggruppare.\n")
        return

    _stampa_top("chiave_sequenza (ordine delle mosse)", L["per_sequenza"], tot, "[DATO]")
    _stampa_top_fen4(L, tot)
    _stampa_cumulativa(L)
    _stampa_campioni_fen4(L)


def _stampa_riepilogo(rie):
    print()
    print("=== Errori posizionali puri in APERTURA: concentrati o sparsi? (SOLA LETTURA) ===")
    _stampa_legenda()
    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']}")
    print(f"  File saltati (non gioco io / illeggibili): {rie['file_saltati']}")
    print()
    for nome in ("bianco", "nero"):
        _stampa_lato(nome, rie["lati"][nome])

    print("  NOTA DI ONESTA': si conta solo. 'Concentrato' (quota cumulativa alta) NON")
    print("  garantisce che il drill funzioni, ma dice DOVE guardare; 'sparso' (quota")
    print("  bassa) e' il segnale che un allenamento per-apertura renderebbe poco.")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_cartella()

    lati = riepilogo["lati"]
    if lati["bianco"]["tot_apertura"] == 0 and lati["nero"]["tot_apertura"] == 0:
        print("\nNessun mio errore posizionale puro in apertura trovato "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_riepilogo(riepilogo)
