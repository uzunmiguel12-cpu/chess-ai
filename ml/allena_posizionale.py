"""
Allena il MODELLO POSIZIONALE (Fase 3 — Sparring): regressione che predice la
perdita in centipawn di una mossa a partire dalle sole feature posizionali.

Input:  data/dataset_posizionale.csv (da ml/dataset_posizionale.py)
Output: data/modello_posizionale.joblib  (modello + lista feature)

Scelte oneste:
  - solo mosse NON tattiche (la tattica la copre gia' Stockfish);
  - target cp_loss clippato a 300 (oltre, e' quasi sempre tattica sfuggita al filtro);
  - split train/test PER PARTITA (GroupShuffleSplit): mai mosse della stessa
    partita in entrambi i lati -> il MAE riportato e' un [DATO], non gonfiato;
  - baseline dichiarata (predire sempre la media): il modello vale solo se la batte.

Uso:
    python allena_posizionale.py
    python allena_posizionale.py --csv ../data/dataset_posizionale.csv
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


def carica(percorso_csv):
    df = pd.read_csv(percorso_csv)
    df = df[df["tattica"] == 0].copy()
    df["y"] = df["cp_loss"].clip(0, CLIP_TARGET)
    colonne = [c for c in df.columns if c.startswith(("pre_", "d_"))]
    colonne += ["eval_prima", "muove_bianco"]
    return df, colonne


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=CSV_DEFAULT)
    ap.add_argument("--out", default=MODELLO_DEFAULT)
    args = ap.parse_args()

    df, colonne = carica(args.csv)
    print(f"Dataset: {len(df)} mosse non tattiche da {df['partita'].nunique()} partite, "
          f"{len(colonne)} feature")

    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    idx_train, idx_test = next(gss.split(df, groups=df["partita"]))
    tr, te = df.iloc[idx_train], df.iloc[idx_test]

    modello = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.08, max_depth=6,
        l2_regularization=1.0, random_state=42,
    )
    modello.fit(tr[colonne], tr["y"])

    pred = modello.predict(te[colonne])
    mae = mean_absolute_error(te["y"], pred)
    baseline = mean_absolute_error(te["y"], [tr["y"].mean()] * len(te))
    print(f"[DATO] MAE modello:  {mae:.1f} cp")
    print(f"[DATO] MAE baseline: {baseline:.1f} cp (predire sempre la media)")

    imp = permutation_importance(modello, te[colonne].iloc[:5000], te["y"].iloc[:5000],
                                 n_repeats=3, random_state=42)
    classifica = sorted(zip(colonne, imp.importances_mean), key=lambda x: -x[1])[:15]
    print("\nFeature piu' importanti (permutation importance sul test):")
    for nome, val in classifica:
        print(f"  {nome:28s} {val:.3f}")

    # --- classificatore di RISCHIO (errore posizionale >= 100 cp): e' quello
    # che il pannello Sparring mostra come probabilita' [STIMA].
    df["errore"] = (df["cp_loss"] >= 100).astype(int)
    tr, te = df.iloc[idx_train], df.iloc[idx_test]
    classificatore = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.08, max_depth=6, random_state=42,
    )
    classificatore.fit(tr[colonne], tr["errore"])
    proba = classificatore.predict_proba(te[colonne])[:, 1]
    auc = roc_auc_score(te["errore"], proba)
    print(f"\n[DATO] AUC classificatore rischio (errore >=100cp): {auc:.3f} "
          f"(0.5 = caso, 1.0 = perfetto)")

    joblib.dump({
        "modello": classificatore,          # usato dal pannello (predict_proba)
        "regressore": modello,              # perdita stimata in cp (facoltativo)
        "colonne": colonne,
        "clip": CLIP_TARGET,
        "auc_test": round(auc, 3),
        "mae_test": round(mae, 1),
    }, args.out)
    print(f"\nModello salvato in {args.out}")


if __name__ == "__main__":
    main()
