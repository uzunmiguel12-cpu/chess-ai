"""
Curva di SCALING del modello posizionale: quanto migliora l'AUC aggiungendo dati?

Decide se conviene: (a) aggiungere altri mesi di dump Lichess, oppure (b) passare
a S3 (rete neurale). Misura-prima-della-soluzione:

  - test set FISSO: 20% delle partite (split per partita, seed 42), sempre lo stesso;
  - si allena lo STESSO classificatore (stessi iperparametri di allena_posizionale.py)
    su frazioni crescenti delle partite di train: 10%, 25%, 50%, 100%;
  - si stampa la tabella AUC (e MAE del regressore) per frazione.

LETTURA DEL RISULTATO [DATO]:
  - AUC ancora in crescita al 100%  -> il volume paga: aggiungere mesi di dump
    (dataset_lichess.py --append) prima di investire in S3;
  - AUC piatta tra 50% e 100%       -> plateau: piu' dati uguali non servono,
    serve un modello/input migliore (S3) o feature nuove.

Uso (dal PC, ~10-15 minuti):
    python curva_scaling.py --csv ..\\data\\dataset_posizionale.csv ..\\data\\dataset_lichess.csv
"""

import argparse
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import (HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor)
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

CLIP_TARGET = 300
FRAZIONI = (0.10, 0.25, 0.50, 1.00)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", nargs="+", required=True)
    ap.add_argument("--frazioni", nargs="+", type=float, default=list(FRAZIONI))
    args = ap.parse_args()

    df = pd.concat([pd.read_csv(p) for p in args.csv], ignore_index=True)
    df = df[df["tattica"] == 0].copy()
    df["y"] = df["cp_loss"].clip(0, CLIP_TARGET)
    df["errore"] = (df["cp_loss"] >= 100).astype(int)
    colonne = [c for c in df.columns if c.startswith(("pre_", "d_"))]
    colonne += ["eval_prima", "muove_bianco"]
    print(f"Totale: {len(df)} mosse non tattiche, {df['partita'].nunique()} partite, "
          f"{len(colonne)} feature\n")

    # test set FISSO (stesso seed di allena_posizionale.py)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    idx_train, idx_test = next(gss.split(df, groups=df["partita"]))
    train, test = df.iloc[idx_train], df.iloc[idx_test]
    partite_train = train["partita"].unique()
    rng = np.random.default_rng(42)
    partite_mescolate = rng.permutation(partite_train)
    print(f"Test fisso: {len(test)} mosse da {test['partita'].nunique()} partite\n")
    print(f"{'frazione':>9} {'partite':>9} {'mosse':>10} {'AUC':>8} {'MAE':>8} {'tempo':>7}")

    risultati = []
    for fr in sorted(args.frazioni):
        scelte = set(partite_mescolate[:max(1, int(len(partite_mescolate) * fr))])
        tr = train[train["partita"].isin(scelte)]
        t0 = time.time()
        clf = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.08, max_depth=6, random_state=42)
        clf.fit(tr[colonne], tr["errore"])
        auc = roc_auc_score(test["errore"], clf.predict_proba(test[colonne])[:, 1])
        reg = HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.08, max_depth=6,
            l2_regularization=1.0, random_state=42)
        reg.fit(tr[colonne], tr["y"])
        mae = mean_absolute_error(test["y"], reg.predict(test[colonne]))
        dt = time.time() - t0
        print(f"{fr:>9.0%} {len(scelte):>9} {len(tr):>10} {auc:>8.4f} {mae:>8.2f} {dt:>6.0f}s",
              flush=True)
        risultati.append((fr, auc))

    # verdetto automatico [DATO]: pendenza dell'ultimo tratto vs il precedente
    if len(risultati) >= 3:
        (f1, a1), (f2, a2), (f3, a3) = risultati[-3], risultati[-2], risultati[-1]
        ultimo = (a3 - a2) / max(1e-9, (f3 - f2))
        prima = (a2 - a1) / max(1e-9, (f2 - f1))
        print("\nPendenza AUC ultimo tratto: "
              f"{ultimo:+.4f} per unita' di frazione (tratto prima: {prima:+.4f})")
        if a3 - a2 >= 0.003:
            print("VERDETTO [DATO]: curva ancora in crescita -> aggiungere mesi di "
                  "dump (dataset_lichess.py --append) conviene ancora.")
        else:
            print("VERDETTO [DATO]: curva quasi piatta -> il volume 'uguale' rende "
                  "poco; la prossima leva e' S3 (input piu' ricco) o nuove feature.")


if __name__ == "__main__":
    main()
