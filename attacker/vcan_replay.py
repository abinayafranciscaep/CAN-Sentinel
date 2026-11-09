
#!/usr/bin/env python3
"""Replay explicitly synthetic CAN datasets on local vcan0 only."""

import argparse
import json
import math
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

if __package__:
    from .replay_offline import read_recording
else:
    from replay_offline import read_recording


INTERFACE = "vcan0"
MAX_FRAMES = 121
MAX_DURATION = 120.0
MAX_RATE = 1.0
SCENARIOS = (
    "spoof_brake",
    "replay",
    "fuzz",
    "masquerade",
    "diag_abuse",
)
CSV_FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]


def validate_metadata(csv_path):
    """Load and strictly validate metadata emitted by generate_attack_runs.py."""
    metadata_path = csv_path.with_name(
        csv_path.stem + ".metadata.json"
    )

    if not metadata_path.is_file():
        raise ValueError("Synthetic run metadata file is required")

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Synthetic run metadata is not valid JSON") from error

    if not isinstance(metadata, dict):
        raise ValueError("Synthetic run metadata must be a JSON object")

    if metadata.get("synthetic") is not True:
        raise ValueError("Only explicitly synthetic datasets are permitted")

    if metadata.get("transmitted") is not False:
        raise ValueError("Dataset metadata indicates prior transmission")

    scenario = metadata.get("scenario")
    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        raise ValueError("Dataset scenario metadata is invalid")

    run_number = metadata.get("run_number")
    if (
        isinstance(run_number, bool)
        or not isinstance(run_number, int)
        or run_number < 1
    ):
        raise ValueError("Dataset run_number metadata is invalid")

    expected_run_id = f"{scenario}_run_{run_number:02d}"
    if metadata.get("run_id") != expected_run_id:
        raise ValueError("Dataset run_id metadata does not match scenario/run_number")

    if metadata.get("duration_seconds") != MAX_DURATION:
        raise ValueError("Dataset must declare a 120-second duration")

    interval = metadata.get("interval_seconds")
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not math.isfinite(interval)
        or interval < (1.0 / MAX_RATE)
    ):
        raise ValueError("Dataset interval metadata is invalid or exceeds frame rate")

    steps = MAX_DURATION / interval
    if not math.isclose(steps, round(steps), rel_tol=0, abs_tol=1e-9):
        raise ValueError("Dataset interval must divide the 120-second duration")

    record_count = metadata.get("record_count")
    expected_count = int(round(steps)) + 1
    if (
        isinstance(record_count, bool)
        or not isinstance(record_count, int)
        or record_count != expected_count
        or record_count > MAX_FRAMES
    ):
        raise ValueError("Dataset record_count metadata is invalid")

    baseline_count = metadata.get("baseline_record_count")
    scenario_count = metadata.get("scenario_record_count")
    for name, value in (
        ("baseline_record_count", baseline_count),
        ("scenario_record_count", scenario_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"Dataset {name} metadata is invalid")

    if baseline_count + scenario_count != record_count:
        raise ValueError("Dataset label counts do not match record_count")

    seed = metadata.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Dataset seed metadata is invalid")

    if metadata.get("csv_fields") != CSV_FIELDS:
        raise ValueError("Dataset CSV schema metadata is invalid")

    for name in ("timestamp_start", "timestamp_end"):
        value = metadata.get(name)
        try:
            parsed = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Dataset {name} metadata is invalid") from error
        if not math.isfinite(parsed) or parsed <= 0:
            raise ValueError(f"Dataset {name} metadata is invalid")

    if not math.isclose(
        float(metadata["timestamp_end"]) - float(metadata["timestamp_start"]),
        MAX_DURATION,
        rel_tol=0,
        abs_tol=0.000001,
    ):
        raise ValueError("Dataset metadata timestamps must span 120 seconds")

    return metadata


def validate_metadata_records(metadata, records):
    """Ensure metadata describes the actual CSV records being replayed."""
    if len(records) != metadata["record_count"]:
        raise ValueError("CSV record count does not match metadata")

    first_timestamp = records[0]["timestamp"]
    last_timestamp = records[-1]["timestamp"]

    if not math.isclose(
        first_timestamp,
        float(metadata["timestamp_start"]),
        rel_tol=0,
        abs_tol=0.000001,
    ):
        raise ValueError("CSV start timestamp does not match metadata")

    if not math.isclose(
        last_timestamp,
        float(metadata["timestamp_end"]),
        rel_tol=0,
        abs_tol=0.000001,
    ):
        raise ValueError("CSV end timestamp does not match metadata")

    labels = [record["label"] for record in records]
    if labels.count("normal") != metadata["baseline_record_count"]:
        raise ValueError("CSV baseline label count does not match metadata")

    if labels.count(metadata["scenario"]) != metadata["scenario_record_count"]:
        raise ValueError("CSV scenario label count does not match metadata")

    if any(label not in ("normal", metadata["scenario"]) for label in labels):
        raise ValueError("CSV contains labels inconsistent with metadata")

    expected_interval = metadata["interval_seconds"]
    for index in range(1, len(records)):
        delta = records[index]["timestamp"] - records[index - 1]["timestamp"]
        if not math.isclose(
            delta,
            expected_interval,
            rel_tol=0,
            abs_tol=0.000001,
        ):
            raise ValueError("CSV interval does not match metadata")

    return True


def check_vcan0():
    result = subprocess.run(
        ["ip", "-j", "-d", "link", "show", "dev", INTERFACE],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Local vcan0 does not exist or cannot be inspected"
        )

    try:
        interfaces = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise RuntimeError(
            "Could not parse vcan0 interface details"
        ) from error

    if len(interfaces) != 1:
        raise RuntimeError("Expected exactly one vcan0 interface")

    interface = interfaces[0]

    if interface.get("ifname") != INTERFACE:
        raise RuntimeError("Unexpected CAN interface")

    if interface.get("linkinfo", {}).get("info_kind") != "vcan":
        raise RuntimeError("Interface is not a virtual CAN device")

    if "UP" not in interface.get("flags", []):
        raise RuntimeError("vcan0 is not administratively UP")

    return True


def validate_records(records):
    if not records:
        raise ValueError("Recording is empty")

    if len(records) > MAX_FRAMES:
        raise ValueError("Maximum 121 frames permitted")

    duration = records[-1]["timestamp"] - records[0]["timestamp"]

    if not math.isclose(duration, MAX_DURATION, abs_tol=0.000001):
        raise ValueError(
            "Recording timestamps must span exactly 120 seconds"
        )

    for record in records:
        if record["dlc"] > 8:
            raise ValueError("Invalid CAN DLC")

    for index in range(1, len(records)):
        delta = (
            records[index]["timestamp"]
            - records[index - 1]["timestamp"]
        )

        if delta < (1.0 / MAX_RATE) - 0.000001:
            raise ValueError("Dataset exceeds permitted frame rate")

    return duration


def write_audit(path, event, **fields):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "event": event,
            "timestamp": time.time(),
            "interface": INTERFACE,
            **fields,
        }) + "\n")
        handle.flush()


def run(csv_path, audit_path, execute=False):
    can_socket = None
    sent = 0
    result = 0
    status = "dry_run" if not execute else "completed"
    run_id = None

    try:
        metadata = validate_metadata(csv_path)
        run_id = metadata["run_id"]

        records = read_recording(csv_path)
        duration = validate_records(records)
        validate_metadata_records(metadata, records)
        check_vcan0()

        print("[OK] Interface: vcan0")
        print(f"[OK] Scenario: {metadata['scenario']}")
        print(f"[OK] Run: {run_id}")
        print(f"[OK] Records: {len(records)}")
        print(f"[OK] Timeline: {duration:.1f} seconds")
        print(f"[INFO] Maximum rate: {MAX_RATE:.1f} frame/second")

        if not execute:
            print("[DRY RUN] No CAN frames transmitted.")
            print("Use --execute for isolated vcan0 testing.")
            return 0

        # Require a successful start audit before opening transmission.
        write_audit(
            audit_path,
            "run_start",
            run_id=run_id,
            record_count=len(records),
            duration_seconds=duration,
        )

        can_socket = socket.socket(
            socket.PF_CAN,
            socket.SOCK_RAW,
            socket.CAN_RAW,
        )
        can_socket.bind((INTERFACE,))

        start = time.monotonic()
        first_timestamp = records[0]["timestamp"]

        for index, record in enumerate(records):
            offset = record["timestamp"] - first_timestamp

            if offset < 0 or offset > MAX_DURATION:
                raise ValueError("Frame offset exceeds duration limit")

            target = start + offset
            remaining = target - time.monotonic()

            if remaining > 0:
                time.sleep(remaining)

            can_id = int(record["can_id"], 16)
            payload = bytes.fromhex(record["data_hex"])

            if len(payload) != record["dlc"] or len(payload) > 8:
                raise ValueError("Payload length does not match CAN DLC")

            frame = struct.pack(
                "=IB3x8s",
                can_id,
                len(payload),
                payload.ljust(8, b"\x00"),
            )

            can_socket.sendall(frame)
            sent += 1

            # If this audit fails, the exception stops the next frame.
            # The current frame has already been sent and may be unaudited.
            write_audit(
                audit_path,
                "frame_sent",
                run_id=run_id,
                frame_number=sent,
                can_id=record["can_id"],
                dlc=record["dlc"],
                data_hex=record["data_hex"],
                label=record["label"],
            )

            if sent == 1 or sent % 30 == 0:
                print(f"[SENT] {sent}/{len(records)}")

        print(f"[DONE] Frames sent to vcan0: {sent}")

    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        status = "error"
        result = 1
        print(f"[ERROR] {error}", file=sys.stderr)

    finally:
        if can_socket is not None:
            try:
                can_socket.close()
            except OSError as error:
                print(
                    f"[ERROR] Socket close failed: {error}",
                    file=sys.stderr,
                )
                result = 1
                status = "error"

        if execute:
            try:
                write_audit(
                    audit_path,
                    "run_end",
                    run_id=run_id,
                    status=status,
                    frames_sent=sent,
                )
            except OSError as error:
                print(
                    f"[ERROR] Final audit logging failed: {error}",
                    file=sys.stderr,
                )
                result = 1

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Replay synthetic CAN data on isolated vcan0 only."
    )
    parser.add_argument("recording", type=Path)
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("logs/vcan_replay.jsonl"),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Explicitly transmit synthetic frames to local vcan0",
    )

    args = parser.parse_args()
    return run(args.recording, args.audit, args.execute)


if __name__ == "__main__":
    sys.exit(main())
