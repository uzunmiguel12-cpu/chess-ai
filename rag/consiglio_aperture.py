"""
Modulo CONSIGLIO APERTURE (modulo Aperture, v1) - questionario + motore di consiglio.

Dato il questionario dell'utente (fascia Elo, obiettivo, minuti al giorno, colore), propone
DA QUALI aperture partire. Approccio deciso: ROSA CURATA di aperture solide e note, ordinata
per COMPLESSITA' reale (ramificazione_eco dai dati ECO) e filtrata per livello/obiettivo.

Onesta' (sostanza non apparenza):
  - La rosa e' una SCELTA CURATA dichiarata (aperture standard consigliate ai principianti),
    NON un ranking di popolarita' (l'Explorer, che darebbe la popolarita' reale, e' bloccato).
  - La complessita' (quante varianti) viene dai DATI ECO reali, non e' inventata.
  - Niente "minuti per apertura" finti: il tempo diventa un consiglio QUALITATIVO.
  - Il sistema CONSIGLIA soltanto: l'utente puo' studiare qualsiasi apertura.
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag")

from aperture import ramificazione_eco  # noqa: E402

# Livelli: 1 = principiante, 2 = intermedio, 3 = avanzato.
# Obiettivi: "divertimento", "migliorare", "competere".
# Le mosse sono la linea che DEFINISCE l'apertura (UCI); la complessita' si calcola da li'.
APERTURE_CURATE = [
    {"nome": "Italiana", "colore": "bianco", "mosse": "e2e4 e7e5 g1f3 b8c6 f1c4",
     "livello": 1, "obiettivi": {"divertimento", "migliorare"},
     "perche": "Sviluppo naturale e piani chiari: ideale per iniziare col Bianco."},
    {"nome": "Sistema Londra", "colore": "bianco", "mosse": "d2d4 d7d5 c1f4",
     "livello": 1, "obiettivi": {"divertimento", "migliorare"},
     "perche": "E' un 'sistema': stesse mosse contro quasi tutto, poca teoria da ricordare."},
    {"nome": "Partita Viennese", "colore": "bianco", "mosse": "e2e4 e7e5 b1c3",
     "livello": 1, "obiettivi": {"divertimento"},
     "perche": "Semplice e aggressiva, buona per prendere confidenza con l'attacco."},
    {"nome": "Scozzese", "colore": "bianco", "mosse": "e2e4 e7e5 g1f3 b8c6 d2d4",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "Apre subito il centro: posizioni chiare, meno teoria della Spagnola."},
    {"nome": "Spagnola (Ruy Lopez)", "colore": "bianco", "mosse": "e2e4 e7e5 g1f3 b8c6 f1b5",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "L'apertura classica per eccellenza: tanta teoria ma insegna tantissimo."},
    {"nome": "Gambetto di Donna", "colore": "bianco", "mosse": "d2d4 d7d5 c2c4",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "Gioco posizionale solido col Bianco, un classico del gioco di donna."},
    {"nome": "Scandinava", "colore": "nero", "mosse": "e2e4 d7d5",
     "livello": 1, "obiettivi": {"divertimento", "migliorare"},
     "perche": "Contro 1.e4 porti subito la donna in gioco: piani semplici e diretti."},
    {"nome": "Caro-Kann", "colore": "nero", "mosse": "e2e4 c7c6",
     "livello": 1, "obiettivi": {"migliorare"},
     "perche": "Solida e affidabile contro 1.e4, struttura di pedoni sana."},
    {"nome": "Francese", "colore": "nero", "mosse": "e2e4 e7e6",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "Struttura chiusa e piani chiari; insegna il gioco sui pedoni."},
    {"nome": "Gambetto di Donna Rifiutato", "colore": "nero", "mosse": "d2d4 d7d5 c2c4 e7e6",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "Risposta classica e solida a 1.d4."},
    {"nome": "Difesa Slava", "colore": "nero", "mosse": "d2d4 d7d5 c2c4 c7c6",
     "livello": 2, "obiettivi": {"migliorare"},
     "perche": "Solida contro 1.d4, tiene l'alfiere di donna attivo."},
    {"nome": "Siciliana", "colore": "nero", "mosse": "e2e4 c7c5",
     "livello": 3, "obiettivi": {"competere"},
     "perche": "La risposta piu' combattiva a 1.e4, ma tantissima teoria: meglio piu' avanti."},
    {"nome": "Est-Indiana (King's Indian)", "colore": "nero", "mosse": "d2d4 g8f6 c2c4 g7g6",
     "livello": 3, "obiettivi": {"competere"},
     "perche": "Dinamica e ricca di attacchi, ma impegnativa: da affrontare con esperienza."},
]


def _livello_max(fascia_elo):
    """Fascia Elo -> livello massimo di apertura consigliato (curato, dichiarato)."""
    if fascia_elo is None or fascia_elo < 1200:
        return 1
    if fascia_elo < 1600:
        return 2
    return 3


def _nota_tempo(minuti):
    """Consiglio QUALITATIVO dal tempo giornaliero: niente minuti-per-apertura inventati."""
    if minuti is None:
        return "Studia al tuo ritmo: impara bene le idee di un'apertura prima di aggiungerne."
    if minuti < 20:
        return ("Poco tempo al giorno: concentrati su 1-2 aperture e imparane bene le idee "
                "prima di allargare il repertorio.")
    if minuti <= 45:
        return "Tempo medio: 2-3 aperture, alternando Bianco e Nero."
    return "Buon tempo a disposizione: puoi coprire un repertorio piu' ampio."


def consiglia(fascia_elo, obiettivo, minuti, colore="entrambi", f_complessita=None):
    """
    Motore di consiglio. `colore` in {"bianco","nero","entrambi"}. `f_complessita` e' iniettabile
    per i test (default: ramificazione_eco dai dati ECO reali).

    RESTITUISCE {livello_max, consigli (ordinati: livello poi complessita' crescente),
    nota_tempo, nota}. Ogni consiglio: nome, colore, livello, complessita', mosse, perche.
    """
    f_complessita = f_complessita or ramificazione_eco
    lmax = _livello_max(fascia_elo)

    def compatibile(a):
        return (a["livello"] <= lmax
                and colore in ("entrambi", a["colore"])
                and (obiettivo is None or obiettivo in a["obiettivi"]))

    cand = [a for a in APERTURE_CURATE if compatibile(a)]
    if not cand:  # l'obiettivo filtra troppo: rilasso all'obiettivo, tenendo livello/colore
        cand = [a for a in APERTURE_CURATE
                if a["livello"] <= lmax and colore in ("entrambi", a["colore"])]

    consigli = []
    for a in cand:
        consigli.append({
            "nome": a["nome"], "colore": a["colore"], "livello": a["livello"],
            "mosse": a["mosse"], "perche": a["perche"],
            "complessita": f_complessita(a["mosse"].split()),
            "obiettivi": sorted(a["obiettivi"]),
        })
    consigli.sort(key=lambda c: (c["livello"], c["complessita"]))
    return {
        "livello_max": lmax,
        "consigli": consigli,
        "nota_tempo": _nota_tempo(minuti),
        "nota": ("Rosa CURATA di aperture solide, ordinata per complessita' (dati ECO reali) "
                 "e filtrata per il tuo livello/obiettivo. Puoi comunque studiare qualsiasi "
                 "apertura: questi sono solo i consigliati da cui partire."),
    }


if __name__ == "__main__":
    elo = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    obiettivo = sys.argv[2] if len(sys.argv) > 2 else "migliorare"
    minuti = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    res = consiglia(elo, obiettivo, minuti)
    print(f"\nElo {elo}, obiettivo '{obiettivo}', {minuti} min/giorno -> livello max {res['livello_max']}")
    print(res["nota_tempo"])
    print("\nAperture consigliate (dalla piu' semplice):")
    for c in res["consigli"]:
        print(f"  [{c['colore']:6} L{c['livello']} compl {c['complessita']:3}] {c['nome']}")
        print(f"        {c['perche']}")
    print(f"\n{res['nota']}\n")
