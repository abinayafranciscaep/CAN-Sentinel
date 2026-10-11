
#!/usr/bin/env python3
"""
CAN-Sentinel Attacker Framework
Day 7: Bounded vcan0 flood testing with timestamped logging.
"""

import argparse
import json
import math
import socket
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_INTERFACE = "vcan0"
MAX_DURATION = 5.0
MAX_RATE = 100
MAX_FRAMES = 500

DEFAULT_LOG = Path("logs/flood_test.jsonl")

PLANNED_ATTACKS = {
    "flood": "Rate-limited local vcan0 traffic simulation",
    "spoof_brake": "Brake message spoofing (planned)",
    "replay": "Previously captured frame replay (planned)",
    "fuzz": "Controlled CAN payload fuzzing (planned)",
    "masquerade": "CAN message masquerading (planned)",
    "diag_abuse": "Diagnostic-message testing (planned)",
}


def timestamp():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def write_log(log_file, event, **fields):
    """Append one timestamped JSON record to the log."""
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
        print(f"[ERROR] Could not write log: {error}", file=sys.stderr)
        return False
    return True


def check_interface(interface):
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
    if not check_interface(ALLOWED_INTERFACE):
        return 1

    if duration <= 0 or duration > MAX_DURATION:
        print(
            f"[ERROR] Duration must be greater than 0 and "
            f"at most {MAX_DURATION} seconds."
        )
        return 1

    if rate <= 0 or rate > MAX_RATE:
        print(
            f"[ERROR] Rate must be between 1 and "
            f"{MAX_RATE} frames/second."
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
    write_log(
        log_path,
        "run_start",
        interface=ALLOWED_INTERFACE,
        duration_seconds=duration,
        requested_rate_fps=rate,
        maximum_frames=frame_count,
        can_id="0x000",
        dlc=8,
        mode="execute" if execute else "dry_run",
    )

    if not execute:
        print("[DRY RUN] No CAN frames transmitted.")
        print("Use --execute to run this bounded local test.")
        write_log(
            log_path,
            "run_end",
            status="dry_run",
            frames_sent=0,
            start_timestamp=run_start,
        )
        return 0

    can_socket = None
    sent = 0
    start = None
    status = "completed"

    try:
        can_socket = socket.socket(
            socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW
        )
        can_socket.bind((ALLOWED_INTERFACE,))

        payload = bytes(
            [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]
        )
        frame = struct.pack("=IB3x8s", 0x000, len(payload), payload)

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

            write_log(
                log_path,
                "frame_sent",
                interface=ALLOWED_INTERFACE,
                frame_number=sent,
                can_id="0x000",
                dlc=len(payload),
                payload=payload.hex(" ").upper(),
            )

        elapsed = time.monotonic() - start

        print(f"[DONE] Frames sent: {sent}")
        print(f"[DONE] Elapsed time: {elapsed:.3f} seconds")
        print("[INFO] Transmission was restricted to vcan0.")

        return 0

    except OSError as error:
        status = "error"
        print(f"[ERROR] CAN transmission failed: {error}", file=sys.stderr)
        return 1

    finally:
        if can_socket is not None:
            can_socket.close()

        elapsed = (
            time.monotonic() - start if start is not None else 0.0
        )

        write_log(
            log_path,
            "run_end",
            status=status,
            frames_sent=sent,
            elapsed_seconds=round(elapsed, 3),
            end_timestamp=timestamp(),
        )


def build_parser():
    parser = argparse.ArgumentParser(
        description="CAN-Sentinel local vcan0 testing framework"
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
        help="List available and planned modules",
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
        help="Transmit bounded frames on local vcan0",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=DEFAULT_LOG,
        help="Path for timestamped JSON Lines log",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.interface != ALLOWED_INTERFACE:
        parser.error("Safety restriction: only --interface vcan0 is allowed")

    if args.check_interface:
        return 0 if check_interface(args.interface) else 1

    if args.list_attacks:
        print("CAN-Sentinel modules:")
        for name, description in PLANNED_ATTACKS.items():
            print(f"  {name:<12} {description}")
        return 0

    if args.attack == "flood":
        return run_flood(
            args.duration,
            args.rate,
            args.execute,
            args.log_file,
        )

    if args.attack:
        print(f"[PLANNED] {args.attack} is not implemented yet.")
        print("[INFO] No CAN frames transmitted.")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
