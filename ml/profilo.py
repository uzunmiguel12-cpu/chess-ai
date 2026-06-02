"""
Modulo profilo giocatore (Fase 3) - costruisce il profilo di debolezze.

Dato un nome di giocatore, scorre tutte le partite arricchite in
data/categorie/, raccoglie SOLO gli errori di quel giocatore (mosse del
colore con cui giocava in ogni partita), e costruisce un profilo con:
- conteggi per gravita (imprecisione / errore / blunder)
- conteggi per fase (apertura / mediogioco / finale)
- percentuali
- debolezza principale (la fase dove si concentrano gli errori gravi)

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

# Consideriamo "errori veri" solo le mosse con queste gravita
# (le mosse "ok" e "imprecisione" non sono debolezze da allenare).
GRAVITA_ERRORE = {"errore", "blunder"}


def _normalizza(nome):
    """Rende il confronto tra nomi robusto: minuscole, niente spazi extra."""
    return nome.strip().lower()


def _errori_del_giocatore(dato_partita, nome_norm):
    """
    Data una partita arricchita, restituisce la lista degli errori commessi
    dal giocatore indicato (se ha giocato in quella partita), con la fase.

    In una partita le mosse si alternano: indice 0 = Bianco, 1 = Nero,
    2 = Bianco, ... quindi le mosse di indice pari sono del Bianco.
    """
    bianco = _normalizza(dato_partita.get("bianco", ""))
    nero = _normalizza(dato_partita.get("nero", ""))

    if nome_norm == bianco:
        colore_pari = True   # il giocatore e' il Bianco -> mosse pari
    elif nome_norm == nero:
        colore_pari = False  # il giocatore e' il Nero -> mosse dispari
    else:
        return []  # il giocatore non ha giocato questa partita

    errori = []
    for i, mossa in enumerate(dato_partita["mosse"]):
        e_del_giocatore = (i % 2 == 0) if colore_pari else (i % 2 == 1)
        if e_del_giocatore:
            errori.append(mossa)
    return errori


def costruisci_profilo(nome, cartella=CARTELLA_CATEGORIE):
    """
    Costruisce il profilo del giocatore indicato leggendo tutte le partite
    arricchite. RESTITUISCE un dizionario col profilo, o None se il giocatore
    non compare in nessuna partita.
    """
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
        mosse_giocatore = _errori_del_giocatore(dato, nome_norm)
        if mosse_giocatore:
            partite_trovate += 1
            tutte_mosse.extend(mosse_giocatore)

    if partite_trovate == 0:
        logger.warning("Nessuna partita trovata per '%s'", nome)
        return None

    # Contiamo le gravita su tutte le mosse del giocatore.
    conteggio_gravita = Counter(m["gravita"] for m in tutte_mosse)

    # Contiamo le fasi SOLO sugli errori veri (errore + blunder).
    errori_veri = [m for m in tutte_mosse if m["gravita"] in GRAVITA_ERRORE]
    conteggio_fase = Counter(m["fase"] for m in errori_veri)

    totale_mosse = len(tutte_mosse)
    totale_errori = len(errori_veri)

    # Percentuali di errore per fase (su quanti errori gravi in quella fase).
    percentuali_fase = {}
    for fase, n in conteggio_fase.items():
        percentuali_fase[fase] = round(100 * n / totale_errori, 1) if totale_errori else 0.0

    # Debolezza principale: la fase con piu' errori gravi.
    debolezza = conteggio_fase.most_common(1)[0][0] if conteggio_fase else None

    profilo = {
        "giocatore": nome,
        "partite_analizzate": partite_trovate,
        "mosse_totali": totale_mosse,
        "errori_gravi_totali": totale_errori,
        "conteggio_gravita": dict(conteggio_gravita),
        "errori_per_fase": dict(conteggio_fase),
        "percentuali_per_fase": percentuali_fase,
        "debolezza_principale": debolezza,
    }
    logger.info("Profilo costruito: %d partite, %d errori gravi",
                partite_trovate, totale_errori)
    return profilo


def stampa_profilo(profilo):
    """Mostra il profilo in modo leggibile."""
    print()
    print(f"=== Profilo di {profilo['giocatore']} ===")
    print(f"Partite analizzate: {profilo['partite_analizzate']}")
    print(f"Mosse totali: {profilo['mosse_totali']}")
    print()
    print("Gravita delle mosse:")
    for g in ("ok", "imprecisione", "errore", "blunder"):
        n = profilo["conteggio_gravita"].get(g, 0)
        print(f"  {g:13}: {n}")
    print()
    print(f"Errori gravi totali (errore+blunder): {profilo['errori_gravi_totali']}")
    if profilo["errori_per_fase"]:
        print("Errori gravi per fase:")
        for fase in ("apertura", "mediogioco", "finale"):
            n = profilo["errori_per_fase"].get(fase, 0)
            perc = profilo["percentuali_per_fase"].get(fase, 0.0)
            print(f"  {fase:11}: {n}  ({perc}%)")
        print()
        print(f"  --> Debolezza principale: {profilo['debolezza_principale'].upper()}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Uso: python profilo.py "Nome Giocatore"')
        sys.exit(1)

    p = costruisci_profilo(sys.argv[1])
    if p is None:
        print(f"\nNessuna partita trovata per '{sys.argv[1]}'.")
        print("Verifica che le partite siano in data/categorie/ e il nome sia corretto.\n")
        sys.exit(1)

    stampa_profilo(p)
