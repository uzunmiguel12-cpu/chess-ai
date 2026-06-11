"""
Modulo validazione errori - USA Stockfish.

A differenza di estrai_errori.py (sola lettura), questo modulo apre il motore.

Scopo: prendere i candidati grezzi da data/candidati_errori.json (prodotti da
estrai_errori.py) e validarne l'UNICITA' della soluzione con Stockfish in
MultiPV. Un buon puzzle ha UNA mossa nettamente migliore di tutte le altre:
misuriamo il "gap" in centipawn tra la 1a e la 2a mossa migliore.

Due modalita':

  - TARATURA (tappa 2a, default): NON valida tutti gli 8546 candidati. Lavora su
    un CAMPIONE rappresentativo (mescolato con seed fisso) e stampa una tabella
    con i numeri, cosi' l'utente sceglie le soglie. Qui NON si salva nulla.
        python ml/valida_errori.py --campione 150 --profondita 18

  - BATCH (tappa 2b, flag --batch): ignora --campione e valida TUTTI i candidati
    non-bullet alla profondita' richiesta (default 18). Tiene un puzzle se il
    gap >= soglia (default 200 centipawn, vedi --gap) oppure se e' un matto a
    favore di chi muove; gli altri li conta soltanto. I puzzle tenuti finiscono
    in data/puzzle_errori.json. Il batch dura ~1 ora: salva in modo incrementale
    e, se interrotto, RIPARTE da dove era rimasto (usa --ricomincia per rifare
    tutto da zero).
        python ml/valida_errori.py --batch --profondita 18 --gap 200

L'utente ha deciso di ESCLUDERE i candidati con cadenza "bullet": vengono
saltati prima ancora di sprecare Stockfish su di essi.
"""

import os
import sys
import json
import time
import random
import logging
import argparse

import chess
import chess.engine

# Aggiungiamo engine/ al percorso per riusare la configurazione del motore.
CARTELLA_ENGINE = os.path.join(os.path.dirname(__file__), "..", "engine")
if CARTELLA_ENGINE not in sys.path:
    sys.path.insert(0, CARTELLA_ENGINE)

# Riusiamo la costante del motore gia' definita (e, come fa analisi_database,
# apriamo il motore con popen_uci). Importiamo anche turno_da_fen dal modulo
# fratello estrai_errori per non duplicare la logica del turno dal FEN.
from analisi_database import PERCORSO_STOCKFISH  # noqa: E402
from estrai_errori import turno_da_fen  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

PERCORSO_CANDIDATI = os.path.join(
    os.path.dirname(__file__), "..", "data", "candidati_errori.json"
)
# File del batch (tappa 2b): i puzzle tenuti e lo stato di avanzamento per la
# ripartenza sicura (sidecar accanto al file dei puzzle).
PERCORSO_PUZZLE = os.path.join(
    os.path.dirname(__file__), "..", "data", "puzzle_errori.json"
)
PERCORSO_PROGRESSO = os.path.join(
    os.path.dirname(__file__), "..", "data", "puzzle_errori.progress.json"
)

# Soglie di gap (centipawn) su cui misurare il tasso di sopravvivenza.
SOGLIE_GAP = [100, 150, 200]
# Soglia di gap (centipawn) di default per TENERE un puzzle nel batch (tappa 2b).
GAP_DEFAULT = 200
# Cadenza del salvataggio incrementale (ripartenza sicura): si salva su disco
# ogni SALVA_OGNI_PUZZLE puzzle tenuti oppure ogni SALVA_OGNI_CANDIDATI processati.
SALVA_OGNI_PUZZLE = 50
SALVA_OGNI_CANDIDATI = 100

# Oltre questo |valore| la valutazione e' un mate-score (vedi engine).
SOGLIA_MATTO = 100000
# Gap "infinito" attribuito ai matti forzati: unicita' garantita per definizione,
# passano qualsiasi soglia.
GAP_MATTO = 10 ** 9

# Default della tappa di taratura.
CAMPIONE_DEFAULT = 150
PROFONDITA_DEFAULT = 18
# Seed fisso: campione riproducibile e rappresentativo (non i primi N del file).
SEED = 42


# --- Funzioni pure (testabili senza Stockfish) ---------------------------

def eval_lato_mossa(eval_bianco, turno):
    """
    Converte una valutazione (centipawn, vista Bianco) nel punto di vista di
    chi deve muovere: se tocca al Nero si inverte il segno. Positivo = chi
    muove sta meglio.
    """
    return eval_bianco if turno == "w" else -eval_bianco


def estrai_linea(info):
    """
    Da una singola linea MultiPV (un dict come quelli restituiti da
    chess.engine.analyse) ricava la tripla:
      (eval_centipawn_vista_bianco, e_matto, prima_mossa_uci).
    I matti diventano +/-SOGLIA_MATTO come nel resto del progetto.
    """
    pov = info["score"].white()
    if pov.is_mate():
        eval_bianco = SOGLIA_MATTO if pov.mate() > 0 else -SOGLIA_MATTO
        matto = True
    else:
        eval_bianco = pov.score()
        matto = False
    pv = info.get("pv")
    mossa = pv[0].uci() if pv else None
    return eval_bianco, matto, mossa


def calcola_gap(eval1_lato, eval2_lato):
    """
    Gap (centipawn) tra la 1a e la 2a mossa, ENTRAMBE dal punto di vista di chi
    muove. La 1a e' la migliore, quindi il gap e' >= 0. Se la 1a mossa e' un
    matto forzato a favore di chi muove il puzzle e' valido per definizione:
    gap "infinito".
    """
    if eval1_lato >= SOGLIA_MATTO:
        return GAP_MATTO
    return max(0, eval1_lato - eval2_lato)


def valuta_multipv(info, turno, candidato):
    """
    Dato l'output MultiPV (lista di linee) e il turno dal FEN, calcola il
    risultato di validazione di un candidato. Funzione pura: non tocca il
    motore, cosi' e' testabile con linee finte.

    Restituisce un dizionario con la soluzione validata (1a mossa a questa
    profondita'), il gap, se e' un matto e il confronto con la vecchia
    soluzione salvata.
    """
    eval1_bianco, _, mossa1 = estrai_linea(info[0])
    eval1_lato = eval_lato_mossa(eval1_bianco, turno)

    if len(info) >= 2:
        eval2_bianco, _, _ = estrai_linea(info[1])
        eval2_lato = eval_lato_mossa(eval2_bianco, turno)
        gap = calcola_gap(eval1_lato, eval2_lato)
    else:
        # Una sola mossa disponibile/restituita: nessuna alternativa -> unica.
        eval2_lato = None
        gap = GAP_MATTO

    matto = eval1_lato >= SOGLIA_MATTO
    soluzione_vecchia = candidato.get("soluzione_uci")

    return {
        "fen": candidato["fen"],
        "soluzione_validata_uci": mossa1,
        "soluzione_uci_vecchia": soluzione_vecchia,
        "soluzione_cambiata": mossa1 != soluzione_vecchia,
        "eval1_lato": eval1_lato,
        "eval2_lato": eval2_lato,
        "gap": gap,
        "matto": matto,
        "cadenza": candidato.get("cadenza"),
    }


def filtra_non_bullet(candidati):
    """Tiene solo i candidati con cadenza diversa da 'bullet'."""
    return [c for c in candidati if c.get("cadenza") != "bullet"]


def seleziona_campione(candidati, n, seed=SEED):
    """
    Esclude i bullet, mescola i restanti con seed fisso (campione
    rappresentativo, NON i primi N in ordine di file) e ne restituisce i primi
    n. Restituisce la coppia (campione, totale_non_bullet).
    """
    non_bullet = filtra_non_bullet(candidati)
    mescolati = list(non_bullet)
    random.Random(seed).shuffle(mescolati)
    return mescolati[:n], len(non_bullet)


def seleziona_batch(candidati):
    """
    Modalita' batch (tappa 2b): TUTTI i candidati non-bullet, NON un campione.
    Restituisce la coppia (non_bullet, totale_non_bullet); l'ordine e' quello
    del file (nessun mescolamento, cosi' la ripartenza e' deterministica).
    """
    non_bullet = filtra_non_bullet(candidati)
    return non_bullet, len(non_bullet)


def tieni_puzzle(risultato, soglia):
    """
    Regola del batch per TENERE un puzzle: lo si tiene se e' un matto a favore di
    chi muove (unicita' garantita) oppure se il gap >= soglia. Altrimenti il
    puzzle e' ambiguo/"rotto" e va scartato.
    """
    return risultato["matto"] or risultato["gap"] >= soglia


def costruisci_puzzle(candidato, risultato, profondita):
    """
    Costruisce il dizionario del puzzle da salvare unendo il candidato grezzo e
    il risultato della validazione. La soluzione e' quella VALIDATA a questa
    profondita' (non la vecchia best_move_uci del candidato).
    """
    return {
        "fen": candidato["fen"],
        "soluzione_uci": risultato["soluzione_validata_uci"],
        "tua_mossa_uci": candidato.get("mossa_giocata_uci"),
        "san_giocata": candidato.get("san_giocata"),
        "gap_centipawn": risultato["gap"],
        "era_matto": risultato["matto"],
        "eval_mia_prima": candidato.get("eval_mia_prima"),
        "centipawn_loss": candidato.get("centipawn_loss"),
        "fonte_file": candidato.get("fonte_file"),
        "indice_mossa": candidato.get("indice_mossa"),
        "cadenza": candidato.get("cadenza"),
        "profondita_validazione": profondita,
    }


def chiave_candidato(candidato):
    """
    Chiave univoca di un candidato per la ripartenza sicura: la coppia
    (fonte_file, indice_mossa) identifica una mossa precisa di una partita.
    Restituita come stringa "fonte|indice" cosi' e' serializzabile in JSON.
    """
    return f"{candidato.get('fonte_file')}|{candidato.get('indice_mossa')}"


def filtra_da_processare(candidati, processati):
    """
    Tiene solo i candidati la cui chiave NON e' fra i gia'-processati (set/lista
    di chiavi). E' il cuore della ripartenza: ciò che era gia' stato validato in
    una corsa precedente viene saltato.
    """
    processati = set(processati)
    return [c for c in candidati if chiave_candidato(c) not in processati]


def tasso_sopravvivenza(gap_list, soglie=SOGLIE_GAP):
    """Per ogni soglia, quanti gap la superano (>=). Restituisce {soglia: n}."""
    return {s: sum(1 for g in gap_list if g >= s) for s in soglie}


def stima_tempo_totale(tempo_medio, totale_non_bullet):
    """Stima (secondi) per validare TUTTI i candidati non-bullet."""
    return tempo_medio * totale_non_bullet


def formatta_durata(secondi):
    """Formatta una durata in secondi come stringa leggibile (ore/minuti)."""
    secondi = int(round(secondi))
    ore, resto = divmod(secondi, 3600)
    minuti, sec = divmod(resto, 60)
    if ore:
        return f"{ore}h {minuti}m"
    if minuti:
        return f"{minuti}m {sec}s"
    return f"{sec}s"


# --- Validazione con Stockfish -------------------------------------------

def carica_candidati(percorso=PERCORSO_CANDIDATI):
    """Carica i candidati grezzi prodotti da estrai_errori.py."""
    with open(percorso, "r", encoding="utf-8") as f:
        return json.load(f)


def valida_candidato(candidato, motore, profondita):
    """
    Valida un singolo candidato con Stockfish in MultiPV=2: analizza la
    posizione del FEN alla profondita' richiesta, chiede le 2 migliori mosse e
    calcola il gap. Restituisce il dizionario di valuta_multipv arricchito col
    tempo impiegato (secondi).
    """
    board = chess.Board(candidato["fen"])
    turno = turno_da_fen(candidato["fen"])

    inizio = time.perf_counter()
    info = motore.analyse(board, chess.engine.Limit(depth=profondita), multipv=2)
    tempo = time.perf_counter() - inizio

    risultato = valuta_multipv(info, turno, candidato)
    risultato["tempo_secondi"] = tempo
    return risultato


def valida_campione(candidati, n, profondita, percorso_motore=PERCORSO_STOCKFISH):
    """
    Apre Stockfish e valida il campione di n candidati non-bullet (mescolati con
    seed fisso). Restituisce (risultati, totale_non_bullet, n_bullet_saltati)
    oppure None se il motore non e' disponibile.
    """
    if not os.path.exists(percorso_motore):
        logger.error("Stockfish non trovato in: %s", percorso_motore)
        return None

    campione, totale_non_bullet = seleziona_campione(candidati, n)
    n_bullet_saltati = len(candidati) - totale_non_bullet

    logger.info(
        "Campione: %d candidati (su %d non-bullet, %d bullet saltati), profondita %d",
        len(campione), totale_non_bullet, n_bullet_saltati, profondita,
    )

    motore = chess.engine.SimpleEngine.popen_uci(percorso_motore)
    risultati = []
    try:
        for indice, candidato in enumerate(campione, start=1):
            risultato = valida_candidato(candidato, motore, profondita)
            risultati.append(risultato)
            logger.info(
                "Validato %d/%d | gap=%s | matto=%s | %.2fs",
                indice, len(campione),
                "inf" if risultato["matto"] else risultato["gap"],
                risultato["matto"], risultato["tempo_secondi"],
            )
    finally:
        motore.quit()

    return risultati, totale_non_bullet, n_bullet_saltati


# --- Batch completo (tappa 2b): salvataggio e ripartenza sicura ----------

def _stato_iniziale():
    """Contatori cumulativi del batch (azzerati a una corsa da zero)."""
    return {"validati": 0, "tenuti": 0, "scartati": 0, "matti": 0, "cambiate": 0}


def componi_stato(processati, contatori, gap, profondita):
    """
    Compone l'oggetto di stato da serializzare nel file di progresso: i parametri
    della corsa, l'elenco (ordinato) delle chiavi gia' processate e i contatori
    cumulativi. Funzione pura, testabile senza disco.
    """
    stato = {"gap": gap, "profondita": profondita,
             "processati": sorted(processati)}
    stato.update(contatori)
    return stato


def salva_progresso(puzzle, stato, percorso_puzzle=PERCORSO_PUZZLE,
                    percorso_progresso=PERCORSO_PROGRESSO):
    """
    Salvataggio incrementale: scrive i puzzle tenuti e, accanto, lo stato di
    avanzamento. Cosi' un'interruzione non perde il lavoro fatto.
    """
    os.makedirs(os.path.dirname(percorso_puzzle), exist_ok=True)
    with open(percorso_puzzle, "w", encoding="utf-8") as f:
        json.dump(puzzle, f, indent=2, ensure_ascii=False)
    with open(percorso_progresso, "w", encoding="utf-8") as f:
        json.dump(stato, f, indent=2, ensure_ascii=False)


def carica_progresso(percorso_puzzle=PERCORSO_PUZZLE,
                     percorso_progresso=PERCORSO_PROGRESSO):
    """
    Ricarica una validazione batch in corso: restituisce (puzzle, stato) se ESI-
    STONO sia il file dei puzzle sia il sidecar di progresso, altrimenti None
    (nessuna corsa da riprendere -> si parte da zero).
    """
    if not (os.path.exists(percorso_puzzle) and os.path.exists(percorso_progresso)):
        return None
    with open(percorso_puzzle, "r", encoding="utf-8") as f:
        puzzle = json.load(f)
    with open(percorso_progresso, "r", encoding="utf-8") as f:
        stato = json.load(f)
    return puzzle, stato


def valida_batch(candidati, profondita, soglia=GAP_DEFAULT, ricomincia=False,
                 percorso_motore=PERCORSO_STOCKFISH,
                 percorso_puzzle=PERCORSO_PUZZLE,
                 percorso_progresso=PERCORSO_PROGRESSO):
    """
    Tappa 2b: valida con Stockfish TUTTI i candidati non-bullet e salva i puzzle
    tenuti (gap >= soglia o matto) in percorso_puzzle, scartando-contando gli
    altri. Salvataggio incrementale + ripartenza dalla corsa precedente (a meno
    di ricomincia=True). Restituisce un riepilogo (dict) o None se manca il motore.
    """
    if not os.path.exists(percorso_motore):
        logger.error("Stockfish non trovato in: %s", percorso_motore)
        return None

    non_bullet, totale_non_bullet = seleziona_batch(candidati)
    n_bullet_saltati = len(candidati) - totale_non_bullet

    # Ripartenza: riprendo puzzle, chiavi gia' processate e contatori, se ci sono.
    puzzle = []
    processati = set()
    contatori = _stato_iniziale()
    if not ricomincia:
        precedente = carica_progresso(percorso_puzzle, percorso_progresso)
        if precedente is not None:
            puzzle, stato = precedente
            processati = set(stato.get("processati", []))
            contatori = {k: stato.get(k, 0) for k in contatori}
            logger.info("Ripartenza: %d candidati gia' processati, %d puzzle tenuti",
                        len(processati), len(puzzle))

    da_processare = filtra_da_processare(non_bullet, processati)
    logger.info(
        "Batch: %d candidati non-bullet (%d bullet saltati), %d da processare, "
        "profondita %d, soglia gap %d",
        totale_non_bullet, n_bullet_saltati, len(da_processare), profondita, soglia,
    )

    motore = chess.engine.SimpleEngine.popen_uci(percorso_motore)
    inizio = time.perf_counter()
    da_ultimo_salvataggio = 0
    tenuti_da_ultimo_salvataggio = 0
    try:
        for candidato in da_processare:
            risultato = valida_candidato(candidato, motore, profondita)
            contatori["validati"] += 1
            if risultato["matto"]:
                contatori["matti"] += 1
            if risultato["soluzione_cambiata"]:
                contatori["cambiate"] += 1

            if tieni_puzzle(risultato, soglia):
                puzzle.append(costruisci_puzzle(candidato, risultato, profondita))
                contatori["tenuti"] += 1
                tenuti_da_ultimo_salvataggio += 1
            else:
                contatori["scartati"] += 1

            processati.add(chiave_candidato(candidato))
            da_ultimo_salvataggio += 1

            # Salvataggio incrementale + avanzamento periodico.
            if (tenuti_da_ultimo_salvataggio >= SALVA_OGNI_PUZZLE
                    or da_ultimo_salvataggio >= SALVA_OGNI_CANDIDATI):
                stato = componi_stato(processati, contatori, soglia, profondita)
                salva_progresso(puzzle, stato, percorso_puzzle, percorso_progresso)
                da_ultimo_salvataggio = 0
                tenuti_da_ultimo_salvataggio = 0
                logger.info(
                    "validati %d / %d candidati, tenuti %d puzzle finora, trascorso %s",
                    contatori["validati"], totale_non_bullet, contatori["tenuti"],
                    formatta_durata(time.perf_counter() - inizio),
                )
    finally:
        motore.quit()

    # Salvataggio finale (anche se l'ultimo blocco non ha raggiunto la soglia).
    stato = componi_stato(processati, contatori, soglia, profondita)
    salva_progresso(puzzle, stato, percorso_puzzle, percorso_progresso)

    riepilogo = dict(contatori)
    riepilogo.update({
        "totale_non_bullet": totale_non_bullet,
        "n_bullet_saltati": n_bullet_saltati,
        "tempo_corsa": time.perf_counter() - inizio,
        "n_puzzle_file": len(puzzle),
        "percorso_puzzle": percorso_puzzle,
    })
    return riepilogo


def _stampa_riepilogo_batch(riepilogo, profondita, soglia):
    """Stampa il riepilogo finale del batch completo (tappa 2b)."""
    print()
    print("=== BATCH validazione errori (profondita %d, soglia gap %d) ==="
          % (profondita, soglia))
    print()
    print(f"  Candidati bullet saltati          : {riepilogo['n_bullet_saltati']}")
    print(f"  Totale candidati non-bullet       : {riepilogo['totale_non_bullet']}")
    print(f"  Candidati validati                : {riepilogo['validati']}")
    print(f"  Puzzle TENUTI (gap>=soglia o matto): {riepilogo['tenuti']}")
    print(f"  Candidati scartati (gap<soglia)   : {riepilogo['scartati']}")
    print(f"  Matti forzati                     : {riepilogo['matti']}")
    print(f"  Soluzione diversa dalla vecchia   : {riepilogo['cambiate']}")
    print(f"  Tempo di questa corsa             : "
          f"{formatta_durata(riepilogo['tempo_corsa'])} ({riepilogo['tempo_corsa']:.1f}s)")
    print()
    print(f"  Salvati {riepilogo['n_puzzle_file']} puzzle in {riepilogo['percorso_puzzle']}")
    print()


def _stampa_tabella(risultati, totale_non_bullet, n_bullet_saltati, profondita):
    """Stampa la tabella di taratura con cui l'utente sceglie i parametri."""
    n = len(risultati)
    gap_list = [r["gap"] for r in risultati]
    n_matti = sum(1 for r in risultati if r["matto"])
    n_cambiate = sum(1 for r in risultati if r["soluzione_cambiata"])
    sopravvivenza = tasso_sopravvivenza(gap_list)

    tempi = [r["tempo_secondi"] for r in risultati]
    tempo_totale = sum(tempi)
    tempo_medio = (tempo_totale / n) if n else 0.0
    stima = stima_tempo_totale(tempo_medio, totale_non_bullet)

    print()
    print("=== TARATURA validazione errori (profondita %d) ===" % profondita)
    print()
    print(f"  Candidati nel campione validati : {n}")
    print(f"  Candidati bullet saltati        : {n_bullet_saltati}")
    print(f"  Totale candidati non-bullet     : {totale_non_bullet}")
    print(f"  Matti forzati (passano sempre)  : {n_matti}")
    print(f"  Soluzione diversa dalla vecchia : {n_cambiate}")
    print()
    print("  Tasso di sopravvivenza per soglia di gap (centipawn):")
    print(f"    {'Soglia':<10} {'Passano':>8} {'%':>8}")
    print(f"    {'-' * 10} {'-' * 8:>8} {'-' * 8:>8}")
    for s in SOGLIE_GAP:
        passano = sopravvivenza[s]
        perc = (100.0 * passano / n) if n else 0.0
        print(f"    {'>=' + str(s):<10} {passano:>8} {perc:>7.1f}%")
    print()
    print(f"  Tempo medio per candidato : {tempo_medio:.2f}s")
    print(f"  Tempo totale del campione : {formatta_durata(tempo_totale)} "
          f"({tempo_totale:.1f}s)")
    print(f"  STIMA batch completo      : {formatta_durata(stima)} "
          f"(~{totale_non_bullet} candidati non-bullet)")
    print()


def _argomenti(argv=None):
    parser = argparse.ArgumentParser(
        description="Validazione errori (usa Stockfish, MultiPV): taratura su "
                    "campione (default) oppure batch completo con --batch."
    )
    parser.add_argument("--campione", type=int, default=CAMPIONE_DEFAULT,
                        help="taratura: quanti candidati non-bullet validare "
                             "(default %d, ignorato con --batch)" % CAMPIONE_DEFAULT)
    parser.add_argument("--profondita", type=int, default=PROFONDITA_DEFAULT,
                        help="profondita' Stockfish (default %d)"
                             % PROFONDITA_DEFAULT)
    parser.add_argument("--batch", action="store_true",
                        help="tappa 2b: valida TUTTI i non-bullet e salva i "
                             "puzzle in data/puzzle_errori.json")
    parser.add_argument("--gap", type=int, default=GAP_DEFAULT,
                        help="batch: soglia di gap (centipawn) per tenere un "
                             "puzzle (default %d)" % GAP_DEFAULT)
    parser.add_argument("--ricomincia", action="store_true",
                        help="batch: ignora il progresso salvato e rifa' tutto "
                             "da zero")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _argomenti()

    logger.info("Carico i candidati da: %s", PERCORSO_CANDIDATI)
    candidati = carica_candidati()
    logger.info("Caricati %d candidati grezzi", len(candidati))

    if args.batch:
        riepilogo = valida_batch(candidati, args.profondita, args.gap,
                                 ricomincia=args.ricomincia)
        if riepilogo is None:
            print("\nValidazione non riuscita (Stockfish presente in engine/bin/?).\n")
            sys.exit(1)
        _stampa_riepilogo_batch(riepilogo, args.profondita, args.gap)
        sys.exit(0)

    esito = valida_campione(candidati, args.campione, args.profondita)
    if esito is None:
        print("\nValidazione non riuscita (Stockfish presente in engine/bin/?).\n")
        sys.exit(1)

    risultati, totale_non_bullet, n_bullet_saltati = esito
    _stampa_tabella(risultati, totale_non_bullet, n_bullet_saltati, args.profondita)
    print("Tappa di TARATURA: nessun puzzle salvato. Scegli le soglie e poi "
          "lancia la tappa 2b per il batch completo.")
    print()
