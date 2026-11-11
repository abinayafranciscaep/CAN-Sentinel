"""
CAN-Sentinel: end-to-end evaluation of the detector's alerts.

train_model.py evaluate scores the model's windows. This tool scores what the
dashboard actually receives: the alert JSON lines. For a labelled CAN CSV it
reports, per attack (docs/week1_design.md, Section 4.3):

  - detected or not, and time to detect (first attack frame -> first alert)
  - how many alerts named the right attack type
  - how many alerts named the right CAN ID
  - false alarms: alerts outside every attack (plus a 1 s grace period)
  - precision over all alerts

Usage (from the repository root):
    python ml_engine/evaluate_alerts.py data/synthetic_all_attacks.csv
    python ml_engine/evaluate_alerts.py data/attacks_run1.csv --alerts results/run1_alerts.jsonl --md docs/results_run1.md

Without --alerts, the detector (detect.py) is run first.

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import json
import os
import tempfile

from features import load_frames

GRACE_SECONDS = 1.0  # an alert up to one window after an attack still belongs to it
BUS_WIDE = ("fuzz",)  # random IDs: no single correct suspect ID


def attack_phases(frames):
    """One entry per attack label: time span and the CAN ID it mostly used."""
    phases = []
    attacks = frames[~frames["label"].isin(["normal", "unknown"])]
    for label, rows in attacks.groupby("label"):
        phases.append({
            "attack": label,
            "start": float(rows["timestamp"].min()),
            "end": float(rows["timestamp"].max()),
            "frames": len(rows),
            "expected_id": None if label in BUS_WIDE else rows["can_id"].mode().iloc[0],
        })
    return sorted(phases, key=lambda p: p["start"])


def score(frames, alerts):
    """Return per-attack rows and overall numbers for one labelled recording."""
    phases = attack_phases(frames)
    used = set()
    rows = []
    for p in phases:
        inside = [i for i, a in enumerate(alerts)
                  if p["start"] <= a["timestamp"] <= p["end"] + GRACE_SECONDS]
        used.update(inside)
        hits = [alerts[i] for i in inside]
        right_type = sum(a["attack_type"] == p["attack"] for a in hits)
        right_id = (None if p["expected_id"] is None
                    else sum(a["suspect_id"] == p["expected_id"] for a in hits))
        rows.append({
            "attack": p["attack"],
            "detected": bool(hits),
            "time_to_detect": round(min(a["timestamp"] for a in hits) - p["start"], 2) if hits else None,
            "alerts": len(hits),
            "right_type": right_type,
            "right_id": right_id,
            "expected_id": p["expected_id"] or "random IDs",
        })

    false_alarms = [a for i, a in enumerate(alerts) if i not in used]
    duration = float(frames["timestamp"].max() - frames["timestamp"].min())
    attack_time = sum(p["end"] - p["start"] + GRACE_SECONDS for p in phases)
    normal_hours = max(duration - attack_time, 0.0) / 3600
    overall = {
        "frames": len(frames),
        "duration_s": round(duration, 1),
        "alerts": len(alerts),
        "false_alarms": len(false_alarms),
        "false_alarms_per_hour": round(len(false_alarms) / normal_hours, 1) if normal_hours else None,
        "precision": round((len(alerts) - len(false_alarms)) / len(alerts), 3) if alerts else None,
        "detected": f"{sum(r['detected'] for r in rows)}/{len(rows)}",
    }
    return rows, overall


def to_markdown(path, rows, overall):
    lines = [f"Evaluation of `{path}`", "",
             f"Frames: {overall['frames']} | Duration: {overall['duration_s']} s | "
             f"Alerts: {overall['alerts']} | Attacks detected: {overall['detected']}", "",
             "| Attack | Detected | Time to detect | Alerts | Right attack type | Right CAN ID |",
             "|---|---|---|---:|---|---|"]
    for r in rows:
        ttd = f"{r['time_to_detect']:.2f} s" if r["detected"] else "-"
        rtype = f"{r['right_type']}/{r['alerts']}" if r["alerts"] else "-"
        rid = ("n/a (random IDs)" if r["right_id"] is None
               else f"{r['right_id']}/{r['alerts']} ({r['expected_id']})" if r["alerts"] else "-")
        lines.append(f"| {r['attack']} | {'Yes' if r['detected'] else 'No'} | {ttd} | "
                     f"{r['alerts']} | {rtype} | {rid} |")
    fph = overall["false_alarms_per_hour"]
    lines += ["", f"False alarms (alerts outside every attack): {overall['false_alarms']}"
              + (f" ({fph} per hour of normal traffic)" if fph is not None else ""),
              "Precision (alerts that belong to a real attack): "
              + (str(overall["precision"]) if overall["precision"] is not None else "n/a (no alerts)")]
    return "\n".join(lines)


def read_alerts(path):
    alerts = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    alerts.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return alerts


def main():
    p = argparse.ArgumentParser(description="CAN-Sentinel alert evaluation")
    p.add_argument("input_csv", help="labelled CAN CSV")
    p.add_argument("--alerts", help="alert JSONL from detect.py (runs the detector if omitted)")
    p.add_argument("--md", help="also write the result table to this Markdown file")
    a = p.parse_args()

    alert_path = a.alerts
    if alert_path is None:
        from detect import run
        alert_path = os.path.join(tempfile.gettempdir(), "can_sentinel_eval_alerts.jsonl")
        run(a.input_csv, alert_path)
        print()

    frames = load_frames(a.input_csv)
    if frames["label"].isin(["unknown"]).all():
        print("Note: the CSV has no labels, so only the alert count is meaningful.")
    rows, overall = score(frames, read_alerts(alert_path))
    text = to_markdown(a.input_csv, rows, overall)
    print(text)
    if a.md:
        with open(a.md, "w") as f:
            f.write(text + "\n")
        print(f"\nWritten to {a.md}")


if __name__ == "__main__":
    main()
