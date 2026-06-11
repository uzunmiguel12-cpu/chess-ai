"""
Modulo di SOLA MISURAZIONE - sola lettura, NON usa Stockfish, NON salva file.

Serve a misurare quanto spesso NON converto un vantaggio, a varie soglie, per
decidere i parametri guardando i numeri veri (non a intuito).

Legge le analisi in data/analisi/*.json (le stesse usate da estrai_errori.py).
Per ogni partita che gioco IO (username "MigueL_uz", case-insensitive):
  - normalizza ogni eval dal MIO punto di vista (se sono Nero inverto il segno);
  - determina il RISULTATO dal mio punto di vista incrociando "risultato" col
    mio colore -> "vittoria" / "patta" / "sconfitta";
  - calcola il PICCO di vantaggio mio (massimo eval_mia raggiunto in partita).

CONTEGGIO a piu' soglie [150, 200, 300] centipawn: partite che hanno raggiunto
quel vantaggio e, tra queste, quante NON ho convertito (patta o sconfitta).

Per la soglia 200, tra le non-conversioni distingue:
  - "crollo": una singola mia mossa con centipawn_loss >= 300 fa scendere il
    vantaggio sotto soglia di colpo (gia' catturato dal profilo errori);
  - "erosione": il vantaggio cala sotto soglia in modo graduale, senza una
    singola mia mossa >= 300 (questo e' il "non converto" che il profilo
    errori NON cattura -> il caso interessante).

ESCLUSIONE BULLET: i file il cui nome inizia per "bullet" sono esclusi di default
(escludi_bullet=True). In bullet una non-conversione e' spesso il tempo che scade,
non tecnica di conversione mancata: inquinerebbe la diagnosi (stessa ragione per cui
il bullet e' escluso dai puzzle-errore). Si puo' misurare tutto con escludi_bullet=False.

TETTO AL PICCO (solo nella diagnosi_conversione): anche escludendo il bullet, molte
"erosioni" partono da vantaggi stratosferici (>+6, fino a +13): da li' non e' "tecnica
di conversione mancata", e' matto facile o anomalia. La vera non-conversione tecnica
avviene da vantaggi DECISIVI MA NON BANALI, nell'intervallo
[PICCO_MIN_CONVERSIONE, PICCO_MAX_CONVERSIONE] (+2.0 / +6.0). Il tetto si applica DOPO
l'esclusione bullet; le erosioni sopra il tetto sono riportate a parte, per trasparenza.

SCELTA sui mate-score: gli eval fasulli |eval| >= 100000 (matto annunciato)
vengono "tagliati" (cap) a +/- 1000 centipawn prima di ogni calcolo, cosi'
contano come "vantaggio enorme ma finito" senza falsare i picchi.

GUARDRAIL ONESTA': la tabella mostra SEMPRE i numeri assoluti accanto alle
percentuali, cosi' si capisce se un tasso e' significativo o solo rumore
(es. 3 partite su 3000 non sono un pattern).

Uso:  python ml/converti_vantaggio.py
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

# Soglie di vantaggio (centipawn, dal MIO punto di vista) su cui misurare.
SOGLIE = [150, 200, 300]
# Soglia su cui fare la ripartizione crollo vs erosione.
SOGLIA_DETTAGLIO = 200
# Centipawn loss che qualifica una mia mossa come "crollo" (vantaggio buttato).
CPL_CROLLO = 300

# TETTO AL PICCO per la diagnosi "non converti il vantaggio".
# Intervallo (centipawn, +2.0 / +6.0) dove convertire e' una VERA abilita' tecnica:
#   - sotto +2 (PICCO_MIN) non e' ancora "vantaggio chiaro";
#   - sopra +6 (PICCO_MAX) e' gia' vinto in modo banale / matto imminente: da li' una
#     non-conversione non e' "tecnica mancata" ma matto facile o anomalia.
# La vera non-conversione tecnica avviene da vantaggi DECISIVI MA NON BANALI.
PICCO_MIN_CONVERSIONE = 200
PICCO_MAX_CONVERSIONE = 600

# Mate-score fasullo: |eval| >= di questo e' un matto annunciato.
SOGLIA_MATTO = 100000
# Cap applicato ai mate-score: oltre questo il vantaggio e' comunque "enorme".
CAP_MATTO = 1000

# Soglia di significativita' del campione di EROSIONI: sotto questo numero di
# partite il pattern e' indicativo, non affidabile. E' un'EURISTICA DICHIARATA
# (non una soglia statistica formale): serve solo a non gridare al pattern su
# 3 partite. 20 e' un campione abbastanza grande da non essere puro rumore.
SOGLIA_AFFIDABILITA = 20

# Riuso eval_dal_mio_punto_di_vista da estrai_errori.py se importabile;
# altrimenti la replico identica qui sotto (fallback).
try:
    from estrai_errori import eval_dal_mio_punto_di_vista
except Exception:  # pragma: no cover - solo fallback se import non disponibile
    def eval_dal_mio_punto_di_vista(eval_prima, sono_bianco):
        """Normalizza eval (vista Bianco) dal mio punto di vista: se Nero inverto."""
        return eval_prima if sono_bianco else -eval_prima


def _normalizza(nome):
    """Normalizza un nome per il confronto case-insensitive."""
    return nome.strip().lower()


def e_bullet(nome_file):
    """
    Deduce dal nome del file se la partita e' bullet (come fa estrai_errori.py per
    il campo cadenza): True se il basename inizia per "bullet".

    Il bullet va escluso dalla diagnosi di conversione: una non-conversione in bullet
    e' spesso il tempo che scade, non tecnica di conversione mancata (stessa ragione
    per cui il bullet e' escluso dai puzzle-errore).
    """
    return os.path.basename(nome_file).lower().startswith("bullet")


def mio_colore(dato_partita, nome=USERNAME):
    """
    Determina il mio colore confrontando i nomi (case-insensitive).
    Restituisce "w" col Bianco, "b" col Nero, None se non gioco io.
    """
    nome_norm = _normalizza(nome)
    if _normalizza(dato_partita.get("bianco", "")) == nome_norm:
        return "w"
    if _normalizza(dato_partita.get("nero", "")) == nome_norm:
        return "b"
    return None


def turno_da_fen(fen):
    """Estrae il turno dal FEN (secondo token): "w" Bianco, "b" Nero."""
    parti = fen.split()
    return parti[1] if len(parti) >= 2 else None


def cap_mate(eval_centipawn):
    """
    Taglia i mate-score fasulli: se |eval| >= SOGLIA_MATTO lo riporto a
    +/- CAP_MATTO mantenendo il segno. Gli eval normali restano invariati.
    """
    if eval_centipawn >= SOGLIA_MATTO:
        return CAP_MATTO
    if eval_centipawn <= -SOGLIA_MATTO:
        return -CAP_MATTO
    return eval_centipawn


def risultato_dal_mio_punto_di_vista(risultato, sono_bianco):
    """
    Traduce il campo "risultato" (1-0 / 0-1 / 1/2-1/2) dal MIO punto di vista.
    Restituisce "vittoria" / "patta" / "sconfitta", oppure None se illeggibile.
    """
    r = (risultato or "").strip()
    if r in ("1/2-1/2", "1/2", "0.5-0.5"):
        return "patta"
    if r == "1-0":
        return "vittoria" if sono_bianco else "sconfitta"
    if r == "0-1":
        return "sconfitta" if sono_bianco else "vittoria"
    return None


def costruisci_timeline(dato_partita, colore):
    """
    Costruisce la "timeline" della partita dal MIO punto di vista: una lista di
    mosse in ordine, ciascuna con
      - eval_prima_mia / eval_dopo_mia : eval (con cap mate) dal mio lato;
      - centipawn_loss                 : perdita di chi muove (sempre >= 0);
      - mia                            : True se la mossa e' mia.
    """
    sono_bianco = (colore == "w")
    timeline = []
    for mossa in dato_partita.get("mosse", []):
        eval_prima = cap_mate(mossa["eval_prima"])
        eval_dopo = cap_mate(mossa["eval_dopo"])
        timeline.append({
            "eval_prima_mia": eval_dal_mio_punto_di_vista(eval_prima, sono_bianco),
            "eval_dopo_mia": eval_dal_mio_punto_di_vista(eval_dopo, sono_bianco),
            "centipawn_loss": mossa["centipawn_loss"],
            "mia": turno_da_fen(mossa["fen"]) == colore,
        })
    return timeline


def picco_vantaggio(timeline):
    """
    Massimo vantaggio mio (eval_mia) raggiunto nella partita, considerando ogni
    punto della timeline (prima e dopo ogni mossa). Restituisce None se vuota.
    """
    if not timeline:
        return None
    valori = []
    for m in timeline:
        valori.append(m["eval_prima_mia"])
        valori.append(m["eval_dopo_mia"])
    return max(valori)


def indice_picco(timeline, picco):
    """
    Numero di mossa (1-based, conteggio in ply) in cui il vantaggio raggiunge per
    la prima volta il picco. Utile per dire "eri al massimo intorno alla mossa N".
    Restituisce None se la timeline e' vuota.
    """
    for i, m in enumerate(timeline):
        if max(m["eval_prima_mia"], m["eval_dopo_mia"]) == picco:
            return i + 1
    return None


def eval_finale(timeline):
    """Ultima eval mia della partita (dopo l'ultima mossa). None se timeline vuota."""
    return timeline[-1]["eval_dopo_mia"] if timeline else None


def classifica_perdita(timeline, soglia=SOGLIA_DETTAGLIO, cpl_crollo=CPL_CROLLO):
    """
    Classifica COME ho perso il vantaggio (per una partita non convertita che
    ha raggiunto la soglia):
      - "crollo"   : esiste una mia mossa con centipawn_loss >= cpl_crollo che
                     da sola porta l'eval da >= soglia a < soglia;
      - "erosione" : nessuna singola mia mossa fa quel salto -> il vantaggio si
                     e' sciolto gradualmente.
    """
    for m in timeline:
        if (m["mia"]
                and m["centipawn_loss"] >= cpl_crollo
                and m["eval_prima_mia"] >= soglia
                and m["eval_dopo_mia"] < soglia):
            return "crollo"
    return "erosione"


def _nuovo_riepilogo(soglie=SOGLIE):
    """Struttura vuota dei conteggi (un blocco per soglia + ripartizione 200)."""
    return {
        "n_partite_analizzate": 0,   # partite dove gioco io e leggo il risultato
        "n_file_saltati": 0,         # non gioco io, o file illeggibile/incompleto
        "partite_bullet_escluse": 0,  # file bullet saltati prima di ogni conteggio
        "soglie": {s: {"con_vantaggio": 0, "non_convertite": 0} for s in soglie},
        "ripartizione_dettaglio": {"crollo": 0, "erosione": 0},
        # Erosioni escluse dal conteggio per via del TETTO AL PICCO: partono da un
        # vantaggio stratosferico (picco > picco_max) -> matto facile / anomalia,
        # non tecnica di conversione mancata. Le traccio per trasparenza.
        "erosioni_sopra_tetto_escluse": 0,
        # Le partite di EROSIONE alla soglia di dettaglio, per poterle rivedere:
        # e' la parte di valore (il pattern che il profilo errori NON cattura).
        "partite_erosione": [],
    }


def analizza_partite(cartella=CARTELLA_ANALISI, soglie=SOGLIE,
                     soglia_dettaglio=SOGLIA_DETTAGLIO, escludi_bullet=True,
                     picco_max=None):
    """
    Scorre tutte le analisi e produce il riepilogo dei conteggi.

    Per ogni partita mia: calcola il picco di vantaggio e il risultato dal mio
    lato; per ogni soglia incrementa "con_vantaggio" se il picco la raggiunge e
    "non_convertite" se in piu' non ho vinto. Alla soglia di dettaglio classifica
    le non-conversioni in crollo vs erosione.

    Con `escludi_bullet=True` (default) i file bullet vengono SALTATI prima di
    qualsiasi conteggio: in bullet una non-conversione e' spesso il tempo che scade,
    non tecnica mancata, e inquinerebbe la diagnosi. Il numero di file bullet saltati
    finisce in rie["partite_bullet_escluse"]. Con `escludi_bullet=False` si misura
    tutto (utile se serve il quadro completo).

    Con `picco_max` valorizzato (es. PICCO_MAX_CONVERSIONE) si applica il TETTO AL
    PICCO, DOPO l'esclusione bullet: le partite con picco di vantaggio > picco_max
    sono escluse dai conteggi (con_vantaggio, non_convertite, ripartizione), perche'
    un vantaggio stratosferico e' matto facile, non tecnica di conversione. Le
    EROSIONI cosi' escluse vengono contate in rie["erosioni_sopra_tetto_escluse"]
    (trasparenza). Con `picco_max=None` (default) non si applica alcun tetto.
    """
    rie = _nuovo_riepilogo(soglie)

    file_analisi = sorted(glob.glob(os.path.join(cartella, "*.json")))
    if not file_analisi:
        logger.warning("Nessun file di analisi trovato in: %s", cartella)
        return rie

    for percorso in file_analisi:
        # Esclusione bullet PRIMA di leggere/contare: la cadenza si deduce dal nome.
        if escludi_bullet and e_bullet(percorso):
            rie["partite_bullet_escluse"] += 1
            continue

        try:
            with open(percorso, "r", encoding="utf-8") as f:
                dato = json.load(f)
        except (OSError, json.JSONDecodeError):
            rie["n_file_saltati"] += 1
            continue

        colore = mio_colore(dato)
        if colore is None:
            # Non gioco questa partita: la salto del tutto.
            rie["n_file_saltati"] += 1
            continue

        sono_bianco = (colore == "w")
        esito = risultato_dal_mio_punto_di_vista(dato.get("risultato"), sono_bianco)
        timeline = costruisci_timeline(dato, colore)
        picco = picco_vantaggio(timeline)
        if esito is None or picco is None:
            # Risultato illeggibile o partita senza mosse: non misurabile.
            rie["n_file_saltati"] += 1
            continue

        rie["n_partite_analizzate"] += 1
        non_convertita = esito in ("patta", "sconfitta")

        # TETTO AL PICCO (se richiesto): un picco stratosferico (> picco_max) e'
        # matto facile / anomalia, non conversione tecnica -> fuori dai conteggi.
        sopra_tetto = (picco_max is not None and picco > picco_max)

        for s in soglie:
            if picco >= s and not sopra_tetto:
                rie["soglie"][s]["con_vantaggio"] += 1
                if non_convertita:
                    rie["soglie"][s]["non_convertite"] += 1

        # Ripartizione crollo vs erosione solo sulle non-conversioni alla
        # soglia di dettaglio.
        if non_convertita and picco >= soglia_dettaglio:
            tipo = classifica_perdita(timeline, soglia_dettaglio)
            # Sopra il tetto: non conto la non-conversione, ma traccio le erosioni
            # cosi' escluse (cosi' e' trasparente quante ne abbiamo tolte e perche').
            if sopra_tetto:
                if tipo == "erosione":
                    rie["erosioni_sopra_tetto_escluse"] += 1
                continue
            rie["ripartizione_dettaglio"][tipo] += 1
            # Solo le EROSIONI: tengo i dati per poterle rivedere su Chess.com.
            if tipo == "erosione":
                rie["partite_erosione"].append({
                    "fonte_file": os.path.basename(percorso),
                    "picco_vantaggio": picco,
                    "risultato": esito,
                    "mossa_del_picco": indice_picco(timeline, picco),
                    "eval_fine": eval_finale(timeline),
                    "n_mosse": len(timeline),
                })

    # Erosioni ordinate per picco decrescente: prima le occasioni piu' grosse.
    rie["partite_erosione"].sort(key=lambda p: p["picco_vantaggio"], reverse=True)
    return rie


def _pct(parte, totale):
    """Percentuale robusta: 0.0 se il totale e' zero (evita divisioni per zero)."""
    return (100.0 * parte / totale) if totale else 0.0


def _stampa_tabella(rie, soglie=SOGLIE, soglia_dettaglio=SOGLIA_DETTAGLIO):
    """Stampa a schermo la tabella di misurazione (numeri assoluti + percentuali)."""
    n = rie["n_partite_analizzate"]
    print()
    print("=== Conversione del vantaggio (SOLA MISURAZIONE) ===")
    print()
    print(f"  Partite mie analizzate: {n}")
    print(f"  Partite bullet escluse: {rie['partite_bullet_escluse']} "
          f"(in bullet si perde a tempo, non per tecnica)")
    print(f"  File saltati (non gioco io / illeggibili): {rie['n_file_saltati']}")
    print()
    print(f"  {'Soglia':<9} {'Con vantaggio':>14} {'Non convertite':>16} {'Tasso':>9}")
    print(f"  {'-'*9} {'-'*14:>14} {'-'*16:>16} {'-'*9:>9}")
    for s in soglie:
        con = rie["soglie"][s]["con_vantaggio"]
        nc = rie["soglie"][s]["non_convertite"]
        print(f"  {'>=' + str(s):<9} {con:>14} {nc:>16} {_pct(nc, con):>8.1f}%")
    print()

    # Ripartizione crollo vs erosione alla soglia di dettaglio.
    crollo = rie["ripartizione_dettaglio"]["crollo"]
    erosione = rie["ripartizione_dettaglio"]["erosione"]
    tot_nc = crollo + erosione
    print(f"  Non-conversioni a soglia {soglia_dettaglio}: ripartizione")
    print(f"    crollo   (1 mossa mia con cpl >= {CPL_CROLLO}): "
          f"{crollo:>5}  ({_pct(crollo, tot_nc):.1f}%)")
    print(f"    erosione (calo graduale, gia' NON catturato): "
          f"{erosione:>5}  ({_pct(erosione, tot_nc):.1f}%)")
    print()
    print("  Nota onesta': i numeri assoluti contano piu' delle percentuali.")
    print("  Un tasso alto su poche partite e' rumore, non un pattern.")
    print()


def diagnosi_conversione(soglia=SOGLIA_DETTAGLIO, cartella=CARTELLA_ANALISI,
                         escludi_bullet=True):
    """
    DIAGNOSI consultabile "non converti il vantaggio" (prima diagnosi del punto 5
    della visione): invece di stampare, RESTITUISCE un dizionario coi numeri gia'
    calcolati dallo script, pensato per essere servito via API.

    Approccio: SOLO consapevolezza (mostra il pattern), niente puzzle/allenamento:
    l'erosione non ha una mossa-soluzione validabile.

    Con `escludi_bullet=True` (default) le partite bullet sono escluse: in bullet la
    non-conversione e' spesso il tempo che scade, non tecnica mancata.

    TETTO AL PICCO: la diagnosi considera SOLO i vantaggi nell'intervallo tecnico
    [PICCO_MIN_CONVERSIONE, PICCO_MAX_CONVERSIONE] (+2.0 / +6.0). Il limite inferiore
    e' la soglia stessa; il limite superiore e' picco_max=PICCO_MAX_CONVERSIONE,
    applicato DOPO l'esclusione bullet. Le erosioni con picco sopra il tetto sono
    riportate in "erosioni_sopra_tetto_escluse".

    Restituisce:
      {
        soglia,                       # centipawn (default 200 = vantaggio +2)
        picco_min, picco_max,         # intervallo tecnico considerato (centipawn)
        partite_con_vantaggio,        # partite con picco in [picco_min, picco_max]
        non_convertite, tasso_non_conversione,
        crollo:   {n, perc},          # % sulle non-conversioni nell'intervallo
        erosione: {n, perc},
        erosioni_sopra_tetto_escluse, # erosioni con picco > picco_max, escluse
        partite_erosione: [...],      # le erosioni da rivedere, picco decrescente
        affidabile,                   # n erosioni >= SOGLIA_AFFIDABILITA
        partite_bullet_escluse,       # quanti file bullet sono stati saltati
        escludi_bullet,               # il flag effettivamente usato
      }
    """
    # Misuro su quella SOLA soglia, usata anche come soglia di dettaglio (cosi'
    # crollo+erosione coincide con le non-conversioni a quella soglia). Applico il
    # TETTO AL PICCO: solo i vantaggi fino a PICCO_MAX_CONVERSIONE (+6.0) contano.
    rie = analizza_partite(cartella, soglie=[soglia], soglia_dettaglio=soglia,
                           escludi_bullet=escludi_bullet,
                           picco_max=PICCO_MAX_CONVERSIONE)

    con_vantaggio = rie["soglie"][soglia]["con_vantaggio"]
    non_convertite = rie["soglie"][soglia]["non_convertite"]
    crollo_n = rie["ripartizione_dettaglio"]["crollo"]
    erosione_n = rie["ripartizione_dettaglio"]["erosione"]
    tot_nc = crollo_n + erosione_n  # == non_convertite a questa soglia

    return {
        "soglia": soglia,
        # Intervallo tecnico dichiarato: il minimo e' la soglia, il massimo il tetto.
        "picco_min": PICCO_MIN_CONVERSIONE,
        "picco_max": PICCO_MAX_CONVERSIONE,
        "partite_con_vantaggio": con_vantaggio,
        "non_convertite": non_convertite,
        "tasso_non_conversione": round(_pct(non_convertite, con_vantaggio), 1),
        "crollo": {"n": crollo_n, "perc": round(_pct(crollo_n, tot_nc), 1)},
        "erosione": {"n": erosione_n, "perc": round(_pct(erosione_n, tot_nc), 1)},
        # Trasparenza: quante erosioni sono state tolte perche' sopra il tetto.
        "erosioni_sopra_tetto_escluse": rie["erosioni_sopra_tetto_escluse"],
        "partite_erosione": rie["partite_erosione"],
        # Il campione di EROSIONI e' affidabile solo se abbastanza numeroso.
        "affidabile": erosione_n >= SOGLIA_AFFIDABILITA,
        # Informativi: quante partite bullet sono state escluse e con quale flag.
        "partite_bullet_escluse": rie["partite_bullet_escluse"],
        "escludi_bullet": escludi_bullet,
    }


def _stampa_diagnosi_tetto(diag):
    """
    Stampa la diagnosi "non converti il vantaggio" col TETTO AL PICCO: conta solo i
    vantaggi nell'intervallo tecnico [picco_min, picco_max] (+2.0 / +6.0) e mostra
    quante EROSIONI stratosferiche (picco > picco_max) sono state escluse, e perche'.
    """
    pmin = diag["picco_min"]
    pmax = diag["picco_max"]
    print(f"  === Diagnosi conversione (TETTO AL PICCO: +{pmin/100:.0f} / +{pmax/100:.0f}) ===")
    print(f"    Picco di vantaggio considerato: [{pmin}, {pmax}] centipawn")
    print(f"    Partite con vantaggio nell'intervallo: {diag['partite_con_vantaggio']}")
    print(f"    Non convertite: {diag['non_convertite']} "
          f"({diag['tasso_non_conversione']}%)  di cui erosioni: {diag['erosione']['n']}")
    print(f"    Erosioni ESCLUSE per tetto (picco > {pmax}): "
          f"{diag['erosioni_sopra_tetto_escluse']}")
    print("    (sopra il tetto e' matto facile / anomalia, non tecnica mancata)")
    print()


if __name__ == "__main__":
    logger.info("Leggo i file di analisi da: %s", CARTELLA_ANALISI)
    riepilogo = analizza_partite()

    if riepilogo["n_partite_analizzate"] == 0:
        print("\nNessuna partita mia misurabile "
              "(controlla username e cartella analisi).\n")
        sys.exit(0)

    _stampa_tabella(riepilogo)
    # Diagnosi raffinata col tetto al picco: mostra anche le erosioni escluse perche'
    # partono da vantaggi stratosferici (matto facile), non tecnica di conversione.
    _stampa_diagnosi_tetto(diagnosi_conversione())
