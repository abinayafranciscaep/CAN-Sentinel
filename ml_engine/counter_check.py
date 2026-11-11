"""
CAN-Sentinel: rolling-counter checker.

Every ECU frame carries a rolling counter in byte 7 that increases by 1 per
frame and wraps to 0. In normal traffic each CAN ID's counter is continuous.
When an attacker injects frames with their own counter (spoofing), or re-sends
old frames (replay), the sequence breaks. This tool measures those breaks.

It is a standalone analysis tool: it does not change the detector. It is used to
  - check recorded datasets (normal runs should have zero breaks),
  - find the counter range actually used (for example 0-15 or 0-255),
  - measure how strongly spoofing and replay break the counter, as groundwork
    for a rolling-counter rule in the detector.

Usage (from the repository root):
    python ml_engine/counter_check.py data/normal_run1_1016.csv
    python ml_engine/counter_check.py data/synthetic_all_attacks.csv --show 5

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import sys

import pandas as pd

# Periodic IDs that carry a rolling counter in byte 7 (docs/week1_design.md, Section 2)
COUNTER_IDS = ["0x0A0", "0x0B0", "0x100", "0x200", "0x300", "0x600"]


def normalise_id(can_id):
    text = str(can_id).strip().lower().replace("0x", "")
    return "0x" + text.upper().zfill(3)


def counter_value(data_hex):
    """Byte 7 of an 8-byte payload, or None if the payload is shorter."""
    if not isinstance(data_hex, str) or len(data_hex) < 16:
        return None
    try:
        return int(data_hex[14:16], 16)
    except ValueError:
        return None


def infer_modulus(counters):
    """Counter range from the largest value seen: 0-15 gives 16, 0-255 gives 256."""
    top = max(counters)
    for modulus in (16, 256):
        if top < modulus:
            return modulus
    return top + 1


def check(df):
    """Return one summary row per CAN ID and a list of individual breaks."""
    df = df.copy()
    df["can_id"] = df["can_id"].map(normalise_id)
    df = df.sort_values("timestamp", kind="stable")
    df["counter"] = df["data_hex"].map(counter_value)
    has_label = "label" in df.columns

    summary, breaks = [], []
    for can_id in COUNTER_IDS:
        rows = df[(df["can_id"] == can_id) & df["counter"].notna()]
        if len(rows) < 2:
            continue
        counters = rows["counter"].astype(int).tolist()
        modulus = infer_modulus(counters)
        count = 0
        for i in range(1, len(rows)):
            prev, cur = counters[i - 1], counters[i]
            if (cur - prev) % modulus != 1:
                count += 1
                row = rows.iloc[i]
                breaks.append({
                    "timestamp": row["timestamp"], "can_id": can_id,
                    "previous": prev, "current": cur,
                    "label": row["label"] if has_label else "",
                })
        summary.append({
            "can_id": can_id, "frames": len(rows), "range": f"0-{modulus - 1}",
            "breaks": count, "break_rate_%": round(100 * count / (len(rows) - 1), 2),
        })
    return pd.DataFrame(summary), pd.DataFrame(breaks)


def main():
    p = argparse.ArgumentParser(description="CAN-Sentinel rolling-counter checker")
    p.add_argument("input_csv", help="CAN CSV: timestamp, can_id, dlc, data_hex[, label]")
    p.add_argument("--show", type=int, default=0, help="print the first N breaks")
    a = p.parse_args()

    df = pd.read_csv(a.input_csv)
    missing = {"timestamp", "can_id", "data_hex"} - set(df.columns)
    if missing:
        sys.exit(f"CSV is missing columns: {sorted(missing)}")

    summary, breaks = check(df)
    if summary.empty:
        sys.exit("No frames with an 8-byte payload on the baseline IDs were found.")

    print(f"Rolling-counter check: {a.input_csv}")
    print(summary.to_string(index=False))
    total = int(summary["breaks"].sum())
    print(f"Total counter breaks: {total}")

    if total and "label" in breaks.columns and breaks["label"].astype(str).str.len().any():
        print("\nBreaks by label (an injected frame breaks the sequence, and so does the")
        print("next genuine frame, so some breaks are counted on normal frames):")
        print(breaks["label"].value_counts().to_string())
    if a.show and total:
        print(f"\nFirst {min(a.show, total)} breaks:")
        shown = breaks.head(a.show).copy()
        shown["timestamp"] = shown["timestamp"].map(lambda t: f"{t:.6f}")
        print(shown.to_string(index=False))

    print("\nResult:", "PASS - counters continuous on every ID" if total == 0
          else "Counter breaks found - expected only during spoofing or replay")


if __name__ == "__main__":
    main()
