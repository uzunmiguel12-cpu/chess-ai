"""
Modulo profilo giocatore (Fase 3) - profilo di debolezze a tre dimensioni.

Dato un nome di giocatore, scorre le partite arricchite in data/categorie/ e
costruisce un profilo con:
- DOVE sbaglia: conteggi e TASSO di errore per fase (la debolezza principale
  e' la fase col tasso piu' alto, misura onesta)
- QUANTO gravemente: conteggi per gravita (scala stile Chess.com)
- COME sbaglia: dimensione tattica (pezzo in presa, forchetta) sugli errori
  gravi, con percentuali e distinzione per fase. Gli errori senza tipo tattico
  noto (posizionali, ecc.) finiscono in "non_tattico".

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
TIPI_TATTICI = ("pezzo_in_presa", "forchetta")


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

    mosse_per_fase = Counter(m["fase"] for m in tutte_mosse)
    errori_veri = [m for m in tutte_mosse if m["gravita"] in GRAVITA_ERRORE]
    errori_per_fase = Counter(m["fase"] for m in errori_veri)

    tasso_per_fase = {}
    for fase in FASI:
        mosse_fase = mosse_per_fase.get(fase, 0)
        errori_fase = errori_per_fase.get(fase, 0)
        tasso_per_fase[fase] = round(100 * errori_fase / mosse_fase, 1) if mosse_fase else 0.0

    fasi_valide = {f: t for f, t in tasso_per_fase.items() if mosse_per_fase.get(f, 0) > 0}
    debolezza = max(fasi_valide, key=fasi_valide.get) if fasi_valide else None

    # --- DIMENSIONE TATTICA (sugli errori gravi) ---
    totale_errori = len(errori_veri)

    # Conteggio per tipo tattico; gli errori senza tipo noto -> "non_tattico".
    conteggio_tattico = Counter()
    # Conteggio tipo tattico distinto per fase.
    tattico_per_fase = {tipo: Counter() for tipo in TIPI_TATTICI}

    for m in errori_veri:
        tipo = m.get("tipo_tattico")
        if tipo in TIPI_TATTICI:
            conteggio_tattico[tipo] += 1
            tattico_per_fase[tipo][m["fase"]] += 1
        else:
            conteggio_tattico["non_tattico"] += 1

    # Percentuali sul totale degli errori gravi.
    percentuali_tattico = {}
    for tipo in list(TIPI_TATTICI) + ["non_tattico"]:
        n = conteggio_tattico.get(tipo, 0)
        percentuali_tattico[tipo] = round(100 * n / totale_errori, 1) if totale_errori else 0.0

    profilo = {
        "giocatore": nome,
        "partite_analizzate": partite_trovate,
        "mosse_totali": len(tutte_mosse),
        "errori_gravi_totali": totale_errori,
        "conteggio_gravita": dict(conteggio_gravita),
        "mosse_per_fase": dict(mosse_per_fase),
        "errori_per_fase": dict(errori_per_fase),
        "tasso_errore_per_fase": tasso_per_fase,
        "debolezza_principale": debolezza,
        "conteggio_tattico": dict(conteggio_tattico),
        "percentuali_tattico": percentuali_tattico,
        "tattico_per_fase": {t: dict(c) for t, c in tattico_per_fase.items()},
    }
    logger.info("Profilo costruito: %d partite, %d errori gravi",
                partite_trovate, totale_errori)
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
    print("DOVE - per fase (errori / mosse = tasso):")
    for fase in FASI:
        err = profilo["errori_per_fase"].get(fase, 0)
        tot = profilo["mosse_per_fase"].get(fase, 0)
        tasso = profilo["tasso_errore_per_fase"].get(fase, 0.0)
        print(f"  {fase:11}: {err:4} / {tot:4} mosse  =  {tasso}% di errori")
    if profilo["debolezza_principale"]:
        d = profilo["debolezza_principale"]
        print(f"  --> Debolezza principale (per tasso): {d.upper()} "
              f"({profilo['tasso_errore_per_fase'][d]}%)")
    print()
    print("COME - tipo di errore (sugli errori gravi):")
    for tipo in TIPI_TATTICI:
        n = profilo["conteggio_tattico"].get(tipo, 0)
        perc = profilo["percentuali_tattico"].get(tipo, 0.0)
        per_fase = profilo["tattico_per_fase"].get(tipo, {})
        dettaglio_fase = ", ".join(f"{f}:{per_fase.get(f,0)}" for f in FASI)
        etichetta = tipo.replace("_", " ")
        print(f"  {etichetta:14}: {n:4}  ({perc}%)   [{dettaglio_fase}]")
    n_altro = profilo["conteggio_tattico"].get("non_tattico", 0)
    perc_altro = profilo["percentuali_tattico"].get("non_tattico", 0.0)
    print(f"  {'non tattico':14}: {n_altro:4}  ({perc_altro}%)   (errori posizionali, ecc.)")
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
