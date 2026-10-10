#!/usr/bin/env python3
"""
CAN-Sentinel Attacker Framework
Day 6: Rate-limited flood simulation on the local vcan0 interface.
"""

import argparse
import math
import socket
import struct
import subprocess
import sys
import time

ALLOWED_INTERFACE = "vcan0"
MAX_DURATION = 5.0
MAX_RATE = 100
MAX_FRAMES = 500

PLANNED_ATTACKS = {
    "flood": "Rate-limited local vcan0 traffic simulation",
    "spoof_brake": "Brake message spoofing (planned)",
    "replay": "Previously captured frame replay (planned)",
    "fuzz": "Controlled CAN payload fuzzing (planned)",
    "masquerade": "CAN message masquerading (planned)",
    "diag_abuse": "Diagnostic-message testing (planned)",
}


def check_interface(interface):
    """Allow only the configured local virtual CAN interface."""
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


def run_flood(duration, rate, execute):
    """Send bounded standard CAN frames only when explicitly requested."""
    if not check_interface(ALLOWED_INTERFACE):
        return 1

    if duration <= 0 or duration > MAX_DURATION:
        print(f"[ERROR] Duration must be between 0 and {MAX_DURATION} seconds.")
        return 1

    if rate <= 0 or rate > MAX_RATE:
        print(f"[ERROR] Rate must be between 1 and {MAX_RATE} frames/second.")
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

    if not execute:
        print("[DRY RUN] No CAN frames transmitted.")
        print("Use --execute to run this bounded local test.")
        return 0

    can_socket = None
    sent = 0

    try:
        can_socket = socket.socket(
            socket.PF_CAN,
            socket.SOCK_RAW,
            socket.CAN_RAW,
        )
        can_socket.bind((ALLOWED_INTERFACE,))

        payload = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
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

        elapsed = time.monotonic() - start
        print(f"[DONE] Frames sent: {sent}")
        print(f"[DONE] Elapsed time: {elapsed:.3f} seconds")
        print("[INFO] Transmission was restricted to vcan0.")
        return 0

    except OSError as error:
        print(f"[ERROR] CAN transmission failed: {error}", file=sys.stderr)
        return 1

    finally:
        if can_socket is not None:
            can_socket.close()


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
        help="Actually transmit bounded frames on local vcan0",
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
        return run_flood(args.duration, args.rate, args.execute)

    if args.attack:
        print(f"[PLANNED] {args.attack} is not implemented yet.")
        print("[INFO] No CAN frames transmitted.")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
