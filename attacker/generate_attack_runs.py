#!/usr/bin/env python3
"""Generate reproducible, offline-only synthetic CAN scenario runs."""

import argparse
import csv
import json
import math
import random
from pathlib import Path

FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]

SCENARIOS = (
    "spoof_brake",
    "replay",
    "fuzz",
    "masquerade",
    "diag_abuse",
)

BASE_TIMESTAMP = 1794300000.0
CAN_ID = "0x0A0"
DLC = 8
BASELINE_FRACTION = 0.10


def generate_run(scenario, run_number, duration, interval, seed):
    """Return deterministic synthetic records and run metadata."""
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError(f"Unsupported scenario: {scenario}")

    if (
        isinstance(run_number, bool)
        or not isinstance(run_number, int)
        or run_number < 1
    ):
        raise ValueError("run_number must be a positive integer")

    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("duration must be finite and greater than zero")

    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not math.isfinite(interval)
        or interval <= 0
    ):
        raise ValueError("interval must be finite and greater than zero")

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")

    steps = duration / interval
    if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-9):
        raise ValueError("duration must be an exact multiple of interval")

    count = int(round(steps)) + 1
    if count > 100000:
        raise ValueError("run would exceed 100000 synthetic records")

    run_seed = seed + run_number * 1009 + SCENARIOS.index(scenario) * 100003
    rng = random.Random(run_seed)

    baseline_count = max(1, int(count * BASELINE_FRACTION))
    records = []

    for index in range(count):
        timestamp = BASE_TIMESTAMP + (run_number * 1000) + (
            SCENARIOS.index(scenario) * 100000
        ) + index * interval

        payload = bytes(rng.randrange(256) for _ in range(DLC)).hex().upper()
        label = "normal" if index < baseline_count else scenario

        records.append({
            "timestamp": f"{timestamp:.6f}",
            "can_id": CAN_ID,
            "dlc": str(DLC),
            "data_hex": payload,
            "label": label,
        })

    metadata = {
        "synthetic": True,
        "transmitted": False,
        "scenario": scenario,
        "run_number": run_number,
        "run_id": f"{scenario}_run_{run_number:02d}",
        "duration_seconds": duration,
        "interval_seconds": interval,
        "record_count": count,
        "baseline_record_count": baseline_count,
        "scenario_record_count": count - baseline_count,
        "seed": run_seed,
        "timestamp_start": records[0]["timestamp"],
        "timestamp_end": records[-1]["timestamp"],
        "csv_fields": FIELDS,
    }

    return records, metadata


def write_run(output_dir, scenario, run_number, records, metadata):
    run_dir = output_dir / scenario
    run_dir.mkdir(parents=True, exist_ok=True)

    stem = f"run_{run_number:02d}"
    csv_path = run_dir / f"{stem}.csv"
    metadata_path = run_dir / f"{stem}.metadata.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)

    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")

    return csv_path, metadata_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate offline synthetic CAN scenario runs."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/synthetic_attack_runs"),
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.runs < 1 or args.runs > 100:
        parser.error("--runs must be between 1 and 100")
    if args.seed < 0:
        parser.error("--seed must be non-negative")

    try:
        for scenario in SCENARIOS:
            for run_number in range(1, args.runs + 1):
                records, metadata = generate_run(
                    scenario,
                    run_number,
                    args.duration,
                    args.interval,
                    args.seed,
                )
                csv_path, metadata_path = write_run(
                    args.output_dir,
                    scenario,
                    run_number,
                    records,
                    metadata,
                )
                print(
                    f"[OK] {metadata['run_id']}: "
                    f"{len(records)} records, "
                    f"{args.duration:.1f} seconds"
                )
                print(f"[CSV] {csv_path}")
                print(f"[META] {metadata_path}")

    except (ValueError, OSError) as exc:
        parser.exit(1, f"[ERROR] {exc}\n")

    print("[DONE] Synthetic scenario datasets generated.")
    print("[INFO] Offline synthetic data only.")
    print("[INFO] No CAN sockets opened; no CAN frames transmitted.")


if __name__ == "__main__":
    main()
