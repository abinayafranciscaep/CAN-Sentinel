#!/usr/bin/env python3
"""Generate synthetic ECU traffic-gap examples offline; no CAN transmission."""

import argparse
import csv
import math
import sys
from pathlib import Path

FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]


def generate_cases(start_timestamp=1791300200.0):
    """Create normal, gap, and synthetic masquerade-labelled records."""
    if (
        isinstance(start_timestamp, bool)
        or not isinstance(start_timestamp, (int, float))
        or not math.isfinite(start_timestamp)
        or start_timestamp <= 0
    ):
        raise ValueError("start_timestamp must be finite and positive")

    samples = [
        (0.000, "3201000000000017", "normal"),
        (0.020, "3301000000000018", "normal"),
        (0.040, "3401000000000019", "normal"),
        # A deliberately longer timestamp gap follows.
        (0.140, "350100000000001A", "masquerade"),
        (0.160, "360100000000001B", "masquerade"),
        (0.180, "370100000000001C", "masquerade"),
    ]

    return [
        {
            "timestamp": f"{start_timestamp + offset:.6f}",
            "can_id": "0x0A0",
            "dlc": 8,
            "data_hex": payload,
            "label": label,
        }
        for offset, payload, label in samples
    ]


def write_cases(output_path, records):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(
        description="Generate offline synthetic masquerade examples."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/masquerade_offline/synthetic_masquerade.csv"),
        help="Output CSV path",
    )
    args = parser.parse_args()

    try:
        records = generate_cases()
        write_cases(args.output, records)
    except OSError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print(f"[OK] Synthetic records generated: {len(records)}")
    print(f"[FILE] {args.output}")
    print("[INFO] Offline synthetic data only; no CAN frames transmitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
