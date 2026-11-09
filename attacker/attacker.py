
#!/usr/bin/env python3
"""
CAN-Sentinel Attacker Framework.

Flood mode:
    Bounded vcan0-only CAN traffic testing with audit logging.

Other modes:
    Offline CSV validation or synthetic dataset generation.
    No CAN transmission is performed by offline modes.
"""

import argparse
import csv
import json
import math
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if __package__:
    from . import replay_offline, fuzz_offline, masquerade_offline
else:
    import replay_offline
    import fuzz_offline
    import masquerade_offline


ALLOWED_INTERFACE = "vcan0"
MAX_DURATION = 5.0
MAX_RATE = 100
MAX_FRAMES = 500

DEFAULT_LOG = Path("logs/flood_test.jsonl")

CSV_FIELDS = [
    "timestamp",
    "can_id",
    "dlc",
    "data_hex",
    "label",
]

PLANNED_ATTACKS = {
    "flood": "Bounded vcan0 CAN traffic testing",
    "spoof_brake": "Offline synthetic brake-spoof dataset",
    "replay": "Offline recorded CAN CSV validation",
    "fuzz": "Offline synthetic CAN fuzz dataset",
    "masquerade": "Offline synthetic masquerade dataset",
    "diag_abuse": "Offline synthetic diagnostic-abuse dataset",
}


def timestamp():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_log(log_file, event, **fields):
    """Append one timestamped JSON record to the audit log."""
    record = {
        "timestamp": timestamp(),
        "event": event,
        **fields,
    }

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    except OSError as error:
        print(
            f"[ERROR] Could not write log: {error}",
            file=sys.stderr,
        )
        return False

    return True


def check_interface(interface):
    """Allow CAN testing only on local vcan0."""

    if interface != ALLOWED_INTERFACE:
        print("[ERROR] Only vcan0 is permitted.", file=sys.stderr)
        return False

    result = subprocess.run(
        ["ip", "-details", "link", "show", "dev", interface],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("[ERROR] vcan0 does not exist or cannot be inspected.")
        print("Create the virtual interface before testing.")
        return False

    print("[OK] vcan0 exists.")
    return True


def run_flood(duration, rate, execute, log_path):
    """Run bounded CAN traffic testing exclusively on vcan0."""

    if not check_interface(ALLOWED_INTERFACE):
        return 1

    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
        or duration > MAX_DURATION
    ):
        print(
            f"[ERROR] Duration must be finite, greater than 0 "
            f"and at most {MAX_DURATION} seconds."
        )
        return 1

    if (
        isinstance(rate, bool)
        or not isinstance(rate, int)
        or rate <= 0
        or rate > MAX_RATE
    ):
        print(
            f"[ERROR] Rate must be an integer between 1 "
            f"and {MAX_RATE} frames/second."
        )
        return 1

    frame_count = math.ceil(duration * rate)

    if frame_count > MAX_FRAMES:
        print(f"[ERROR] Maximum frame count is {MAX_FRAMES}.")
        return 1

    print("[INFO] Target: local vcan0 only")
    print(f"[INFO] Duration: {duration} seconds")
    print(f"[INFO] Requested rate: {rate} frames/second")
    print(f"[INFO] Maximum frames for this run: {frame_count}")
    print("[INFO] Standard CAN ID: 0x000; payload length: 8 bytes")
    print(f"[INFO] Log file: {log_path}")

    run_start = timestamp()

    if not write_log(
        log_path,
        "run_start",
        interface=ALLOWED_INTERFACE,
        duration_seconds=duration,
        requested_rate_fps=rate,
        maximum_frames=frame_count,
        can_id="0x000",
        dlc=8,
        mode="execute" if execute else "dry_run",
    ):
        print("[ERROR] Initial audit log failed; stopping.")
        return 1

    if not execute:
        print("[DRY RUN] No CAN frames transmitted.")
        print("Use --execute to run this bounded local test.")

        if not write_log(
            log_path,
            "run_end",
            status="dry_run",
            frames_sent=0,
            start_timestamp=run_start,
        ):
            print("[ERROR] Final audit log failed.")
            return 1

        return 0

    can_socket = None
    sent = 0
    start = None
    status = "completed"
    result = 0

    try:
        can_socket = socket.socket(
            socket.PF_CAN,
            socket.SOCK_RAW,
            socket.CAN_RAW,
        )

        can_socket.bind((ALLOWED_INTERFACE,))

        payload = bytes([
            0x11, 0x22, 0x33, 0x44,
            0x55, 0x66, 0x77, 0x88,
        ])

        frame = struct.pack(
            "=IB3x8s",
            0x000,
            len(payload),
            payload,
        )

        start = time.monotonic()
        interval = 1.0 / rate

        for index in range(frame_count):
            target_time = start + index * interval
            remaining = target_time - time.monotonic()

            if remaining > 0:
                time.sleep(remaining)

            if time.monotonic() - start >= duration:
                break

            can_socket.send(frame)
            sent += 1

            if not write_log(
                log_path,
                "frame_sent",
                interface=ALLOWED_INTERFACE,
                frame_number=sent,
                can_id="0x000",
                dlc=len(payload),
                payload=payload.hex(" ").upper(),
            ):
                status = "logging_error"
                result = 1

                print(
                    "[ERROR] Frame audit logging failed; "
                    "stopping further transmission.",
                    file=sys.stderr,
                )
                break

        elapsed = time.monotonic() - start

        print(f"[DONE] Frames sent: {sent}")
        print(f"[DONE] Elapsed time: {elapsed:.3f} seconds")
        print("[INFO] Transmission was restricted to vcan0.")

    except OSError as error:
        status = "error"
        result = 1

        print(
            f"[ERROR] CAN transmission failed: {error}",
            file=sys.stderr,
        )

    finally:
        if can_socket is not None:
            can_socket.close()

        elapsed = (
            time.monotonic() - start
            if start is not None
            else 0.0
        )

        if not write_log(
            log_path,
            "run_end",
            status=status,
            frames_sent=sent,
            elapsed_seconds=round(elapsed, 3),
            end_timestamp=timestamp(),
        ):
            print("[ERROR] Final audit log failed.", file=sys.stderr)
            result = 1

    return result


def export_replay_jsonl(output_path, records):
    """Export validated recording records to JSON Lines."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def run_replay(recording, output_path):
    """Validate and optionally export a recording without transmission."""

    if recording is None:
        print("[ERROR] Replay requires --recording.", file=sys.stderr)
        return 1

    try:
        records = replay_offline.read_recording(recording)

        if output_path is not None:
            export_replay_jsonl(output_path, records)

    except (OSError, ValueError) as error:
        print(f"[ERROR] Replay validation failed: {error}", file=sys.stderr)
        return 1

    print(f"[OK] Validated recording records: {len(records)}")
    print("[INFO] Offline processing only; no CAN frames transmitted.")

    if output_path is not None:
        print(f"[FILE] {output_path}")

    return 0


def run_fuzz(count, seed, output_path):
    """Generate reproducible offline fuzz records."""

    try:
        records = fuzz_offline.generate_cases(
            count=count,
            seed=seed,
        )
        fuzz_offline.write_cases(output_path, records)

    except (OSError, ValueError) as error:
        print(f"[ERROR] Fuzz generation failed: {error}", file=sys.stderr)
        return 1

    print(f"[OK] Synthetic fuzz records generated: {len(records)}")
    print(f"[FILE] {output_path}")
    print("[INFO] Offline synthetic data only; no CAN frames transmitted.")

    return 0


def run_masquerade(output_path):
    """Generate offline synthetic masquerade examples."""

    try:
        records = masquerade_offline.generate_cases()
        masquerade_offline.write_cases(output_path, records)

    except (OSError, ValueError) as error:
        print(
            f"[ERROR] Masquerade generation failed: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] Synthetic masquerade records generated: {len(records)}")
    print(f"[FILE] {output_path}")
    print("[INFO] Offline synthetic data only; no CAN frames transmitted.")

    return 0


def generate_synthetic_attack_cases(attack):
    """
    Generate generic synthetic examples for offline dataset testing.

    These records are not real ECU signals and must never be transmitted.
    """

    base_timestamp = 1791300300.0

    if attack == "spoof_brake":
        label = "spoof_brake_synthetic"
        payloads = [
            "A500000000000001",
            "A500000000000002",
            "A500000000000003",
        ]

    elif attack == "diag_abuse":
        label = "diag_abuse_synthetic"
        payloads = [
            "B100000000000001",
            "B100000000000002",
            "B100000000000003",
        ]

    else:
        raise ValueError("Unsupported synthetic attack type")

    return [
        {
            "timestamp": f"{base_timestamp + index * 0.02:.6f}",
            "can_id": "0x123",
            "dlc": 8,
            "data_hex": payload,
            "label": label,
        }
        for index, payload in enumerate(payloads)
    ]


def run_synthetic_attack(attack, output_path):
    """Write generic offline synthetic records for a planned attack."""

    try:
        records = generate_synthetic_attack_cases(attack)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=CSV_FIELDS,
            )
            writer.writeheader()
            writer.writerows(records)

    except (OSError, ValueError) as error:
        print(
            f"[ERROR] Synthetic generation failed: {error}",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] Synthetic {attack} records generated: {len(records)}")
    print(f"[FILE] {output_path}")
    print("[INFO] Generic offline fixture only.")
    print("[INFO] No CAN socket opened; no CAN frames transmitted.")

    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="CAN-Sentinel local vcan0 and offline testing framework"
    )

    parser.add_argument(
        "--interface",
        default=ALLOWED_INTERFACE,
        help="Only vcan0 is allowed",
    )

    parser.add_argument(
        "--check-interface",
        action="store_true",
        help="Check whether vcan0 exists",
    )

    parser.add_argument(
        "--list-attacks",
        action="store_true",
        help="List available modules and their execution modes",
    )

    parser.add_argument(
        "--attack",
        choices=sorted(PLANNED_ATTACKS),
        help="Select a module",
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=1.0,
        help="Flood duration in seconds (maximum 5)",
    )

    parser.add_argument(
        "--rate",
        type=int,
        default=10,
        help="Flood rate in frames/second (maximum 100)",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Transmit bounded frames on local vcan0 (flood only)",
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG,
        help="Path for timestamped flood JSON Lines audit log",
    )

    parser.add_argument(
        "--recording",
        type=Path,
        help="Input CAN recording CSV for offline replay validation",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSONL or CSV path for offline processing",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of offline fuzz records (1-1000)",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible fuzz records",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.interface != ALLOWED_INTERFACE:
        parser.error(
            "Safety restriction: only --interface vcan0 is allowed"
        )

    if args.check_interface:
        if args.attack or args.execute or args.recording or args.output:
            parser.error("--check-interface cannot be combined with attack options")
        return 0 if check_interface(args.interface) else 1

    if args.list_attacks:
        print("CAN-Sentinel modules:")

        for name, description in PLANNED_ATTACKS.items():
            print(f"  {name:<12} {description}")

        return 0

    if not args.attack:
        parser.print_help()
        return 0

    if args.attack == "flood":
        if args.recording is not None or args.output is not None:
            parser.error("Offline recording/output options cannot be used with flood")

        return run_flood(
            args.duration,
            args.rate,
            args.execute,
            args.log_file,
        )

    if args.execute:
        parser.error("--execute is permitted only with --attack flood")

    if args.attack == "replay":
        if args.recording is None:
            parser.error("--attack replay requires --recording")

        return run_replay(args.recording, args.output)

    if args.recording is not None:
        parser.error("--recording is only valid with --attack replay")

    if args.attack == "fuzz":
        output_path = args.output or Path(
            "logs/fuzz_offline/synthetic_fuzz_cases.csv"
        )
        return run_fuzz(args.count, args.seed, output_path)

    if args.attack == "masquerade":
        if args.count != 20 or args.seed != 42:
            parser.error("--count and --seed are only valid with --attack fuzz")

        output_path = args.output or Path(
            "logs/masquerade_offline/synthetic_masquerade.csv"
        )
        return run_masquerade(output_path)

    if args.attack == "spoof_brake":
        if args.count != 20 or args.seed != 42:
            parser.error("--count and --seed are only valid with --attack fuzz")

        output_path = args.output or Path(
            "logs/spoof_brake_offline/synthetic_spoof_brake.csv"
        )
        return run_synthetic_attack(args.attack, output_path)

    if args.attack == "diag_abuse":
        if args.count != 20 or args.seed != 42:
            parser.error("--count and --seed are only valid with --attack fuzz")

        output_path = args.output or Path(
            "logs/diag_abuse_offline/synthetic_diag_abuse.csv"
        )
        return run_synthetic_attack(args.attack, output_path)

    return 1


if __name__ == "__main__":
    sys.exit(main())
