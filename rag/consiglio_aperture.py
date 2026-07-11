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

from aperture import ramificazione_eco, conta_linee  # noqa: E402

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
     "livello": 3, "obiettivi": {"migliorare", "competere"},
     "perche": "La risposta piu' combattiva a 1.e4, ma tantissima teoria: da affrontare da esperti."},
    {"nome": "Est-Indiana (King's Indian)", "colore": "nero", "mosse": "d2d4 g8f6 c2c4 g7g6",
     "livello": 3, "obiettivi": {"migliorare", "competere"},
     "perche": "Dinamica e ricca di attacchi, ma impegnativa: da affrontare con esperienza."},
    # --- Catalogo ampliato (galleria 'Tutte le aperture') ---
    {"nome": "Difesa dei Due Cavalli", "colore": "nero", "mosse": "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "Rispondi all'Italiana attaccando: inviti complicazioni e contrattacchi subito."},
    {"nome": "Attacco Fegatello (Fried Liver)", "colore": "bianco", "mosse": "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 f3g5",
     "livello": 2, "obiettivi": {"divertimento", "competere"},
     "perche": "Punti f7 con Cg5: una delle linee piu' aggressive e trappolose per il Bianco."},
    {"nome": "Contrattacco Traxler", "colore": "nero", "mosse": "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 f3g5 f8c5",
     "livello": 3, "obiettivi": {"divertimento", "competere"},
     "perche": "Ignori la minaccia su f7 e attacchi tu: caos totale, roba da temerari."},
    {"nome": "Gambetto di Re", "colore": "bianco", "mosse": "e2e4 e7e5 f2f4",
     "livello": 2, "obiettivi": {"divertimento", "competere"},
     "perche": "Sacrifichi un pedone per aprire la colonna f e attaccare il re: romantico e tagliente."},
    {"nome": "Gambetto Evans", "colore": "bianco", "mosse": "e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 b2b4",
     "livello": 2, "obiettivi": {"divertimento", "competere"},
     "perche": "Offri un pedone nell'Italiana per un vantaggio di sviluppo travolgente."},
    {"nome": "Gambetto Danese", "colore": "bianco", "mosse": "e2e4 e7e5 d2d4 e5d4 c2c3",
     "livello": 2, "obiettivi": {"divertimento"},
     "perche": "Sacrifichi uno, poi due pedoni per due alfieri feroci puntati sul re nero."},
    {"nome": "Difesa Petrov (Russa)", "colore": "nero", "mosse": "e2e4 e7e5 g1f3 g8f6",
     "livello": 2, "obiettivi": {"migliorare"},
     "perche": "Invece di difendere e5 contrattacchi e4: solida, simmetrica, molto sicura."},
    {"nome": "Difesa Philidor", "colore": "nero", "mosse": "e2e4 e7e5 g1f3 d7d6",
     "livello": 1, "obiettivi": {"migliorare"},
     "perche": "Difesa compatta e senza fronzoli contro 1.e4: poca teoria, struttura sana."},
    {"nome": "Difesa Pirc", "colore": "nero", "mosse": "e2e4 d7d6 d2d4 g8f6 b1c3 g7g6",
     "livello": 2, "obiettivi": {"competere"},
     "perche": "Lasci il centro al Bianco per poi colpirlo dai fianchi col fianchetto."},
    {"nome": "Difesa Alekhine", "colore": "nero", "mosse": "e2e4 g8f6",
     "livello": 2, "obiettivi": {"divertimento", "competere"},
     "perche": "Provochi i pedoni bianchi ad avanzare per poi attaccarli: ipermoderna."},
    {"nome": "Difesa Nimzo-Indiana", "colore": "nero", "mosse": "d2d4 g8f6 c2c4 e7e6 b1c3 f8b4",
     "livello": 3, "obiettivi": {"competere"},
     "perche": "Inchiodi il cavallo c3 e giochi sui pedoni doppiati: raffinata e rispettatissima."},
    {"nome": "Difesa Ovest-Indiana", "colore": "nero", "mosse": "d2d4 g8f6 c2c4 e7e6 g1f3 b7b6",
     "livello": 3, "obiettivi": {"competere"},
     "perche": "Fianchetti l'alfiere di donna e controlli e4 a distanza: gioco posizionale."},
    {"nome": "Difesa Grunfeld", "colore": "nero", "mosse": "d2d4 g8f6 c2c4 g7g6 b1c3 d7d5",
     "livello": 3, "obiettivi": {"competere"},
     "perche": "Lasci costruire un centro al Bianco per demolirlo dai fianchi: dinamica e affilata."},
    {"nome": "Difesa Olandese", "colore": "nero", "mosse": "d2d4 f7f5",
     "livello": 2, "obiettivi": {"divertimento", "competere"},
     "perche": "Contro 1.d4 punti subito all'attacco sul re con la colonna f."},
    {"nome": "Apertura Inglese", "colore": "bianco", "mosse": "c2c4",
     "livello": 2, "obiettivi": {"migliorare", "competere"},
     "perche": "Controlli d5 dal fianco: flessibile, ricca di trasposizioni, poca teoria forzata."},
    {"nome": "Apertura Reti", "colore": "bianco", "mosse": "g1f3 d7d5 c2c4",
     "livello": 2, "obiettivi": {"competere"},
     "perche": "Ipermoderna: sviluppi e attacchi il centro nero da lontano."},
    {"nome": "Gambetto Viennese", "colore": "bianco", "mosse": "e2e4 e7e5 b1c3 g8f6 f2f4",
     "livello": 2, "obiettivi": {"divertimento", "competere"},
     "perche": "La Viennese che morde: apri la colonna f e vai all'attacco."},
    {"nome": "Gambetto di Budapest", "colore": "nero", "mosse": "d2d4 g8f6 c2c4 e7e5",
     "livello": 2, "obiettivi": {"divertimento"},
     "perche": "Sorpresa contro 1.d4: offri un pedone per pezzi attivi e trappole insidiose."},
]


def _livello_target(fascia_elo):
    """Fascia Elo -> livello ADATTO (non 'massimo cumulativo'): le raccomandazioni si CENTRANO
    su questo livello, cosi' CAMBIANO con la fascia invece di solo aumentare di numero.

    Fasce Elo (definite da Miguel) mappate sui 3 livelli delle aperture curate:
      500-1250   principiante (prime armi / base / avanzato) -> livello 1
      1250-1750  intermedio (base / avanzato)                -> livello 2
      1750+      avanzato                                     -> livello 3
    """
    if fascia_elo is None or fascia_elo < 1250:
        return 1
    if fascia_elo < 1750:
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

    RESTITUISCE {livello_target, consigli (ordinati: vicinanza al livello poi complessita'),
    nota_tempo, nota}. Ogni consiglio: nome, colore, livello, complessita', mosse, perche.
    """
    f_complessita = f_complessita or ramificazione_eco
    target = _livello_target(fascia_elo)

    def col_ok(a):
        return colore in ("entrambi", a["colore"])

    def ob_ok(a):
        return obiettivo is None or obiettivo in a["obiettivi"]

    # Primario: aperture AL livello adatto. Se troppo poche, aggiungo il livello subito SOTTO
    # (accessibili), MAI quelle sopra (troppo difficili). Cosi' la rosa CAMBIA con la fascia.
    cand = [a for a in APERTURE_CURATE if a["livello"] == target and col_ok(a) and ob_ok(a)]
    if len(cand) < 3:
        cand += [a for a in APERTURE_CURATE
                 if a["livello"] == target - 1 and col_ok(a) and ob_ok(a) and a not in cand]
    if not cand:  # obiettivo troppo restrittivo: rilasso l'obiettivo (tengo livello<=target e colore)
        cand = [a for a in APERTURE_CURATE if a["livello"] <= target and col_ok(a)]

    consigli = []
    for a in cand:
        consigli.append({
            "nome": a["nome"], "colore": a["colore"], "livello": a["livello"],
            "mosse": a["mosse"], "perche": a["perche"],
            "complessita": f_complessita(a["mosse"].split()),
            "obiettivi": sorted(a["obiettivi"]),
        })
    # Ordino: prima le piu' vicine al tuo livello, poi le piu' semplici.
    consigli.sort(key=lambda c: (abs(c["livello"] - target), c["complessita"]))
    return {
        "livello_target": target,
        "consigli": consigli,
        "nota_tempo": _nota_tempo(minuti),
        "nota": ("Rosa CURATA di aperture solide, ordinata per complessita' (dati ECO reali) "
                 "e filtrata per il tuo livello/obiettivo. Puoi comunque studiare qualsiasi "
                 "apertura: questi sono solo i consigliati da cui partire."),
    }


def catalogo(f_conta=None):
    """Catalogo COMPLETO delle aperture curate per la galleria 'Tutte le aperture'. Per ognuna:
    nome, colore, livello, mosse (linea che la definisce), descrizione (scritta a mano) e
    `linee` = numero di varianti ECO reali che passano di li' (proxy onesto, non inventato).
    `f_conta` e' iniettabile per i test (default: conta_linee dai dati ECO)."""
    f_conta = f_conta or conta_linee
    return [{
        "nome": a["nome"], "colore": a["colore"], "livello": a["livello"],
        "mosse": a["mosse"], "descrizione": a["perche"],
        "obiettivi": sorted(a["obiettivi"]),
        "linee": f_conta(a["mosse"].split()),
    } for a in APERTURE_CURATE]


if __name__ == "__main__":
    elo = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    obiettivo = sys.argv[2] if len(sys.argv) > 2 else "migliorare"
    minuti = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    res = consiglia(elo, obiettivo, minuti)
    print(f"\nElo {elo}, obiettivo '{obiettivo}', {minuti} min/giorno -> livello adatto {res['livello_target']}")
    print(res["nota_tempo"])
    print("\nAperture consigliate (dalla piu' semplice):")
    for c in res["consigli"]:
        print(f"  [{c['colore']:6} L{c['livello']} compl {c['complessita']:3}] {c['nome']}")
        print(f"        {c['perche']}")
    print(f"\n{res['nota']}\n")
