"""
CAN-Sentinel: unit tests for features.py.

Run from the repository root:
    pip install pytest
    python -m pytest ml_engine -q

Author: Abinaya Francisca EP (Team Lead)
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from features import (extract_features, normalise_id, payload_entropy,  # noqa: E402
                      shannon_entropy, window_label)

PERIODS = {"0x0A0": 0.020, "0x0B0": 0.010, "0x100": 0.010,
           "0x200": 0.020, "0x300": 0.100, "0x600": 0.100}


def normal_frames(seconds=3.0, start=1000.0):
    rows = []
    for can_id, period in PERIODS.items():
        t = start
        while t < start + seconds:
            rows.append({"timestamp": t, "can_id": can_id, "dlc": 8,
                         "data_hex": "3201000000000017", "label": "normal"})
            t += period
    return rows


def prepare(rows):
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df["payload_entropy"] = df["data_hex"].map(payload_entropy)
    df["dlc_mismatch"] = (df["data_hex"].str.len() != df["dlc"] * 2).astype(int)
    df["is_unknown_id"] = (~df["can_id"].isin(PERIODS.keys() | {"0x7DF"})).astype(int)
    return df


def test_normalise_id_formats():
    assert normalise_id("0a0") == "0x0A0"
    assert normalise_id("0x0a0") == "0x0A0"
    assert normalise_id("7DF") == "0x7DF"


def test_entropy_values():
    assert shannon_entropy([]) == 0.0
    assert shannon_entropy(["a", "a", "a"]) == 0.0
    assert abs(shannon_entropy(["a", "b"]) - 1.0) < 1e-9
    assert payload_entropy("0000000000000000") == 0.0
    assert payload_entropy("0011223344556677") == 3.0  # 8 different bytes


def test_normal_traffic_rates():
    features = extract_features(prepare(normal_frames()), window_len=1.0, step=1.0)
    assert len(features) >= 2
    first = features.iloc[0]
    assert 300 <= first["bus_rate_fps"] <= 340      # about 320 fps baseline
    assert 0.9 <= first["id_0A0_rate_ratio"] <= 1.1  # brake at its normal rate
    assert first["unknown_id_count"] == 0
    assert first["label"] == "normal"


def test_spoofing_doubles_brake_rate():
    rows = normal_frames()
    t = 1000.0
    while t < 1003.0:
        rows.append({"timestamp": t + 0.01, "can_id": "0x0A0", "dlc": 8,
                     "data_hex": "64FF000000000000", "label": "spoof_brake"})
        t += 0.020
    features = extract_features(prepare(rows), window_len=1.0, step=1.0)
    assert features.iloc[0]["id_0A0_rate_ratio"] > 1.8
    assert features.iloc[0]["label"] == "spoof_brake"


def test_window_label_prefers_attack():
    assert window_label(["normal", "normal", "flood"]) == "flood"
    assert window_label(["normal"]) == "normal"
