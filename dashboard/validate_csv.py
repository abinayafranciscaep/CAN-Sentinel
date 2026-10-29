
"""
validate_csv.py - validates a CAN-Sentinel CSV against the expected schema.

Usage:
    python3 dashboard/validate_csv.py data/<file>.csv
"""

import csv
import math
import re
import sys
from pathlib import Path

HEADER = ["timestamp", "can_id", "dlc", "data_hex", "label"]

LABELS = {
    "normal",
    "flood",
    "spoof_brake",
    "replay",
    "fuzz",
    "masquerade",
    "diag_abuse",
}


def check_row(row):
    problems = []

    if len(row) != len(HEADER):
        return [f"expected {len(HEADER)} columns, got {len(row)}"]

    timestamp, can_id, dlc, data_hex, label = row

    # 1. Timestamp must be numeric and finite.
    try:
        timestamp_value = float(timestamp)
        if not math.isfinite(timestamp_value):
            problems.append(f"timestamp must be finite: {timestamp!r}")
    except ValueError:
        problems.append(f"timestamp not a number: {timestamp!r}")

    # 2. CAN ID must use the expected 3-digit uppercase format.
    if not re.fullmatch(r"0x[0-9A-F]{3}", can_id):
        problems.append(f"can_id bad format: {can_id!r}")

    # 3. DLC must be an integer from 0 through 8.
    dlc_int = None
    if not re.fullmatch(r"[0-8]", dlc):
        problems.append(f"dlc must be an integer from 0 to 8: {dlc!r}")
    else:
        dlc_int = int(dlc)

    # 4. Payload must contain uppercase hexadecimal characters.
    if not re.fullmatch(r"[0-9A-F]*", data_hex):
        problems.append(f"data_hex has invalid characters: {data_hex!r}")

    if len(data_hex) % 2 != 0:
        problems.append("data_hex must contain complete bytes")

    if dlc_int is not None and len(data_hex) != 2 * dlc_int:
        problems.append(
            f"data_hex length {len(data_hex)} does not match "
            f"dlc {dlc_int} (need {2 * dlc_int})"
        )

    # 5. Label must belong to the agreed set.
    if label not in LABELS:
        problems.append(f"unknown label: {label!r}")

    return problems


def main(path):
    bad = 0
    total = 0

    try:
        with open(path, newline="", encoding="utf-8-sig") as file:
            reader = csv.reader(file)
            header = next(reader, None)

            if header is None:
                print("ERROR: CSV file is empty or has no header.")
                return 1

            if header != HEADER:
                print(f"BAD HEADER: expected {HEADER}, got {header}")
                return 1

            for line_no, row in enumerate(reader, start=2):
                total += 1

                for problem in check_row(row):
                    print(f"line {line_no}: {problem}")
                    bad += 1

    except (OSError, UnicodeError, csv.Error) as error:
        print(f"ERROR: Could not validate CSV: {error}")
        return 1

    print(f"{total} rows checked, {bad} problems")

    if total == 0:
        print("WARNING: CSV contains a header but no data rows.")
        return 1

    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python3 {Path(sys.argv[0]).as_posix()} <file.csv>")
        sys.exit(2)

    sys.exit(main(sys.argv[1]))
