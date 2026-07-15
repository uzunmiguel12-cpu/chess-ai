"""
Allena il MODELLO POSIZIONALE (Fase 3 — Sparring): predice il costo posizionale
di una mossa dalle sole feature, senza engine.

Input:  uno o PIU' CSV (ml/dataset_posizionale.py e/o ml/dataset_lichess.py,
        colonne identiche — si concatenano).
Output: data/modello_posizionale.joblib con dentro:
        - "modello": classificatore di RISCHIO (errore posizionale >=100cp),
          e' quello che il pannello Sparring mostra come probabilita' [STIMA];
        - "regressore": perdita stimata in cp (facoltativo);
        - "colonne", "clip", "auc_test", "mae_test".

Scelte oneste:
  - solo mosse NON tattiche (la tattica la copre gia' Stockfish);
  - target cp_loss clippato a 300;
  - split train/test PER PARTITA (GroupShuffleSplit): il MAE/AUC riportato
    e' un [DATO], non gonfiato da mosse della stessa partita nei due lati;
  - baseline dichiarata: il modello vale solo se la batte.

Uso:
    python allena_posizionale.py
    python allena_posizionale.py --csv ../data/dataset_posizionale.csv ../data/dataset_lichess.csv
"""

import argparse
import os

import joblib
import pandas as pd
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

_QUI = os.path.dirname(os.path.abspath(__file__))
CSV_DEFAULT = os.path.join(_QUI, "..", "data", "dataset_posizionale.csv")
MODELLO_DEFAULT = os.path.join(_QUI, "..", "data", "modello_posizionale.joblib")

CLIP_TARGET = 300


def carica(percorsi_csv):
    pezzi = []
    for p in percorsi_csv:
        df = pd.read_csv(p)
        print(f"  {p}: {len(df)} mosse, {df['partita'].nunique()} partite")
        pezzi.append(df)
    df = pd.concat(pezzi, ignore_index=True)
    df = df[df["tattica"] == 0].copy()
    df["y"] = df["cp_loss"].clip(0, CLIP_TARGET)
    colonne = [c for c in df.columns if c.startswith(("pre_", "d_"))]
    colonne += ["eval_prima", "muove_bianco"]
    return df, colonne


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="+", default=[CSV_DEFAULT],
                    help="uno o piu' CSV con le stesse colonne")
    ap.add_argument("--out", default=MODELLO_DEFAULT)
    args = ap.parse_args()

    df, colonne = carica(args.csv)
    print(f"Totale: {len(df)} mosse non tattiche da {df['partita'].nunique()} partite, "
          f"{len(colonne)} feature")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    idx_train, idx_test = next(gss.split(df, groups=df["partita"]))
    tr, te = df.iloc[idx_train], df.iloc[idx_test]

    regressore = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.08, max_depth=6,
        l2_regularization=1.0, random_state=42,
    )
    regressore.fit(tr[colonne], tr["y"])
    pred = regressore.predict(te[colonne])
    mae = mean_absolute_error(te["y"], pred)
    baseline = mean_absolute_error(te["y"], [tr["y"].mean()] * len(te))
    print(f"[DATO] MAE regressore: {mae:.2f} cp | baseline (media): {baseline:.2f} cp")

    df["errore"] = (df["cp_loss"] >= 100).astype(int)
    tr, te = df.iloc[idx_train], df.iloc[idx_test]
    classificatore = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.08, max_depth=6, random_state=42,
    )
    classificatore.fit(tr[colonne], tr["errore"])
    proba = classificatore.predict_proba(te[colonne])[:, 1]
    auc = roc_auc_score(te["errore"], proba)
    print(f"[DATO] AUC classificatore rischio (errore >=100cp): {auc:.4f}")

    imp = permutation_importance(classificatore, te[colonne].iloc[:8000],
                                 te["errore"].iloc[:8000],
                                 n_repeats=3, random_state=42, scoring="roc_auc")
    classifica = sorted(zip(colonne, imp.importances_mean), key=lambda x: -x[1])[:12]
    print("\nFeature piu' importanti (permutation importance, AUC, sul test):")
    for nome, val in classifica:
        print(f"  {nome:28s} {val:+.4f}")

    joblib.dump({
        "modello": classificatore,
        "regressore": regressore,
        "colonne": colonne,
        "clip": CLIP_TARGET,
        "auc_test": round(auc, 3),
        "mae_test": round(mae, 1),
    }, args.out)
    print(f"\nModello salvato in {args.out}")


if __name__ == "__main__":
    main()
