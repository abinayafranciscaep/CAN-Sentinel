#!/usr/bin/env python3
"""Generate synthetic CAN fuzz test cases offline; never opens a CAN socket."""

import argparse
import csv
import math
import random
import sys
from pathlib import Path

FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]


def generate_cases(count=20, seed=42, start_timestamp=1791300100.0):
    """Return reproducible synthetic CAN test cases."""
    if not 1 <= count <= 1000:
        raise ValueError("count must be between 1 and 1000")

    if (
        isinstance(start_timestamp, bool)
        or not isinstance(start_timestamp, (int, float))
        or not math.isfinite(start_timestamp)
        or start_timestamp <= 0
    ):
        raise ValueError("start_timestamp must be finite and positive")

    rng = random.Random(seed)
    records = []

    for index in range(count):
        can_id_value = rng.randint(0, 0x7FF)
        dlc = rng.randint(0, 8)
        payload = bytes(rng.randint(0, 255) for _ in range(dlc))

        records.append({
            "timestamp": f"{start_timestamp + index * 0.01:.6f}",
            "can_id": f"0x{can_id_value:03X}",
            "dlc": dlc,
            "data_hex": payload.hex().upper(),
            "label": "fuzz",
        })

    return records


def write_cases(output_path, records):
    """Write synthetic cases using the project's existing CSV schema."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(
        description="Generate offline synthetic CAN fuzz cases; no CAN transmission."
    )
    parser.add_argument(
        "--count", type=int, default=20,
        help="Number of synthetic cases (1-1000; default: 20)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible test data (default: 42)"
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("logs/fuzz_offline/synthetic_fuzz_cases.csv"),
        help="Output CSV path"
    )
    args = parser.parse_args()

    try:
        records = generate_cases(count=args.count, seed=args.seed)
        write_cases(args.output, records)
    except (OSError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print(f"[OK] Synthetic fuzz cases generated: {len(records)}")
    print(f"[FILE] {args.output}")
    print("[INFO] Offline synthetic data only; no CAN frames transmitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
