"""
label_dataset.py - label attack frames in a recording using the attacker's injection log.

Frames that match an injection entry (same ID, same payload, timestamp within
TOLERANCE) get the attack name; every other frame is labeled "normal"
(docs/week1_design.md, Section 4.4).

Usage:
    python3 dashboard/label_dataset.py <recording.csv> <injection_log.csv> <attack> <output.csv>
Injection log columns: timestamp, can_id, data_hex (one row per injected frame).
Both files must come from the same machine, so their clocks agree.
"""
import bisect
import csv
import sys
from collections import defaultdict

TOLERANCE = 0.010   # seconds allowed between send time (log) and capture time (recording)
ATTACKS = {"flood", "spoof_brake", "replay", "fuzz", "masquerade", "diag_abuse"}


def norm_id(text):
    """Normalize an ID such as '0a0' or '0X0A0' to '0x0A0'."""
    text = text.strip().upper()
    if text.startswith("0X"):
        text = text[2:]
    return "0x" + text.zfill(3)


def load_injections(path):
    """Return {(can_id, data_hex): sorted list of injection timestamps}."""
    table = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            key = (norm_id(row["can_id"]), row["data_hex"].strip().upper())
            table[key].append(float(row["timestamp"]))
    for stamps in table.values():
        stamps.sort()                      # bisect needs sorted timestamps
    return table


def main(recording, log, attack, output):
    if attack not in ATTACKS:
        sys.exit(f"Unknown attack '{attack}'. Use one of: {', '.join(sorted(ATTACKS))}")
    injections = load_injections(log)
    total = sum(len(v) for v in injections.values())
    used = {key: [False] * len(v) for key, v in injections.items()}   # each entry labels one frame
    rows = matched = 0

    with open(recording, newline="") as fin, open(output, "w", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["timestamp", "can_id", "dlc", "data_hex", "label"])
        for row in csv.DictReader(fin):
            rows += 1
            label = "normal"                                          # default label
            key = (norm_id(row["can_id"]), row["data_hex"].upper())
            stamps = injections.get(key)
            if stamps:
                t = float(row["timestamp"])
                i = bisect.bisect_left(stamps, t - TOLERANCE)         # first entry in the window
                while i < len(stamps) and stamps[i] <= t + TOLERANCE:
                    if not used[key][i]:
                        used[key][i] = True
                        label = attack
                        matched += 1
                        break
                    i += 1
            writer.writerow([row["timestamp"], row["can_id"], row["dlc"], row["data_hex"], label])

    print(f"{rows} frames, {total} injected, {matched} matched ({100 * matched / max(total, 1):.1f}%)")
    if matched < 0.95 * total:
        print("WARNING: fewer than 95% matched. Check that the log and the recording come "
              "from the same machine, and that the log has the right timestamps and payloads.")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
