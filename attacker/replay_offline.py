#!/usr/bin/env python3
"""Read and validate recorded CAN CSV rows offline; never transmits frames."""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

REQUIRED_FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]
HEX_CHARS = set("0123456789ABCDEF")


def read_recording(path):
    """Load CSV rows and validate their CAN representation and ordering."""
    records = []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames != REQUIRED_FIELDS:
            raise ValueError(
                "CSV header must be: " + ",".join(REQUIRED_FIELDS)
            )

        previous_timestamp = None

        for line_number, row in enumerate(reader, start=2):
            try:
                timestamp = float(row["timestamp"])
                can_id = row["can_id"]
                dlc = int(row["dlc"])
                data_hex = row["data_hex"]
                label = row["label"]

                if not math.isfinite(timestamp):
                    raise ValueError("timestamp must be finite")

                if timestamp <= 0:
                    raise ValueError("timestamp must be positive")

                if previous_timestamp is not None and timestamp < previous_timestamp:
                    raise ValueError("timestamps must be non-decreasing")

                if (
                    len(can_id) != 5
                    or not can_id.startswith("0x")
                    or any(c not in "0123456789ABCDEF" for c in can_id[2:])
                ):
                    raise ValueError("CAN ID must look like 0x0A0")

                if not 0 <= int(can_id[2:], 16) <= 0x7FF:
                    raise ValueError("CAN ID outside standard 11-bit range")

                if not 0 <= dlc <= 8:
                    raise ValueError("DLC must be between 0 and 8")

                if len(data_hex) != dlc * 2:
                    raise ValueError("payload length does not match DLC")

                if any(char not in HEX_CHARS for char in data_hex):
                    raise ValueError("payload must use uppercase hexadecimal")

                if not label:
                    raise ValueError("label cannot be empty")

            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Invalid CSV row at line {line_number}: {error}"
                ) from error

            records.append({
                "timestamp": timestamp,
                "can_id": can_id,
                "dlc": dlc,
                "data_hex": data_hex,
                "label": label,
            })
            previous_timestamp = timestamp

    if not records:
        raise ValueError("recording must contain at least one data row")

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Validate a recorded CAN CSV offline; no CAN transmission."
    )
    parser.add_argument("recording", type=Path, help="Input recording CSV")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSONL file containing validated records",
    )
    args = parser.parse_args()

    try:
        records = read_recording(args.recording)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("w", encoding="utf-8") as handle:
                for record in records:
                    other_fields = {
                        key: value
                        for key, value in record.items()
                        if key != "timestamp"
                    }
                    rest = json.dumps(other_fields)
                    handle.write(
                        '{"timestamp": '
                        + f'{record["timestamp"]:.6f}'
                        + ', '
                        + rest[1:]
                        + "\n"
                    )

    except (OSError, ValueError) as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    print(f"[OK] Validated records: {len(records)}")
    print("[INFO] Offline processing only; no CAN frames transmitted.")
    if args.output:
        print(f"[FILE] {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
