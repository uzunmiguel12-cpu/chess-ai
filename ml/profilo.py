"""
Modulo profilo giocatore (Fase 3) - profilo di debolezze.

Dato un nome di giocatore, scorre le partite arricchite in data/categorie/,
raccoglie le mosse di quel giocatore e costruisce un profilo con:
- conteggi per gravita (scala stile Chess.com: best..blunder)
- conteggi per fase degli errori gravi (mistake + blunder)
- MOSSE TOTALI per fase (serve per il tasso)
- TASSO di errore per fase (% di mosse che sono errori gravi, in quella fase)
- debolezza principale = la fase col TASSO di errore piu' alto

Il tasso e' piu' onesto del semplice conteggio: corregge il fatto che quasi
tutte le partite passano per l'apertura (tante mosse) mentre poche arrivano al
finale (poche mosse). Confronta la frequenza, non il totale assoluto.

Uso:  python profilo.py "Nome Giocatore"
"""

import os
import sys
import json
import glob
import logging
from collections import Counter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ml")

CARTELLA_CATEGORIE = os.path.join(
    os.path.dirname(__file__), "..", "data", "categorie"
)

GRAVITA_ORDINE = ["best", "excellent", "good", "inaccuracy", "mistake", "blunder"]
GRAVITA_ERRORE = {"mistake", "blunder"}
FASI = ("apertura", "mediogioco", "finale")


def _normalizza(nome):
    return nome.strip().lower()


def _mosse_del_giocatore(dato_partita, nome_norm):
    bianco = _normalizza(dato_partita.get("bianco", ""))
    nero = _normalizza(dato_partita.get("nero", ""))
    if nome_norm == bianco:
        colore_pari = True
    elif nome_norm == nero:
        colore_pari = False
    else:
        return []
    mosse = []
    for i, mossa in enumerate(dato_partita["mosse"]):
        e_del_giocatore = (i % 2 == 0) if colore_pari else (i % 2 == 1)
        if e_del_giocatore:
            mosse.append(mossa)
    return mosse


def costruisci_profilo(nome, cartella=CARTELLA_CATEGORIE):
    """Costruisce il profilo del giocatore. None se non compare in nessuna partita."""
    nome_norm = _normalizza(nome)
    if not os.path.isdir(cartella):
        logger.error("Cartella categorie non trovata: %s", cartella)
        return None

    file_partite = sorted(glob.glob(os.path.join(cartella, "*.json")))
    logger.info("Cerco le partite di '%s' in %d file", nome, len(file_partite))

    tutte_mosse = []
    partite_trovate = 0
    for percorso in file_partite:
        with open(percorso, "r", encoding="utf-8") as f:
            dato = json.load(f)
        mosse_giocatore = _mosse_del_giocatore(dato, nome_norm)
        if mosse_giocatore:
            partite_trovate += 1
            tutte_mosse.extend(mosse_giocatore)

    if partite_trovate == 0:
        logger.warning("Nessuna partita trovata per '%s'", nome)
        return None

    conteggio_gravita = Counter(m["gravita"] for m in tutte_mosse)

    # Mosse totali per fase (denominatore del tasso) e errori gravi per fase.
    mosse_per_fase = Counter(m["fase"] for m in tutte_mosse)
    errori_veri = [m for m in tutte_mosse if m["gravita"] in GRAVITA_ERRORE]
    errori_per_fase = Counter(m["fase"] for m in errori_veri)

    # Tasso di errore per fase: errori / mosse in quella fase, in percentuale.
    tasso_per_fase = {}
    for fase in FASI:
        mosse_fase = mosse_per_fase.get(fase, 0)
        errori_fase = errori_per_fase.get(fase, 0)
        tasso_per_fase[fase] = round(100 * errori_fase / mosse_fase, 1) if mosse_fase else 0.0

    # Debolezza principale = fase col TASSO piu' alto (solo tra fasi con mosse).
    fasi_valide = {f: t for f, t in tasso_per_fase.items() if mosse_per_fase.get(f, 0) > 0}
    debolezza = max(fasi_valide, key=fasi_valide.get) if fasi_valide else None

    profilo = {
        "giocatore": nome,
        "partite_analizzate": partite_trovate,
        "mosse_totali": len(tutte_mosse),
        "errori_gravi_totali": len(errori_veri),
        "conteggio_gravita": dict(conteggio_gravita),
        "mosse_per_fase": dict(mosse_per_fase),
        "errori_per_fase": dict(errori_per_fase),
        "tasso_errore_per_fase": tasso_per_fase,
        "debolezza_principale": debolezza,
    }
    logger.info("Profilo costruito: %d partite, %d errori gravi",
                partite_trovate, len(errori_veri))
    return profilo


def stampa_profilo(profilo):
    print()
    print(f"=== Profilo di {profilo['giocatore']} ===")
    print(f"Partite analizzate: {profilo['partite_analizzate']}")
    print(f"Mosse totali: {profilo['mosse_totali']}")
    print()
    print("Qualita' delle mosse (stile Chess.com):")
    for g in GRAVITA_ORDINE:
        print(f"  {g:11}: {profilo['conteggio_gravita'].get(g, 0)}")
    print()
    print(f"Errori gravi totali (mistake + blunder): {profilo['errori_gravi_totali']}")
    print()
    print("Per fase (errori / mosse = tasso):")
    for fase in FASI:
        err = profilo["errori_per_fase"].get(fase, 0)
        tot = profilo["mosse_per_fase"].get(fase, 0)
        tasso = profilo["tasso_errore_per_fase"].get(fase, 0.0)
        print(f"  {fase:11}: {err:4} / {tot:4} mosse  =  {tasso}% di errori")
    print()
    if profilo["debolezza_principale"]:
        d = profilo["debolezza_principale"]
        print(f"  --> Debolezza principale (per tasso): {d.upper()} "
              f"({profilo['tasso_errore_per_fase'][d]}%)")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python profilo.py "Nome Giocatore"')
        sys.exit(1)
    p = costruisci_profilo(sys.argv[1])
    if p is None:
        print(f"\nNessuna partita trovata per '{sys.argv[1]}'.\n")
        sys.exit(1)
    stampa_profilo(p)
