#!/usr/bin/env python3
"""Generate offline synthetic CAN CSV fixtures; never opens a CAN socket."""

import argparse
import csv
from pathlib import Path

CAN_ID = "0x0A0"
DLC = 8
RAW_FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]
INJECTION_FIELDS = ["timestamp", "can_id", "data_hex"]


def main():
    parser = argparse.ArgumentParser(
        description="Generate clearly synthetic CAN dataset fixtures."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/synthetic_fixture"),
        help="Output directory (default: logs/synthetic_fixture)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_path = output_dir / "synthetic_raw.csv"
    injection_path = output_dir / "synthetic_injection_log.csv"

    # Fixed timestamps make this fixture reproducible.
    # These rows are synthetic examples, not real CAN captures.
    normal_rows = [
        (1791300000.100000, "3201000000000017"),
        (1791300000.120000, "3301000000000018"),
        (1791300000.140000, "3401000000000019"),
    ]
    synthetic_event_rows = [
        (1791300000.150000, "000000000000001A"),
        (1791300000.170000, "000000000000001B"),
    ]

    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        writer.writeheader()

        for timestamp, payload in normal_rows:
            writer.writerow({
                "timestamp": f"{timestamp:.6f}",
                "can_id": CAN_ID,
                "dlc": DLC,
                "data_hex": payload,
                "label": "normal",
            })

        for timestamp, payload in synthetic_event_rows:
            writer.writerow({
                "timestamp": f"{timestamp:.6f}",
                "can_id": CAN_ID,
                "dlc": DLC,
                "data_hex": payload,
                "label": "spoof_brake",
            })

    with injection_path.open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=INJECTION_FIELDS)
        writer.writeheader()

        for timestamp, payload in synthetic_event_rows:
            writer.writerow({
                "timestamp": f"{timestamp:.6f}",
                "can_id": CAN_ID,
                "data_hex": payload,
            })

    print("[OK] Synthetic fixture generated.")
    print(f"[FILE] {raw_path}")
    print(f"[FILE] {injection_path}")
    print("[INFO] Offline synthetic data only; no CAN frames transmitted.")


if __name__ == "__main__":
    main()
