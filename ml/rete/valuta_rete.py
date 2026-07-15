"""
S3 — Valuta uno o piu' checkpoint della rete sullo STESSO set di validazione.

Serve quando si riallena con piu' dati o rete piu' grande: lo split cambia con
il dataset, quindi l'AUC salvata nel vecchio .pt non e' confrontabile con quella
del nuovo run. Questo script ricostruisce lo split di validazione dai CSV
attuali (stesso codice/seed di allena_rete.py) e misura TUTTI i checkpoint
indicati su quelle stesse mosse: confronto pulito [DATO].

ATTENZIONE — CONTAMINAZIONE (lezione imparata [DATO], luglio 2026): se i CSV
contengono partite usate nel training di UNO dei checkpoint, il suo AUC esce
gonfiato (ha gia' visto quelle partite). Ricostruire lo split qui NON basta
quando il dataset e' cambiato tra i due training (la permutazione cambia e le
partite si mescolano). Il confronto pulito tra reti allenate su dataset diversi
si fa SOLO su un mese di dump mai visto da nessuna delle due, con --tutte:

    python estrai_posizioni.py --url <dump di un mese NUOVO> --max-partite 5000 --out ..\\..\\data\\posizioni_test.csv
    python valuta_rete.py --dati ..\\..\\data\\posizioni_test.csv --tutte --reti <vecchia.pt> <nuova.pt>

Uso classico (stesso dataset del training, valuta solo il 20% di validazione):
    python valuta_rete.py --dati <csv del training> --reti <rete.pt>

Promozione manuale: se la nuova vince, copiala su data/rete_posizionale.pt
(il backend carica quel percorso).
"""

import argparse
import os
import sys

import numpy as np
import torch
from torch.utils.data import DataLoader
from sklearn.metrics import roc_auc_score

_QUI = os.path.dirname(os.path.abspath(__file__))
if _QUI not in sys.path:
    sys.path.insert(0, _QUI)

from allena_rete import carica_dati, DatasetPosizioni      # noqa: E402
from modello import RetePosizionale, conta_parametri       # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dati", nargs="+", required=True)
    ap.add_argument("--reti", nargs="+", required=True, help="uno o piu' file .pt")
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--max-righe", type=int, default=0)
    ap.add_argument("--tutte", action="store_true",
                    help="valuta su TUTTE le righe dei CSV (per un test set "
                         "neutrale mai visto in training), non solo sul 20%% val")
    args = ap.parse_args()

    df = carica_dati(args.dati, args.max_righe)
    va = df if args.tutte else df[df["val"]]
    etichetta = "Test neutrale (tutte le righe)" if args.tutte else "Validazione (20%)"
    print(f"{etichetta}: {len(va)} mosse da {va['partita'].nunique()} partite\n")
    dl = DataLoader(DatasetPosizioni(va), batch_size=args.batch,
                    num_workers=0 if os.name == "nt" else 2)

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    for percorso in args.reti:
        ckpt = torch.load(percorso, map_location="cpu")
        rete = RetePosizionale(ckpt["canali"], ckpt["blocchi"])
        rete.load_state_dict(ckpt["stato"])
        rete.to(dispositivo).eval()
        probs, veri = [], []
        with torch.no_grad():
            for piani, ev, y in dl:
                logit = rete(piani.to(dispositivo), ev.to(dispositivo))
                probs.append(torch.sigmoid(logit).cpu().numpy())
                veri.append(y.numpy())
        auc = roc_auc_score(np.concatenate(veri), np.concatenate(probs))
        print(f"[DATO] {os.path.basename(percorso):32s} "
              f"{ckpt['canali']}x{ckpt['blocchi']} "
              f"({conta_parametri(rete)/1e6:.1f}M)  AUC = {auc:.4f}")


if __name__ == "__main__":
    main()
