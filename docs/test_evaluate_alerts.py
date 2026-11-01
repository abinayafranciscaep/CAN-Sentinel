"""
CAN-Sentinel: unit tests for evaluate_alerts.py.

Run from the repository root:
    python -m pytest ml_engine -q

Author: Abinaya Francisca EP (Team Lead)
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate_alerts import attack_phases, score  # noqa: E402


def frames():
    rows = [{"timestamp": t / 10, "can_id": "0x100", "label": "normal"} for t in range(0, 300)]
    rows += [{"timestamp": 10 + t / 50, "can_id": "0x0A0", "label": "spoof_brake"} for t in range(250)]
    rows += [{"timestamp": 20 + t / 100, "can_id": f"0x{0x400 + t:03X}", "label": "fuzz"} for t in range(200)]
    return pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)


def alert(t, kind, can_id):
    return {"timestamp": t, "attack_type": kind, "suspect_id": can_id}


def test_phases_found_with_expected_id():
    phases = attack_phases(frames())
    assert [p["attack"] for p in phases] == ["spoof_brake", "fuzz"]
    assert phases[0]["expected_id"] == "0x0A0"
    assert phases[1]["expected_id"] is None  # fuzz uses random IDs


def test_score_counts_detection_and_false_alarms():
    alerts = [alert(10.5, "spoof_brake", "0x0A0"), alert(12.0, "unknown_anomaly", "0x200"),
              alert(20.5, "fuzz", "0x401"), alert(5.0, "flood", "0x000")]
    rows, overall = score(frames(), alerts)
    spoof = rows[0]
    assert spoof["detected"] and spoof["time_to_detect"] == 0.5
    assert (spoof["alerts"], spoof["right_type"], spoof["right_id"]) == (2, 1, 1)
    assert rows[1]["right_id"] is None
    assert overall["false_alarms"] == 1
    assert overall["precision"] == 0.75


def test_missed_attack_reported():
    rows, overall = score(frames(), [])
    assert not rows[0]["detected"] and rows[0]["time_to_detect"] is None
    assert overall["detected"] == "0/2"
