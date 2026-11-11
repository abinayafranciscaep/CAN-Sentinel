"""
CAN-Sentinel: feature extraction for the ML engine.

Reads a CAN traffic CSV (timestamp, can_id, dlc, data_hex, label) and turns it
into one row of features per sliding time window. These rows are the input to
the Isolation Forest and the statistics layer.

Usage:
    python features.py data/normal_run1_1010.csv data/features_normal_run1.csv
    python features.py input.csv output.csv --window 1.0 --step 0.5

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import math
from collections import Counter

import numpy as np
import pandas as pd

# Baseline ECUs from docs/week1_design.md, Section 2: CAN ID -> period in seconds
BASELINE_PERIODS = {
    "0x0A0": 0.020,  # brake
    "0x0B0": 0.010,  # steering
    "0x100": 0.010,  # engine RPM
    "0x200": 0.020,  # vehicle speed
    "0x300": 0.100,  # engine temperature
    "0x600": 0.100,  # infotainment heartbeat
}
DIAGNOSTIC_ID = "0x7DF"
KNOWN_IDS = set(BASELINE_PERIODS) | {DIAGNOSTIC_ID}


def shannon_entropy(values):
    """Shannon entropy (bits) of a sequence of hashable values."""
    if len(values) == 0:
        return 0.0
    counts = Counter(values)
    total = len(values)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def payload_entropy(data_hex):
    """Byte-level entropy of one frame's payload. Random fuzzing scores high."""
    if not isinstance(data_hex, str) or len(data_hex) < 2:
        return 0.0
    payload = [data_hex[i:i + 2] for i in range(0, len(data_hex) - 1, 2)]
    return shannon_entropy(payload)


def normalise_id(can_id):
    """Write every ID the same way, e.g. '0a0' or '0x0a0' -> '0x0A0'."""
    text = str(can_id).strip().lower().replace("0x", "")
    return "0x" + text.upper().zfill(3)


def load_frames(path):
    """Load a CAN CSV and add per-frame helper columns."""
    df = pd.read_csv(path)
    required = {"timestamp", "can_id", "dlc", "data_hex"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV is missing columns: {sorted(missing)}")
    if "label" not in df.columns:
        df["label"] = "unknown"

    df["can_id"] = df["can_id"].map(normalise_id)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["payload_entropy"] = df["data_hex"].map(payload_entropy)
    df["dlc_mismatch"] = (df["data_hex"].fillna("").str.len() != df["dlc"] * 2).astype(int)
    df["is_unknown_id"] = (~df["can_id"].isin(KNOWN_IDS)).astype(int)
    return df


def window_label(labels):
    """A window is labelled with its most frequent attack, else 'normal'."""
    attacks = [l for l in labels if l not in ("normal", "unknown")]
    if attacks:
        return Counter(attacks).most_common(1)[0][0]
    return "normal" if "normal" in set(labels) else "unknown"


def window_features(win, window_len):
    """Compute one feature row for the frames inside one time window."""
    row = {
        "frame_count": len(win),
        "bus_rate_fps": len(win) / window_len,
        "unique_ids": win["can_id"].nunique(),
        "unknown_id_count": int(win["is_unknown_id"].sum()),
        "diag_frame_count": int((win["can_id"] == DIAGNOSTIC_ID).sum()),
        "dlc_mismatch_count": int(win["dlc_mismatch"].sum()),
        "id_entropy": shannon_entropy(win["can_id"].tolist()),
        "payload_entropy_mean": float(win["payload_entropy"].mean()) if len(win) else 0.0,
        "payload_entropy_max": float(win["payload_entropy"].max()) if len(win) else 0.0,
    }

    max_rate_ratio = 0.0
    for can_id, period in BASELINE_PERIODS.items():
        key = can_id.replace("0x", "id_")
        frames = win[win["can_id"] == can_id]
        expected = window_len / period
        rate_ratio = len(frames) / expected  # 1.0 = normal, 2.0 = doubled (spoofing)
        gaps = np.diff(frames["timestamp"].to_numpy())

        row[f"{key}_rate_ratio"] = rate_ratio
        row[f"{key}_iat_mean"] = float(gaps.mean()) if len(gaps) else 0.0
        row[f"{key}_iat_std"] = float(gaps.std()) if len(gaps) else 0.0
        # Longest silence relative to the normal period: catches masquerade gaps
        row[f"{key}_max_gap_ratio"] = float(gaps.max() / period) if len(gaps) else 0.0
        max_rate_ratio = max(max_rate_ratio, rate_ratio)

    row["max_rate_ratio"] = max_rate_ratio
    row["label"] = window_label(win["label"].tolist())
    return row


def extract_features(df, window_len=1.0, step=0.5):
    """Slide a window over the traffic and return one feature row per window."""
    if df.empty:
        return pd.DataFrame()
    start, end = df["timestamp"].iloc[0], df["timestamp"].iloc[-1]
    times = df["timestamp"].to_numpy()
    rows = []
    t = start
    while t + window_len <= end + 1e-9:
        lo = np.searchsorted(times, t, side="left")
        hi = np.searchsorted(times, t + window_len, side="left")
        row = window_features(df.iloc[lo:hi], window_len)
        row["window_start"] = t
        rows.append(row)
        t += step
    features = pd.DataFrame(rows)
    first = ["window_start", "label"]
    return features[first + [c for c in features.columns if c not in first]]


def main():
    parser = argparse.ArgumentParser(description="CAN-Sentinel feature extraction")
    parser.add_argument("input_csv", help="CAN traffic CSV from the logger")
    parser.add_argument("output_csv", help="Where to write the feature table")
    parser.add_argument("--window", type=float, default=1.0, help="Window length in seconds")
    parser.add_argument("--step", type=float, default=0.5, help="Step between windows in seconds")
    args = parser.parse_args()

    frames = load_frames(args.input_csv)
    features = extract_features(frames, args.window, args.step)
    features.to_csv(args.output_csv, index=False)
    print(f"Read {len(frames)} frames, wrote {len(features)} windows to {args.output_csv}")
    if not features.empty:
        print(features["label"].value_counts().to_string())


if __name__ == "__main__":
    main()
