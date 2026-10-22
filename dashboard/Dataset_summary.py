#!/usr/bin/env python3
"""
dataset_summary.py - independent timing/count summary of recorded CAN CSVs.

Why: check_baseline.py says PASS/FAIL against a 10% tolerance. This script
shows the raw numbers behind it (time span, overall frame rate, per-ID counts,
mean and median period, largest gaps) so timing questions can be answered
from evidence instead of guesses. It reads files only; it changes nothing.

Usage (from the repository root):
    python3 dashboard/dataset_summary.py data/normal_run1_1016.csv
    python3 dashboard/dataset_summary.py data/normal_run*_1016.csv --duration 600

CSV schema expected: timestamp,can_id,dlc,data_hex,label
"""

import argparse
import csv
import statistics
import sys
from collections import Counter, defaultdict

# Nominal periods in ms, from the design baseline.
EXPECTED_MS = {
    "0x0A0": 20, "0x0B0": 10, "0x100": 10,
    "0x200": 20, "0x300": 100, "0x600": 100,
}
NOMINAL_FPS = sum(1000 / p for p in EXPECTED_MS.values())  # 320 frames/s


def norm_id(raw):
    """Normalise IDs like '0a0', '0x0a0', '0X0A0' to '0x0A0'."""
    s = raw.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        return "0x%03X" % int(s, 16)
    except ValueError:
        return raw.strip()


def summarise(path, duration):
    ids = defaultdict(list)          # can_id -> list of timestamps
    labels = Counter()
    prev = None
    backwards = 0
    back_steps = []                  # (size_seconds, csv_line, seconds_into_file)
    gaps = []                        # (gap_seconds, time_into_file)
    first = last = None
    rows = 0

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        need = {"timestamp", "can_id", "dlc", "data_hex", "label"}
        if not reader.fieldnames or not need <= set(reader.fieldnames):
            print(f"{path}: header is not the 5-column schema", file=sys.stderr)
            return False
        for line_no, r in enumerate(reader, start=2):
            try:
                ts = float(r["timestamp"])
            except ValueError:
                print(f"{path}: bad timestamp on line {line_no}", file=sys.stderr)
                return False
            if first is None:
                first = ts
            if prev is not None:
                if ts < prev:
                    backwards += 1
                    back_steps.append((prev - ts, line_no, ts - first))
                else:
                    gaps.append((ts - prev, ts - first))
            prev = ts
            last = ts
            rows += 1
            ids[norm_id(r["can_id"])].append(ts)
            labels[r["label"]] += 1

    if rows < 2 or last <= first:
        print(f"{path}: not enough rows to summarise", file=sys.stderr)
        return False

    span = last - first
    print("=" * 70)
    print(path)
    print(f"  rows:                {rows}")
    print(f"  timestamp span:      {span:.2f} s", end="")
    if duration:
        print(f"   (logger asked for {duration} s, difference {span - duration:+.2f} s)")
    else:
        print()
    print(f"  overall frame rate:  {rows / span:.2f} /s   (nominal {NOMINAL_FPS:.0f} /s,"
          f" {100 * (rows / span - NOMINAL_FPS) / NOMINAL_FPS:+.2f}%)")
    print(f"  labels:              {dict(labels)}")
    print(f"  timestamps going backwards: {backwards}")
    if back_steps:
        total_back = sum(b[0] for b in back_steps)
        sizes = [b[0] for b in back_steps]
        print(f"    total stepped back: {total_back:.2f} s   "
              f"(span + this = {span + total_back:.2f} s)")
        print(f"    step size: min {min(sizes):.3f} s, "
              f"median {statistics.median(sizes):.3f} s, max {max(sizes):.3f} s")
        for size, line_no, at in back_steps[:5]:
            print(f"    e.g. -{size:.3f} s at csv line {line_no} ({at:.1f} s into the file)")

    top = sorted(gaps, reverse=True)[:3]
    print("  largest gaps between consecutive frames:")
    for g, at in top:
        print(f"    {g * 1000:8.2f} ms   at {at:8.2f} s into the file")

    print()
    print(f"  {'can_id':<7} {'count':>8} {'mean ms':>9} {'median ms':>10} "
          f"{'nominal':>8} {'mean vs nominal':>16} {'count*median':>13}")
    for cid in sorted(ids):
        t = ids[cid]
        n = len(t)
        diffs = [b - a for a, b in zip(t, t[1:])]
        if not diffs:
            print(f"  {cid:<7} {n:>8}  (single frame)")
            continue
        mean_ms = 1000 * (t[-1] - t[0]) / (n - 1)
        med_ms = 1000 * statistics.median(diffs)
        nom = EXPECTED_MS.get(cid)
        if nom:
            dev = f"{100 * (mean_ms - nom) / nom:+.2f}%"
            nom_s = f"{nom}"
        else:
            dev, nom_s = "unexpected id", "-"
        implied = n * med_ms / 1000
        print(f"  {cid:<7} {n:>8} {mean_ms:>9.2f} {med_ms:>10.2f} {nom_s:>8} "
              f"{dev:>16} {implied:>11.1f} s")
    
    # Dataset quality summary
    expected_ids = set(EXPECTED_MS)
    observed_ids = set(ids)
    unexpected_ids = observed_ids - expected_ids
    unexpected_labels = set(labels) - {"normal", "attack"}

     # Basic dataset quality warnings
    warnings = []

    if backwards:
        warnings.append(
            f"{backwards} backward timestamp step(s)"
        )

    unexpected_ids = set(ids) - set(EXPECTED_MS)
    if unexpected_ids:
        warnings.append(
            "Unexpected CAN IDs: "
            + ", ".join(sorted(unexpected_ids))
        )

    if warnings:
        print("  DATASET QUALITY: WARNING")
        for warning in warnings:
            print(f"    - {warning}")
    else:
        print("  DATASET QUALITY: PASS (basic checks only)")
   
    print()    
    return True



def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--duration", type=float, default=None,
                    help="seconds the logger was asked to record, for comparison")
    args = ap.parse_args()

    ok = True
    for p in args.files:
        try:
            ok = summarise(p, args.duration) and ok
        except OSError as e:
            print(f"{p}: {e}", file=sys.stderr)
            ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()