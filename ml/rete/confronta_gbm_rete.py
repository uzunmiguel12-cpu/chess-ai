"""
S3 — Confronto ONESTO GBM vs rete, a parita' di partite.

La rete e il GBM in produzione sono stati valutati su split diversi (stessa
logica, seed diversi): i loro AUC non sono direttamente confrontabili. Questo
script produce il [DATO] pulito per la decisione di promozione:

  1. ricostruisce ESATTAMENTE lo split train/val della rete (stesso codice e
     seed di allena_rete.py, dai CSV delle posizioni);
  2. riallena il GBM (stessi iperparametri di allena_posizionale.py) sui CSV
     delle FEATURE, filtrati sulle STESSE partite di train della rete;
  3. valuta il GBM sulle STESSE partite di validazione della rete;
  4. stampa GBM vs rete (l'AUC della rete e' letta da data/rete_posizionale.pt).

Prerequisito: le partite nei CSV feature e nei CSV posizioni hanno gli stessi
id (stesse fonti: data/analisi + dump Lichess).

Uso:
    python confronta_gbm_rete.py ^
        --posizioni ..\\..\\data\\posizioni_personali.csv ..\\..\\data\\posizioni_lichess.csv ^
        --feature ..\\..\\data\\dataset_posizionale.csv ..\\..\\data\\dataset_lichess.csv
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

_QUI = os.path.dirname(os.path.abspath(__file__))
if _QUI not in sys.path:
    sys.path.insert(0, _QUI)

RETE_PT = os.path.join(_QUI, "..", "..", "data", "rete_posizionale.pt")


def split_della_rete(percorsi_posizioni, max_righe=0):
    """Ricostruisce lo split di allena_rete.carica_dati (stesso codice, seed 42)."""
    df = pd.concat([pd.read_csv(p) for p in percorsi_posizioni], ignore_index=True)
    df = df[df["tattica"] == 0].copy()
    if max_righe and len(df) > max_righe:
        df = df.sample(max_righe, random_state=42)
    partite = df["partita"].unique()
    rng = np.random.default_rng(42)
    val = set(rng.permutation(partite)[: max(1, len(partite) // 5)])
    train = set(partite) - val
    return train, val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posizioni", nargs="+", required=True)
    ap.add_argument("--feature", nargs="+", required=True)
    ap.add_argument("--max-righe", type=int, default=0,
                    help="deve combaciare col --max-righe usato in allena_rete.py (0 = tutte)")
    args = ap.parse_args()

    partite_train, partite_val = split_della_rete(args.posizioni, args.max_righe)
    print(f"Split della rete: {len(partite_train)} partite train, "
          f"{len(partite_val)} partite val")

    df = pd.concat([pd.read_csv(p) for p in args.feature], ignore_index=True)
    df = df[df["tattica"] == 0].copy()
    df["errore"] = (df["cp_loss"] >= 100).astype(int)
    colonne = [c for c in df.columns if c.startswith(("pre_", "d_"))]
    colonne += ["eval_prima", "muove_bianco"]

    tr = df[df["partita"].isin(partite_train)]
    va = df[df["partita"].isin(partite_val)]
    fuori = df[~df["partita"].isin(partite_train | partite_val)]
    print(f"Feature: {len(tr)} mosse train, {len(va)} mosse val "
          f"({len(fuori)} mosse di partite non presenti nei CSV posizioni: escluse)")

    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.08, max_depth=6, random_state=42)
    gbm.fit(tr[colonne], tr["errore"])
    auc_gbm = roc_auc_score(va["errore"], gbm.predict_proba(va[colonne])[:, 1])

    auc_rete = None
    try:
        import torch
        ckpt = torch.load(RETE_PT, map_location="cpu", weights_only=False)
        auc_rete = ckpt.get("auc_val")
    except Exception as e:
        print(f"(non ho potuto leggere l'AUC della rete da {RETE_PT}: {e})")

    print(f"\n[DATO] AUC GBM  (stesso split della rete): {auc_gbm:.4f}")
    if auc_rete is not None:
        print(f"[DATO] AUC RETE (da rete_posizionale.pt):  {auc_rete:.4f}")
        diff = auc_rete - auc_gbm
        print(f"[DATO] Differenza: {diff:+.4f}")
        if diff >= 0.005:
            print("VERDETTO: la rete batte il GBM in modo netto -> promozione motivata.")
        elif diff > 0:
            print("VERDETTO: vantaggio marginale -> decidere se il costo (torch in "
                  "produzione, latenza) vale il guadagno.")
        else:
            print("VERDETTO: la rete NON batte il GBM -> resta il GBM (e lo si dichiara).")


if __name__ == "__main__":
    main()
