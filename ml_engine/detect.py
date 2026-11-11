"""
CAN-Sentinel: offline detector (all three layers together).

Runs the rules layer, the statistics layer and the Isolation Forest over a
recorded CAN CSV, writes one alert JSON per line, and, if the CSV is labelled,
reports time-to-detect for each attack.

Usage (from the repository root):
    python ml_engine/detect.py data/flood_run1_1013.csv --out alerts.jsonl

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import os

import joblib
import pandas as pd

from alerts import make_alert, to_json_line
from features import load_frames, window_features
from rules import check_window
from train_model import MODEL_PATH, predict

COOLDOWN_SECONDS = 2.0  # do not repeat the same alert for the same ID within this time
MODEL_CONFIRM_WINDOWS = 2  # model-only alerts need this many abnormal windows in a row
BUS_WIDE_ATTACKS = ("flood", "fuzz")  # random/changing IDs: group alerts by attack type


def most_abnormal_id(feature_row):
    """CAN ID whose rate ratio (or longest gap) deviates most from normal."""
    best, best_dev = "bus", 0.0
    for col in feature_row.index:
        if col.endswith("_rate_ratio") and col.startswith("id_"):
            can_id = "0x" + col[3:6]
            dev = max(abs(feature_row[col] - 1.0),
                      (feature_row.get(f"id_{col[3:6]}_max_gap_ratio", 0) - 2.0) / 10)
            if dev > best_dev:
                best, best_dev = can_id, dev
    return best


class Detector:
    """Shared by the offline detector and the live detector."""

    def __init__(self, model_path=MODEL_PATH, window_len=1.0):
        self.window_len = window_len
        self.bundle = joblib.load(model_path) if os.path.exists(model_path) else None
        self.last_sent = {}
        self.model_streak = 0

    def detect_window(self, frames, window_end):
        """Return the alerts for one window of frames."""
        alerts = []
        for f in check_window(frames, self.window_len):
            alerts.append(make_alert(window_end, f["attack_type"], f["suspect_id"],
                                     f["confidence"], "rules"))

        if self.bundle is not None and not frames.empty:
            row = pd.DataFrame([window_features(frames, self.window_len)])
            pred = predict(self.bundle, row).iloc[0]
            self.model_streak = self.model_streak + 1 if pred["flagged"] else 0
            if self.model_streak >= MODEL_CONFIRM_WINDOWS and not alerts:
                # The model knows "something is wrong" but not what; name the ID
                # whose rate is furthest from its normal baseline.
                suspect = most_abnormal_id(row.iloc[0])
                confidence = min(1.0, 0.5 + abs(pred["score"]) / 2)
                alerts.append(make_alert(window_end, "unknown_anomaly", suspect,
                                         confidence, pred["detection_layer"]))
        return self._apply_cooldown(alerts, window_end)

    def _apply_cooldown(self, alerts, now):
        kept = []
        for a in alerts:
            if a["attack_type"] in BUS_WIDE_ATTACKS:
                key = (a["attack_type"], "bus")
            else:
                key = (a["attack_type"], a["suspect_id"])
            if now - self.last_sent.get(key, -1e18) >= COOLDOWN_SECONDS:
                self.last_sent[key] = now
                kept.append(a)
        return kept


def run(path, out_path, window_len=1.0, step=0.5, model_path=MODEL_PATH):
    frames = load_frames(path)
    detector = Detector(model_path, window_len)
    if detector.bundle is None:
        print(f"Note: no trained model at {model_path}; running rules layer only.")

    times = frames["timestamp"].to_numpy()
    start, end = times[0], times[-1]
    alerts = []
    t = start
    while t + window_len <= end + 1e-9:
        lo, hi = times.searchsorted(t), times.searchsorted(t + window_len)
        alerts.extend(detector.detect_window(frames.iloc[lo:hi], t + window_len))
        t += step

    with open(out_path, "w") as f:
        for a in alerts:
            f.write(to_json_line(a) + "\n")
    print(f"{len(frames)} frames, {len(alerts)} alerts written to {out_path}")
    report_time_to_detect(frames, alerts)
    return alerts


def report_time_to_detect(frames, alerts):
    """For each labelled attack: seconds from its first frame to the first alert after it."""
    attacks = frames[~frames["label"].isin(["normal", "unknown"])]
    if attacks.empty:
        return
    print("Time to detect:")
    for attack, rows in attacks.groupby("label"):
        first, last = rows["timestamp"].min(), rows["timestamp"].max()
        # Only alerts raised while the attack is running (plus one window) count.
        later = [a["timestamp"] for a in alerts if first <= a["timestamp"] <= last + 1.0]
        if later:
            print(f"  {attack}: {min(later) - first:.2f} s")
        else:
            print(f"  {attack}: not detected")


def main():
    p = argparse.ArgumentParser(description="CAN-Sentinel offline detector")
    p.add_argument("input_csv")
    p.add_argument("--out", default="alerts.jsonl")
    p.add_argument("--window", type=float, default=1.0)
    p.add_argument("--step", type=float, default=0.5)
    p.add_argument("--model", default=MODEL_PATH)
    a = p.parse_args()
    run(a.input_csv, a.out, a.window, a.step, a.model)


if __name__ == "__main__":
    main()
