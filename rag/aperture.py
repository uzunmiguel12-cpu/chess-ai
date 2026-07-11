"""
Modulo APERTURE - spina dorsale dati (v1 del modulo Aperture).

Fonte della conoscenza (decisa): dati REALI, mai inventati.
  - ECO: nome dell'apertura <-> sequenza di mosse (dataset lichess/chess-openings).
  - Lichess Opening Explorer: per una posizione, quali mosse si giocano DAVVERO e con
    che risultato, FILTRABILI per fascia Elo. E' cio' che rende onesti i consigli e i
    puzzle d'apertura (la "mossa da libro" = quella piu' giocata/che segna meglio alla
    tua fascia, non una mia opinione).

Questo file NON contiene teoria scritta a mano: espone solo dati reali. Il "coach a parole"
(LLM) e' la v2 e sara' VINCOLATO a commentare queste linee, mai a inventarne.

Uso (demo):
    python aperture.py e2e4 e7e5            # nome apertura + continuazioni reali per fascia
    python aperture.py e2e4 c7c5 --elo 1400

NB rete: le funzioni che interrogano l'Explorer fanno una chiamata HTTP (con cache locale).
Il parser (_parse_continuazioni, ramificazione) e' PURO e testabile senza rete.
"""

import os
import sys
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")

URL_EXPLORER = "https://explorer.lichess.ovh/lichess"

# Bucket di rating ammessi dall'Explorer (li usiamo per tradurre una fascia Elo).
BUCKET_ELO = [0, 1000, 1200, 1400, 1600, 1800, 2000, 2200, 2500]

# Cache locale delle risposte Explorer (evita di ri-chiamare la rete per la stessa query).
CARTELLA_CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "cache_aperture")

# Sample ECO (prototipo): il dataset COMPLETO (lichess/chess-openings, ~3000 linee) va
# scaricato in data/aperture_eco.tsv e caricato con carica_eco(). Qui poche linee per
# far girare la demo/i test senza dipendere dal file. Chiave = sequenza UCI separata da spazi.
ECO_SAMPLE = {
    "e2e4 e7e5 g1f3 b8c6 f1c4": ("C50", "Italian Game"),
    "e2e4 e7e5 g1f3 b8c6 f1b5": ("C60", "Ruy Lopez"),
    "e2e4 e7e5 g1f3 b8c6": ("C44", "King's Knight, Open"),
    "e2e4 e7e5 g1f3": ("C40", "King's Knight Opening"),
    "e2e4 e7e5": ("C20", "King's Pawn Game"),
    "e2e4 c7c5": ("B20", "Sicilian Defense"),
    "d2d4 d7d5 c2c4": ("D06", "Queen's Gambit"),
    "e2e4 e7e6": ("C00", "French Defense"),
}


def _fascia_a_bucket(elo):
    """Traduce un Elo nel bucket dell'Explorer piu' vicino (per difetto). None -> tutti."""
    if elo is None:
        return None
    scelto = BUCKET_ELO[0]
    for b in BUCKET_ELO:
        if b <= elo:
            scelto = b
    return scelto


def nome_apertura(mosse_uci, eco_map=None):
    """
    [DATO] Nome ECO dell'apertura raggiunta, per PREFISSO PIU' LUNGO conosciuto (come funziona
    la classificazione ECO: l'ultima linea nota che e' prefisso delle mosse giocate).
    `mosse_uci` = lista di UCI. Restituisce (eco, nome) o None. Usa eco_map o il sample.
    """
    eco_map = eco_map if eco_map is not None else _eco_default()
    trovato = None
    for i in range(len(mosse_uci), 0, -1):
        chiave = " ".join(mosse_uci[:i])
        if chiave in eco_map:
            trovato = eco_map[chiave]
            break
    return trovato


def carica_eco(percorso):
    """
    Carica il dataset ECO completo da un TSV (colonne: eco, name, pgn/uci). Formato tollerante:
    ci si aspetta una sequenza di mosse per riga; se il file non c'e', restituisce il sample.
    (Il download del dataset e' un TODO documentato: lichess/chess-openings.)
    """
    if not percorso or not os.path.exists(percorso):
        logger.warning("Dataset ECO non trovato (%s): uso il sample.", percorso)
        return dict(ECO_SAMPLE)
    eco_map = {}
    with open(percorso, "r", encoding="utf-8") as f:
        for riga in f:
            parti = riga.rstrip("\n").split("\t")
            if len(parti) < 3:
                continue
            eco, nome, mosse = parti[0], parti[1], parti[2].strip()
            if eco.lower() == "eco":  # header
                continue
            eco_map[mosse] = (eco, nome)
    logger.info("ECO caricato: %d linee da %s", len(eco_map), percorso)
    return eco_map


# Dataset ECO completo (scaricato con scarica_eco.py); se manca, si usa il sample.
ECO_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "aperture_eco.tsv")
_ECO_CACHE = None


def _eco_default():
    """Carica UNA volta il dataset ECO da data/aperture_eco.tsv se esiste, altrimenti
    ripiega sul sample. Cache a livello di modulo (evita riletture)."""
    global _ECO_CACHE
    if _ECO_CACHE is None:
        _ECO_CACHE = carica_eco(ECO_FILE)
    return _ECO_CACHE


def continuazioni_eco(mosse_uci, eco_map=None):
    """
    [DATO offline] Continuazioni NOTE dall'albero ECO dopo `mosse_uci`: quali mosse proseguono
    una linea ECO che passa da questa posizione. Per ciascuna: uci, quante linee ECO la
    attraversano ('linee' = proxy di quanto e' battuta/sviluppata), ed eco/nome se P+mossa e'
    esattamente una linea nominata. Ordinate per numero di linee (le piu' sviluppate prima).
    Sostituisce il ruolo dell'Explorer (bloccato) per consigli, studio e puzzle d'apertura.
    """
    eco_map = eco_map if eco_map is not None else _eco_default()
    p = list(mosse_uci)
    n = len(p)
    agg = {}
    for chiave in eco_map:
        mosse = chiave.split()
        if len(mosse) > n and mosse[:n] == p:
            nxt = mosse[n]
            agg.setdefault(nxt, {"uci": nxt, "linee": 0, "eco": None, "nome": None})["linee"] += 1
    for nxt, slot in agg.items():
        esatta = " ".join(p + [nxt])
        if esatta in eco_map:
            slot["eco"], slot["nome"] = eco_map[esatta]
    return sorted(agg.values(), key=lambda s: s["linee"], reverse=True)


def ramificazione_eco(mosse_uci, eco_map=None):
    """[DATO offline] Numero di continuazioni note nell'ECO = proxy ONESTO di complessita'
    dell'apertura (poche continuazioni = piu' semplice da studiare). Per i consigli."""
    return len(continuazioni_eco(mosse_uci, eco_map))


def conta_linee(mosse_uci, eco_map=None):
    """[DATO offline] Quante linee ECO nominate passano da questa posizione: proxy ONESTO di
    'quante varianti ha' l'apertura (per la galleria 'Tutte le aperture', stile 'N lines total').
    Conta le chiavi ECO la cui sequenza inizia con `mosse_uci` (la linea stessa + le sue estensioni)."""
    eco_map = eco_map if eco_map is not None else _eco_default()
    p = list(mosse_uci)
    n = len(p)
    return sum(1 for k in eco_map if k.split()[:n] == p)


def mossa_da_libro_eco(mosse_uci, eco_map=None):
    """[DATO offline] La mossa 'da libro' senza Explorer: la continuazione ECO piu' sviluppata
    (con piu' linee). E' la risposta corretta dei puzzle d'apertura. None se non ce ne sono."""
    cont = continuazioni_eco(mosse_uci, eco_map)
    return cont[0]["uci"] if cont else None


def linea_principale_eco(mosse_uci, max_extra=8, eco_map=None):
    """[DATO offline] Estende la linea data seguendo la mossa da libro (principale) ad ogni passo.
    Restituisce (punti, linea): `punti` = lista di (prefisso, mossa_corretta) su cui si puo'
    interrogare l'utente; `linea` = la sequenza completa raggiunta. Si ferma quando esce dal libro
    o dopo max_extra semimosse (evita cicli/lunghezze eccessive)."""
    seq = list(mosse_uci)
    punti = []
    for _ in range(max_extra):
        m = mossa_da_libro_eco(seq, eco_map)
        if not m:
            break
        punti.append((list(seq), m))
        seq.append(m)
    return punti, seq


def puzzle_apertura(mosse_uci, indice=None, max_extra=8, eco_map=None):
    """[DATO offline] Genera un puzzle 'prosegui dalla mossa N' a partire dalla linea di
    un'apertura. Interroga sulle mosse PRINCIPALI che estendono la linea (la teoria che segue).
    `indice` sceglie la profondita' (0 = prima mossa fuori dalla linea data; default = la piu'
    profonda). NON espone la risposta: si verifica con verifica_puzzle. None se non c'e' teoria."""
    punti, _ = linea_principale_eco(mosse_uci, max_extra, eco_map)
    if not punti:
        return None
    if indice is None:
        indice = len(punti) - 1
    indice = max(0, min(indice, len(punti) - 1))
    prefisso, _corretta = punti[indice]
    ply = len(prefisso)
    nome = nome_apertura(prefisso, eco_map)
    return {
        "setup": prefisso,
        "numero_mossa": ply // 2 + 1,
        "lato": "bianco" if ply % 2 == 0 else "nero",
        "indice": indice,
        "totale": len(punti),
        "apertura": ({"eco": nome[0], "nome": nome[1]} if nome else None),
    }


def verifica_puzzle(setup_uci, mossa_uci, eco_map=None):
    """[DATO offline] Verifica server-side del puzzle: corretto solo se la mossa e' LA principale
    da libro (per scelta: drill sulla linea principale). Rivela l'attesa dopo il tentativo."""
    corretta = mossa_da_libro_eco(setup_uci, eco_map)
    ok = bool(corretta) and (mossa_uci or "")[:4].lower() == corretta[:4].lower()
    dopo = nome_apertura(list(setup_uci) + [corretta], eco_map) if corretta else None
    return {
        "corretto": ok,
        "attesa": corretta,
        "apertura_dopo": ({"eco": dopo[0], "nome": dopo[1]} if dopo else None),
    }


def _parse_continuazioni(dati):
    """
    [DATO - PURO, testabile senza rete] Dalla risposta dell'Explorer estrae le continuazioni
    ordinate per frequenza. Per ogni mossa: uci, san, giocate (= bianco+patte+nero), quota
    (frazione sul totale delle partite in quella posizione), punteggio_bianco (% di vittorie
    del bianco su quella mossa). Restituisce anche 'apertura' (eco/nome) se presente.
    """
    mosse = dati.get("moves", []) or []
    totale = sum((m.get("white", 0) + m.get("draws", 0) + m.get("black", 0)) for m in mosse)
    cont = []
    for m in mosse:
        giocate = m.get("white", 0) + m.get("draws", 0) + m.get("black", 0)
        cont.append({
            "uci": m.get("uci"),
            "san": m.get("san"),
            "giocate": giocate,
            "quota": round(giocate / totale, 3) if totale else 0.0,
            "punteggio_bianco": round(100 * m.get("white", 0) / giocate, 1) if giocate else 0.0,
            "rating_medio": m.get("averageRating"),
        })
    ap = dati.get("opening") or None
    return {
        "apertura": ({"eco": ap.get("eco"), "nome": ap.get("name")} if ap else None),
        "continuazioni": cont,   # gia' ordinate per frequenza dall'Explorer
        "totale_partite": totale,
    }


def ramificazione(dati, soglia=0.1):
    """
    [DATO - PURO] Quanto e' "ramificata" una posizione = quante continuazioni comuni ha
    (quota >= soglia). E' il proxy ONESTO di "complessita'/quante varianti" per i consigli:
    poche continuazioni comuni = apertura piu' semplice da studiare. Niente numeri inventati.
    """
    parsed = _parse_continuazioni(dati) if "continuazioni" not in dati else dati
    return sum(1 for c in parsed["continuazioni"] if c["quota"] >= soglia)


def esplora(mosse_uci, fascia_elo=None, speeds=("blitz", "rapid"), usa_cache=True):
    """
    Interroga il Lichess Opening Explorer per la posizione dopo `mosse_uci` (lista UCI),
    filtrando per fascia Elo. FA UNA CHIAMATA HTTP (con cache locale su file). Restituisce
    l'output gia' passato a _parse_continuazioni, o None in caso di errore.
    """
    import requests  # import locale: il parser puro non dipende da requests

    bucket = _fascia_a_bucket(fascia_elo)
    ratings = [bucket] if bucket is not None else BUCKET_ELO
    params = {
        "variant": "standard",
        "play": ",".join(mosse_uci),
        "speeds": ",".join(speeds),
        "ratings": ",".join(str(r) for r in ratings),
        "topGames": 0, "recentGames": 0,
    }
    chiave_cache = json.dumps(params, sort_keys=True)
    percorso_cache = os.path.join(CARTELLA_CACHE, str(abs(hash(chiave_cache))) + ".json")
    if usa_cache and os.path.exists(percorso_cache):
        with open(percorso_cache, "r", encoding="utf-8") as f:
            return _parse_continuazioni(json.load(f))
    try:
        r = requests.get(URL_EXPLORER, params=params, timeout=15,
                         headers={"User-Agent": "chess-ai openings module (uzunmiguel12@gmail.com)"})
        r.raise_for_status()
        dati = r.json()
    except Exception as e:
        logger.error("Explorer non raggiungibile: %s", e)
        return None
    if usa_cache:
        os.makedirs(CARTELLA_CACHE, exist_ok=True)
        with open(percorso_cache, "w", encoding="utf-8") as f:
            json.dump(dati, f)
    return _parse_continuazioni(dati)


def mossa_da_libro(mosse_uci, fascia_elo=None):
    """
    La mossa "da libro" alla fascia: la piu' giocata nell'Explorer (la prima delle
    continuazioni). E' la risposta corretta dei PUZZLE d'apertura. None se non disponibile.
    """
    parsed = esplora(mosse_uci, fascia_elo)
    if not parsed or not parsed["continuazioni"]:
        return None
    return parsed["continuazioni"][0]["uci"]


if __name__ == "__main__":
    # Parsing argomenti: le mosse sono gli argomenti "nudi"; --elo N e' un'opzione col valore.
    mosse, elo, i, argv = [], None, 0, sys.argv[1:]
    while i < len(argv):
        if argv[i] == "--elo":
            elo = int(argv[i + 1]); i += 2
        else:
            mosse.append(argv[i]); i += 1
    print()
    nome = nome_apertura(mosse)
    print(f"Mosse: {' '.join(mosse)}")
    print(f"Apertura (ECO): {nome or '(non trovata nel dataset)'}")
    cont = continuazioni_eco(mosse)
    print(f"Ramificazione (continuazioni note nell'ECO): {len(cont)}")
    if cont:
        print("Continuazioni piu' sviluppate (n. di linee ECO che le attraversano):")
        for c in cont[:8]:
            etichetta = f"  -> {c['eco']} {c['nome']}" if c["nome"] else ""
            print(f"  {c['uci']}  [{c['linee']} linee]{etichetta}")
    else:
        print("Nessuna continuazione nota nell'ECO (posizione foglia o fuori teoria).")
    print()
    print("(NB: l'Explorer live darebbe le frequenze reali per fascia Elo, ma e' bloccato dalla tua rete.)")
    print()
