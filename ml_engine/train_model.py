"""
CAN-Sentinel: train and evaluate the Isolation Forest.

Step 1 (train): learn what normal CAN traffic looks like from feature files
made by features.py. Only normal windows are used for training.

Two layers run together: a statistics layer (feature outside its normal
range) and the Isolation Forest (unusual combination of features).

Step 2 (evaluate): score a labelled test feature file and report, per attack,
how many windows were caught (recall), plus overall precision and the false
positive rate on normal traffic.

Usage:
    python train_model.py train data/features_normal_run1.csv data/features_normal_run2.csv
    python train_model.py evaluate data/features_attacks.csv

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import json
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

MODEL_PATH = "ml_engine/isolation_forest.joblib"
NON_FEATURE_COLUMNS = {"window_start", "label"}
# Normal windows scoring below this percentile of the training scores are flagged.
# 1.0 means about 1% of normal windows would be false alarms; tune in Week 3.
THRESHOLD_PERCENTILE = 1.0
# A feature more than this fraction of its normal range outside that range is flagged.
RANGE_MARGIN = 0.5


def feature_columns(df):
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def train(paths, model_path=MODEL_PATH, seed=42):
    frames = [pd.read_csv(p) for p in paths]
    data = pd.concat(frames, ignore_index=True)
    if "label" in data.columns:
        data = data[data["label"] == "normal"]
    if data.empty:
        sys.exit("No normal windows found to train on.")

    columns = feature_columns(data)
    scaler = StandardScaler().fit(data[columns])
    X = scaler.transform(data[columns])

    model = IsolationForest(n_estimators=200, contamination="auto", random_state=seed)
    model.fit(X)

    # Lower score = more anomalous. The threshold is set from normal traffic only.
    scores = model.score_samples(X)
    threshold = float(np.percentile(scores, THRESHOLD_PERCENTILE))

    # Statistics layer: the normal range of every feature, with a safety margin.
    # Isolation Forest is weak on values far outside anything seen in training
    # (e.g. a flood's 7x bus rate), so these bounds catch them directly.
    lo, hi = data[columns].min(), data[columns].max()
    margin = (hi - lo) * RANGE_MARGIN + 1e-9
    bounds = {"low": (lo - margin).to_dict(), "high": (hi + margin).to_dict()}

    joblib.dump({"model": model, "scaler": scaler, "columns": columns,
                 "threshold": threshold, "bounds": bounds}, model_path)
    print(f"Trained on {len(data)} normal windows, {len(columns)} features.")
    print(f"Anomaly threshold (score): {threshold:.4f}")
    print(f"Model saved to {model_path}")


def predict(bundle, data):
    """Flag windows with the statistics layer and the Isolation Forest.

    Returns a DataFrame with: stats_flag, iforest_flag, flagged, score,
    detection_layer (statistics / isolation_forest / none).
    """
    cols = bundle["columns"]
    low = pd.Series(bundle["bounds"]["low"])[cols]
    high = pd.Series(bundle["bounds"]["high"])[cols]
    values = data[cols]
    stats_flag = ((values < low) | (values > high)).any(axis=1).to_numpy()

    X = bundle["scaler"].transform(values)
    scores = bundle["model"].score_samples(X)
    iforest_flag = scores < bundle["threshold"]

    layer = np.where(stats_flag, "statistics", np.where(iforest_flag, "isolation_forest", "none"))
    return pd.DataFrame({"stats_flag": stats_flag, "iforest_flag": iforest_flag,
                         "flagged": stats_flag | iforest_flag, "score": scores,
                         "detection_layer": layer}, index=data.index)


def evaluate(path, model_path=MODEL_PATH):
    bundle = joblib.load(model_path)
    data = pd.read_csv(path)
    if "label" not in data.columns:
        sys.exit("Test file needs a 'label' column to evaluate.")

    pred = predict(bundle, data)
    data = data.join(pred)
    flagged = data["flagged"].to_numpy()
    is_attack = (data["label"] != "normal").to_numpy()

    tp = int((flagged & is_attack).sum())
    fp = int((flagged & ~is_attack).sum())
    normal_total = int((~is_attack).sum())

    results = {
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "false_positive_rate": round(fp / normal_total, 3) if normal_total else None,
        "recall_per_attack": {},
        "caught_by_layer": {},
    }
    for attack in sorted(data.loc[is_attack, "label"].unique()):
        rows = data[data["label"] == attack]
        results["recall_per_attack"][attack] = round(float(rows["flagged"].mean()), 3)
        results["caught_by_layer"][attack] = {
            "statistics": int(rows["stats_flag"].sum()),
            "isolation_forest": int(rows["iforest_flag"].sum()),
            "windows": len(rows),
        }

    print(json.dumps(results, indent=2))
    return results


def main():
    parser = argparse.ArgumentParser(description="CAN-Sentinel Isolation Forest")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("train", help="Train on normal feature files")
    t.add_argument("feature_csvs", nargs="+")
    t.add_argument("--model", default=MODEL_PATH)
    e = sub.add_parser("evaluate", help="Evaluate on a labelled feature file")
    e.add_argument("feature_csv")
    e.add_argument("--model", default=MODEL_PATH)
    args = parser.parse_args()

    if args.command == "train":
        train(args.feature_csvs, args.model)
    else:
        evaluate(args.feature_csv, args.model)


if __name__ == "__main__":
    main()
