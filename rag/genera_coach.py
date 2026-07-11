"""
Generatore OFFLINE delle spiegazioni del coach (una tantum, ripristinabile). Usa un modello
locale via Ollama: il modello "ragiona" adesso, poi tutto resta memorizzato in coach_aperture.json
e a runtime si fa solo lookup (nessun LLM in linea).

USO (dalla cartella rag, con Ollama avviato e il modello scaricato):
    ollama pull qwen3:8b
    python genera_coach.py --modello qwen3:8b
Puoi fermarlo con Ctrl-C: salva man mano e, rilanciandolo, riprende da dove era (salta le
posizioni gia' fatte). Prova rapida: --limite 10.

ONESTA': il prompt vincola il modello a spiegare SOLO la mossa e i principi generali, senza
inventare varianti, sequenze future, nomi o valutazioni numeriche.
"""

import os
import sys
import json
import time
import re
import argparse
import urllib.request
import urllib.error

import chess

from aperture import carica_eco, nome_apertura, ECO_FILE
from coach import COACH_FILE


def nodi_ordinati(eco_map):
    """Tutte le posizioni uniche (prefissi di ogni linea ECO), ordinate per QUANTE linee ECO ci
    passano (decrescente): cosi' fermandoti presto copri le posizioni davvero PIU' COMUNI (e4, d4
    e le loro risposte principali), non le sidelines alfabeticamente prime. A parita', prima le
    meno profonde."""
    conta = {}
    for k in eco_map:
        mosse = k.split()
        for i in range(1, len(mosse) + 1):
            p = " ".join(mosse[:i])
            conta[p] = conta.get(p, 0) + 1
    return sorted(conta.keys(), key=lambda s: (-conta[s], len(s.split()), s))


def san_linea(mosse_uci):
    b = chess.Board()
    sans = []
    for u in mosse_uci:
        m = chess.Move.from_uci(u)
        sans.append(b.san(m))
        b.push(m)
    return sans


def prompt_per(mosse_uci, eco_map):
    sans = san_linea(mosse_uci)
    lato = "il Bianco" if (len(mosse_uci) - 1) % 2 == 0 else "il Nero"  # chi ha appena mosso
    ultima = sans[-1]
    nome = nome_apertura(mosse_uci, eco_map)
    nome_str = f"{nome[0]} — {nome[1]}" if nome else "apertura non nominata"
    linea = " ".join(f"{(i // 2) + 1}{'.' if i % 2 == 0 else '...'}{s}" for i, s in enumerate(sans))
    return (
        "Sei un istruttore di scacchi. Spiega in modo TECNICO e PROFESSIONALE, in ITALIANO corretto, "
        f"la mossa {ultima} appena giocata da {lato}.\n"
        f"Posizione (apertura: {nome_str}). Mosse giocate finora: {linea}.\n"
        "In 2-3 frasi CONCISE, PRECISE e mirate (ne' prolisse ne' troppo brevi) spiega perche' e' una "
        "buona mossa e cosa si ottiene: il principio che segue (sviluppo, controllo del centro, sicurezza "
        "del re, spazio, struttura di pedoni, attivita' dei pezzi), le case o le linee che controlla o apre, "
        "le minacce o i piani che prepara.\n"
        "REGOLE FERREE:\n"
        "- Scrivi SOLO in italiano corretto, senza NESSUNA parola inglese: usa 'il Bianco' e 'il Nero' "
        "(mai 'White'/'Black').\n"
        "- Usa i nomi italiani dei pezzi: pedone, cavallo, alfiere, torre, donna, re. MAI 'ministro' o "
        "altri termini stranieri o sbagliati.\n"
        "- Non inventare varianti o mosse future, non dare valutazioni numeriche, non inventare nomi, "
        "non dire che e' 'l'unica' o 'la migliore in assoluto' (in apertura ci sono spesso piu' buone mosse).\n"
        "Rispondi solo con la spiegazione, senza preamboli ne' elenchi puntati."
    )


def ollama(prompt, model, host, temp):
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"temperature": temp},
    }).encode("utf-8")
    req = urllib.request.Request(host.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out = json.loads(r.read().decode("utf-8"))
    testo = out.get("response", "")
    # Qwen3 puo' emettere un blocco di ragionamento <think>...</think>: teniamo solo la risposta.
    testo = re.sub(r"<think>.*?</think>", "", testo, flags=re.DOTALL).strip()
    return testo


def salva(cache, percorso):
    tmp = percorso + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)
    os.replace(tmp, percorso)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modello", default="qwen3:8b")
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--temp", type=float, default=0.4)
    ap.add_argument("--limite", type=int, default=0, help="genera al massimo N nuove (0 = tutte)")
    ap.add_argument("--ogni", type=int, default=20, help="salva ogni N generazioni")
    args = ap.parse_args()

    eco_map = carica_eco(ECO_FILE)
    nodi = nodi_ordinati(eco_map)
    cache = {}
    if os.path.exists(COACH_FILE):
        with open(COACH_FILE, encoding="utf-8") as f:
            cache = json.load(f)
    da_fare = [n for n in nodi if n not in cache]
    print(f"Nodi totali: {len(nodi)} | gia' fatti: {len(cache)} | da fare: {len(da_fare)}")
    if args.limite:
        da_fare = da_fare[:args.limite]

    fatti = 0
    t0 = time.time()
    for k in da_fare:
        # Robusto ai singhiozzi di Ollama (RemoteDisconnected, timeout, riavvii, OOM su una
        # richiesta): ritento qualche volta dando tempo al server di riprendersi. Salvo a ogni
        # tentativo, cosi' non si perde nulla; se proprio non risponde, mi fermo con grazia.
        testo = None
        for tentativo in range(3):
            try:
                testo = ollama(prompt_per(k.split(), eco_map), args.modello, args.host, args.temp)
                break
            except Exception as e:
                print(f"\n  ! Ollama non ha risposto su '{k}' (tentativo {tentativo + 1}/3): {e}", flush=True)
                salva(cache, COACH_FILE)
                time.sleep(5)
        if testo is None:
            print("Ollama continua a non rispondere: salvo e mi fermo. Controlla che Ollama sia attivo "
                  "(o usa un modello piu' leggero, es. --modello qwen3:4b) e rilancia: riprende da qui.")
            salva(cache, COACH_FILE)
            return 1
        if testo:
            cache[k] = testo
        fatti += 1
        vel = fatti / max(time.time() - t0, 0.001)
        print(f"  {fatti}/{len(da_fare)} · {k}", flush=True)  # battito: una riga per posizione
        if fatti % args.ogni == 0:
            salva(cache, COACH_FILE)
            reste = (len(da_fare) - fatti) / max(vel, 0.001) / 3600
            print(f"  --- salvato ({len(cache)} in cache) · {vel:.2f}/s · ~{reste:.1f}h rimanenti", flush=True)
    salva(cache, COACH_FILE)
    print(f"Fatto. Spiegazioni in cache: {len(cache)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
