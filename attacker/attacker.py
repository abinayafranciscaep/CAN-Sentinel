#!/usr/bin/env python3
"""
CAN-Sentinel Attacker Framework
Day 5: CLI skeleton and local vcan0 interface validation.

Attack transmission is intentionally not implemented yet.
All future testing must remain restricted to the local vcan0 lab.
"""

import argparse
import subprocess
import sys

ALLOWED_INTERFACE = "vcan0"

PLANNED_ATTACKS = {
    "flood": "High-rate CAN frame transmission (planned)",
    "spoof_brake": "Brake message spoofing (planned)",
    "replay": "Previously captured frame replay (planned)",
    "fuzz": "Controlled CAN payload fuzzing (planned)",
    "masquerade": "CAN message masquerading (planned)",
    "diag_abuse": "Diagnostic-message testing (planned)",
}


def check_interface(interface):
    """Check whether the permitted local virtual CAN interface exists."""
    if interface != ALLOWED_INTERFACE:
        print(
            f"[ERROR] Only '{ALLOWED_INTERFACE}' is permitted.",
            file=sys.stderr,
        )
        return False

    result = subprocess.run(
        ["ip", "link", "show", "dev", interface],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print(f"[ERROR] Interface '{interface}' was not found.")
        print("Check it with: ip link show vcan0")
        return False

    print(f"[OK] Interface '{interface}' exists.")
    print("[INFO] This is an interface existence check, not an attack test.")
    return True


def build_parser():
    parser = argparse.ArgumentParser(
        description="CAN-Sentinel local vcan0 attacker framework"
    )

    parser.add_argument(
        "--interface",
        default=ALLOWED_INTERFACE,
        help="Permitted lab interface (default: vcan0)",
    )

    parser.add_argument(
        "--check-interface",
        action="store_true",
        help="Check whether the permitted interface exists",
    )

    parser.add_argument(
        "--list-attacks",
        action="store_true",
        help="List planned attack modules",
    )

    parser.add_argument(
        "--attack",
        choices=sorted(PLANNED_ATTACKS),
        help="Select a planned attack module (not implemented yet)",
    )

    parser.add_argument(
        "--duration",
        type=float,
        default=5.0,
        help="Planned duration in seconds (default: 5)",
    )

    parser.add_argument(
        "--rate",
        type=int,
        default=100,
        help="Planned frame rate in frames/second (default: 100)",
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.interface != ALLOWED_INTERFACE:
        parser.error("Safety restriction: only --interface vcan0 is allowed")

    if args.duration <= 0:
        parser.error("--duration must be greater than zero")

    if args.rate <= 0:
        parser.error("--rate must be greater than zero")

    if args.list_attacks:
        print("Planned CAN-Sentinel attack modules:")
        for name, description in PLANNED_ATTACKS.items():
            print(f"  {name:<12} {description}")
        return 0

    if args.check_interface:
        return 0 if check_interface(args.interface) else 1

    if args.attack:
        print(f"[INFO] Selected module: {args.attack}")
        print(f"[INFO] Interface: {args.interface}")
        print(f"[INFO] Planned duration: {args.duration} seconds")
        print(f"[INFO] Planned rate: {args.rate} frames/second")
        print("[NOT IMPLEMENTED] No CAN frames were transmitted.")
        print("Attack implementation is scheduled for a later project day.")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
