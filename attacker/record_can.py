
#!/usr/bin/env python3
"""Capture live local vcan0 frames from the CAN sniffer socket into CSV."""

import argparse
import csv
import json
import socket
import sys
import time
from pathlib import Path

SOCKET_PATH = "/tmp/can_sentinel.sock"
FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]
VALID_LABELS = {
    "normal",
    "spoof_brake",
    "replay",
    "fuzz",
    "masquerade",
    "diag_abuse",
}


def main():
    parser = argparse.ArgumentParser(
        description="Record authorized local vcan0 test traffic."
    )
    parser.add_argument("--label", required=True, choices=sorted(VALID_LABELS))
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not 0 < args.duration <= 600:
        parser.error("Duration must be between 0 and 600 seconds.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    deadline = time.monotonic() + args.duration
    buffer = b""

    print(f"[INFO] Connecting to {SOCKET_PATH}")
    print(f"[INFO] Label: {args.label}")
    print(f"[INFO] Duration: {args.duration}s")
    print(f"[INFO] Output: {output}")
    print("[INFO] Start the C sniffer with --socket in another terminal.")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(5)
            conn.connect(SOCKET_PATH)
            conn.settimeout(1)

            with output.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS)
                writer.writeheader()
                handle.flush()

                while time.monotonic() < deadline:
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        continue

                    if not chunk:
                        raise ConnectionError("Sniffer disconnected.")

                    buffer += chunk

                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip():
                            continue

                        event = json.loads(line.decode("utf-8"))
                        can_id = str(event["can_id"])
                        dlc = int(event["dlc"])
                        data_hex = str(event["data_hex"]).upper()
                        timestamp = float(event["timestamp"])

                        if not 0 <= dlc <= 8:
                            raise ValueError("Invalid CAN DLC.")
                        if len(data_hex) != dlc * 2:
                            raise ValueError("Payload length does not match DLC.")
                        if not can_id.startswith("0x"):
                            raise ValueError("Invalid CAN ID format.")

                        writer.writerow({
                            "timestamp": timestamp,
                            "can_id": can_id,
                            "dlc": dlc,
                            "data_hex": data_hex,
                            "label": args.label,
                        })
                        count += 1

                        if count % 50 == 0:
                            handle.flush()
                            print(f"[INFO] Captured {count} frames")

                handle.flush()

    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"[ERROR] Recording failed: {error}", file=sys.stderr)
        return 1

    print(f"[DONE] Captured {count} frames.")
    print(f"[DONE] Saved: {output}")
    if count == 0:
        print("[WARNING] Empty recording; do not use as dataset evidence.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
