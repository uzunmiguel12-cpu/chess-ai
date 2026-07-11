"""
Coach delle aperture (runtime): legge le spiegazioni PRE-GENERATE offline (genera_coach.py)
da una cache JSON e le serve per lookup. Nessun LLM in linea: il modello "pensa" una volta
sola, durante la generazione; qui si legge soltanto.

Onesta' (sostanza non apparenza): le spiegazioni sono testo statico ispezionabile, ancorato
alla posizione reale (mosse + nome ECO). Se una posizione non e' ancora stata generata, il
coach semplicemente non ha nulla da dire (disponibile=False), niente testo inventato al volo.
"""

import os
import json
import logging

logger = logging.getLogger("rag")

COACH_FILE = os.path.join(os.path.dirname(__file__), "coach_aperture.json")
_CACHE = None
_MTIME = None


def chiave(mosse_uci):
    """Chiave di cache = sequenza di mosse UCI separata da spazio (posizione = percorso)."""
    return " ".join(mosse_uci)


def carica_coach(percorso=None):
    """Carica la cache delle spiegazioni (dict chiave->testo). Si RICARICA automaticamente se il
    file e' cambiato (mtime): cosi', mentre la generazione gira, le nuove spiegazioni compaiono
    dal vivo senza riavviare il backend. Se il file non c'e' ancora, restituisce un dict vuoto."""
    global _CACHE, _MTIME
    p = percorso or COACH_FILE
    mt = os.path.getmtime(p) if os.path.exists(p) else None
    if _CACHE is None or percorso is not None or mt != _MTIME:
        if mt is not None:
            with open(p, "r", encoding="utf-8") as f:
                _CACHE = json.load(f)
            logger.info("Coach: caricate %d spiegazioni da %s", len(_CACHE), p)
        else:
            _CACHE = {}
            logger.warning("Coach: cache non trovata (%s): il coach non ha spiegazioni.", p)
        _MTIME = mt
    return _CACHE


def spiega(mosse_uci, cache=None):
    """Restituisce la spiegazione pre-generata per la posizione (o None se non c'e')."""
    c = cache if cache is not None else carica_coach()
    return c.get(chiave(mosse_uci))
