"""Baseline check: do the IDs and periods match design doc Section 2?
Usage: python3 dashboard/check_baseline.py data/<file>.csv"""
import csv
import sys
from collections import defaultdict

# Expected period in seconds for each baseline ID.
PERIODS = {"0x0A0": 0.020, "0x0B0": 0.010, "0x100": 0.010,
           "0x200": 0.020, "0x300": 0.100, "0x600": 0.100}

times = defaultdict(list)                  # CAN ID -> timestamps of its frames
with open(sys.argv[1], newline="") as f:
    for row in csv.DictReader(f):
        times[row["can_id"]].append(float(row["timestamp"]))

# Check 1: no IDs outside the baseline set.
unexpected = sorted(set(times) - set(PERIODS))
failed = bool(unexpected)
if unexpected:
    print(f"FAIL: {len(unexpected)} unexpected IDs, e.g. {', '.join(unexpected[:5])}")

# Check 2: every baseline ID is present, and its average period is within 10% of expected.
for cid, expected in PERIODS.items():
    stamps = times.get(cid, [])
    if len(stamps) < 2:
        print(f"{cid}: FAIL, missing or too few frames")
        failed = True
        continue
    mean = (stamps[-1] - stamps[0]) / (len(stamps) - 1)   # total time / number of gaps
    ok = abs(mean - expected) <= 0.10 * expected
    failed = failed or not ok
    print(f"{cid}: {len(stamps):>6} frames, period {mean * 1000:6.2f} ms "
          f"(expected {expected * 1000:.0f} ms) {'ok' if ok else 'FAIL'}")

print("RESULT:", "FAIL" if failed else "PASS")
sys.exit(1 if failed else 0)
