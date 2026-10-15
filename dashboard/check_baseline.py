"""Baseline check: do the IDs and periods match design doc Section 2?
Usage: python3 dashboard/check_baseline.py data/<file>.csv"""

"""Check CAN IDs, timing periods, and rolling counters in a CSV."""
import csv
import re
import sys
from collections import defaultdict

PERIODS = {
    "0x0A0": 0.020,
    "0x0B0": 0.010,
    "0x100": 0.010,
    "0x200": 0.020,
    "0x300": 0.100,
    "0x600": 0.100,
}

HEADER = ["timestamp", "can_id", "dlc", "data_hex", "label"]


def main(path):
    times = defaultdict(list)
    counters = defaultdict(list)
    failed = False

    try:
        with open(path, newline="") as f:
            reader = csv.DictReader(f)

            if reader.fieldnames != HEADER:
                print(f"FAIL: expected CSV header: {','.join(HEADER)}")
                print(f"Found: {reader.fieldnames}")
                return 1

            for line_no, row in enumerate(reader, start=2):
                try:
                    cid = row["can_id"]
                    timestamp = float(row["timestamp"])
                    data_hex = row["data_hex"]

                    if not re.fullmatch(r"0x[0-9A-F]{3}", cid):
                        raise ValueError(f"invalid CAN ID {cid!r}")
                    if not re.fullmatch(r"[0-9A-F]*", data_hex):
                        raise ValueError("payload must contain uppercase hex")
                    if len(data_hex) % 2:
                        raise ValueError("payload has an odd number of hex digits")

                    times[cid].append(timestamp)

                    if len(data_hex) == 16:
                        counters[cid].append(int(data_hex[14:16], 16))

                except (TypeError, ValueError) as exc:
                    print(f"FAIL: line {line_no}: {exc}")
                    failed = True

    except OSError as exc:
        print(f"FAIL: cannot open {path}: {exc}")
        return 1

    unexpected = sorted(set(times) - set(PERIODS))
    if unexpected:
        print("FAIL: unexpected CAN IDs:", ", ".join(unexpected))
        failed = True

    for cid, expected in PERIODS.items():
        stamps = times.get(cid, [])

        if len(stamps) < 2:
            print(f"{cid}: FAIL, missing or too few frames")
            failed = True
        else:
            mean = (stamps[-1] - stamps[0]) / (len(stamps) - 1)
            ok = abs(mean - expected) <= 0.10 * expected
            print(
                f"{cid}: {len(stamps):>6} frames, "
                f"period {mean * 1000:6.2f} ms "
                f"(expected {expected * 1000:.0f} ms) "
                f"{'ok' if ok else 'FAIL'}"
            )
            failed = failed or not ok

        seq = counters.get(cid, [])
        if not seq:
            print(f"{cid}: FAIL, no 8-byte frames with a counter")
            failed = True
            continue

        breaks = sum(
            1 for a, b in zip(seq, seq[1:])
            if b != (a + 1) % 256
        )
        print(f"{cid}: counter breaks {breaks}")
        failed = failed or breaks > 0

    print("RESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 dashboard/check_baseline.py data/<file>.csv")
        sys.exit(2)

    sys.exit(main(sys.argv[1]))
