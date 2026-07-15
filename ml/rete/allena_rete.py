"""
S3 — Training della rete posizionale.

Input: CSV di ml/rete/estrai_posizioni.py (partita, fen, mossa, cp_loss,
tattica, eval_prima). Solo mosse non tattiche; target: errore (cp_loss >= 100).
Split train/val PER PARTITA (stesso principio di allena_posizionale.py).

Confronto onesto: l'AUC di riferimento del GBM e' scritta in
data/modello_posizionale.joblib (chiave "auc_test"); la rete deve batterla
per guadagnarsi la produzione.

Uso (PC; GPU consigliata ma funziona anche su CPU con --canali 64 --blocchi 6):
    python estrai_posizioni.py --analisi --out ../../data/posizioni_personali.csv
    python estrai_posizioni.py --url <dump> --max-partite 30000 --out ../../data/posizioni_lichess.csv
    python allena_rete.py --dati ../../data/posizioni_personali.csv ../../data/posizioni_lichess.csv

Output: data/rete_posizionale.pt (pesi migliori su val + iperparametri).

Nota Windows: la classe del dataset e' a livello di modulo (richiesto dal
multiprocessing "spawn"); --workers di default 0 su Windows, alzalo su Linux.
"""

import argparse
import os
import sys
import time

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader

_QUI = os.path.dirname(os.path.abspath(__file__))
if _QUI not in sys.path:
    sys.path.insert(0, _QUI)

from tensori import codifica, normalizza_eval          # noqa: E402

USCITA_DEFAULT = os.path.join(_QUI, "..", "..", "data", "rete_posizionale.pt")


class DatasetPosizioni(Dataset):
    """(piani 24x8x8, eval scalare, target). Codifica al volo dalle FEN."""

    def __init__(self, df):
        self.fen = df["fen"].tolist()
        self.mossa = df["mossa"].tolist()
        self.ev = df["eval_prima"].to_numpy(np.float32)
        self.y = df["y"].to_numpy(np.float32)

    def __len__(self):
        return len(self.fen)

    def __getitem__(self, i):
        piani = codifica(self.fen[i], self.mossa[i])
        return (torch.from_numpy(piani),
                torch.tensor([normalizza_eval(self.ev[i])]),
                torch.tensor([self.y[i]]))


def carica_dati(percorsi, max_righe=0):
    df = pd.concat([pd.read_csv(p) for p in percorsi], ignore_index=True)
    df = df[df["tattica"] == 0].copy()
    df["y"] = (df["cp_loss"] >= 100).astype(np.float32)
    if max_righe and len(df) > max_righe:
        df = df.sample(max_righe, random_state=42)
    # split per partita (deterministico)
    partite = df["partita"].unique()
    rng = np.random.default_rng(42)
    val_set = set(rng.permutation(partite)[: max(1, len(partite) // 5)])
    df["val"] = df["partita"].isin(val_set)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dati", nargs="+", required=True)
    ap.add_argument("--out", default=USCITA_DEFAULT)
    ap.add_argument("--epoche", type=int, default=8)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--canali", type=int, default=128)
    ap.add_argument("--blocchi", type=int, default=10)
    ap.add_argument("--max-righe", type=int, default=0, help="0 = tutte")
    ap.add_argument("--workers", type=int, default=0 if os.name == "nt" else 2)
    ap.add_argument("--riprendi", default=None,
                    help="checkpoint .pt da cui continuare (canali/blocchi presi da li'; "
                         "consigliato abbinare un --lr piu' basso, es. 3e-4)")
    args = ap.parse_args()

    from sklearn.metrics import roc_auc_score
    from modello import RetePosizionale, conta_parametri

    df = carica_dati(args.dati, args.max_righe)
    tr, va = df[~df["val"]], df[df["val"]]
    print(f"Train: {len(tr)} mosse ({tr['partita'].nunique()} partite) | "
          f"Val: {len(va)} mosse ({va['partita'].nunique()} partite)")

    dispositivo = "cuda" if torch.cuda.is_available() else "cpu"
    if args.riprendi:
        ckpt = torch.load(args.riprendi, map_location="cpu")
        args.canali, args.blocchi = ckpt["canali"], ckpt["blocchi"]
        rete = RetePosizionale(args.canali, args.blocchi)
        rete.load_state_dict(ckpt["stato"])
        rete = rete.to(dispositivo)
        print(f"Riprendo da {args.riprendi} (AUC val registrata: {ckpt.get('auc_val')})")
    else:
        rete = RetePosizionale(args.canali, args.blocchi).to(dispositivo)
    print(f"Rete: {args.canali}x{args.blocchi} = "
          f"{conta_parametri(rete)/1e6:.2f}M parametri su {dispositivo}")

    dl_tr = DataLoader(DatasetPosizioni(tr), batch_size=args.batch, shuffle=True,
                       num_workers=args.workers, pin_memory=(dispositivo == "cuda"))
    dl_va = DataLoader(DatasetPosizioni(va), batch_size=args.batch * 2,
                       num_workers=args.workers)

    ottim = torch.optim.AdamW(rete.parameters(), lr=args.lr, weight_decay=1e-4)
    perdita = torch.nn.BCEWithLogitsLoss()
    migliore = 0.0

    for epoca in range(1, args.epoche + 1):
        rete.train()
        t0, tot = time.time(), 0.0
        for piani, ev, y in dl_tr:
            piani, ev, y = piani.to(dispositivo), ev.to(dispositivo), y.to(dispositivo)
            ottim.zero_grad()
            loss = perdita(rete(piani, ev), y)
            loss.backward()
            ottim.step()
            tot += loss.item() * len(y)

        rete.eval()
        probs, veri = [], []
        with torch.no_grad():
            for piani, ev, y in dl_va:
                logit = rete(piani.to(dispositivo), ev.to(dispositivo))
                probs.append(torch.sigmoid(logit).cpu().numpy())
                veri.append(y.numpy())
        auc = roc_auc_score(np.concatenate(veri), np.concatenate(probs))
        print(f"epoca {epoca:2d} | loss {tot/len(tr):.4f} | AUC val {auc:.4f} "
              f"| {time.time()-t0:.0f}s", flush=True)
        if auc > migliore:
            migliore = auc
            torch.save({"stato": rete.state_dict(), "canali": args.canali,
                        "blocchi": args.blocchi, "auc_val": round(auc, 4)}, args.out)

    print(f"\n[DATO] Migliore AUC val: {migliore:.4f} -> {args.out}")
    print("Confronto: il GBM in produzione ha AUC test ~0.698 (vedi "
          "data/modello_posizionale.joblib['auc_test']). La rete va promossa "
          "solo se lo batte nettamente su un confronto a parita' di split.")


if __name__ == "__main__":
    main()
