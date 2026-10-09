"""
validate_csv.py - checks a CAN-Sentinel CSV against the schema (design doc, Section 5.1)
Usage: python3 dashboard/validate_csv.py data/<file>.csv

Q1 (why recv has a timeout): <your answer>
Q2 (why DLC 0 gives two commas): <your answer>
"""
import csv
import re
import sys

HEADER = ["timestamp", "can_id", "dlc", "data_hex", "label"]
LABELS = {"normal", "flood", "spoof_brake", "replay", "fuzz", "masquerade", "diag_abuse"}

def check_row(row):
    problems = []
    if len(row) != 5:
        return [f"expected 5 columns, got {len(row)}"]
    timestamp, can_id, dlc, data_hex, label = row

    # Check 1: timestamp must be a number, or Abinaya's feature code can't compute inter-arrival times
    try:
        float(timestamp)
    except ValueError:
        problems.append(f"timestamp not a number: {timestamp!r}")

    # Check 2: ID must be 0x + 3 uppercase hex digits, or her per-ID grouping splits one ID into two names
    if not re.fullmatch(r"0x[0-9A-F]{3}", can_id):
        problems.append(f"can_id bad format: {can_id!r}")

    # Check 3: DLC must be an integer from 0 to 8 (classic CAN)
    dlc_int = None
    try:
        dlc_int = int(dlc)
        if not 0 <= dlc_int <= 8:
            problems.append(f"dlc out of range 0-8: {dlc_int}")
    except ValueError:
        problems.append(f"dlc not an integer: {dlc!r}")

    # Check 4: data must be uppercase hex only, and 2 hex characters per byte
    if not re.fullmatch(r"[0-9A-F]*", data_hex):
        problems.append(f"data_hex has invalid characters: {data_hex!r}")
    if dlc_int is not None and len(data_hex) != 2 * dlc_int:
        problems.append(f"data_hex length {len(data_hex)} does not match dlc {dlc_int} (need {2 * dlc_int})")

    # Check 5: label must be one of the agreed names, or the model sees a class that doesn't exist
    if label not in LABELS:
        problems.append(f"unknown label: {label!r}")

    return problems

def main(path):
    bad = 0
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header != HEADER:
            print(f"BAD HEADER: {header}")
            bad += 1
        total = 0
        for line_no, row in enumerate(reader, start=2):
            total += 1
            for p in check_row(row):
                print(f"line {line_no}: {p}")
                bad += 1
    print(f"{total} rows checked, {bad} problems")
    return bad

if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1]) else 0)
