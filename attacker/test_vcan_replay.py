
#!/usr/bin/env python3
"""Safety tests for synthetic-only vcan0 replay."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vcan_replay import (
    INTERFACE,
    validate_metadata,
    validate_records,
    validate_metadata_records,
    run,
)


class VCanReplayTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

        self.csv_path = self.root / "run_01.csv"
        self.metadata_path = self.root / "run_01.metadata.json"
        self.audit_path = self.root / "audit.jsonl"

        self.records = []

        for index in range(121):
            self.records.append({
                "timestamp": 1794301000.0 + index,
                "can_id": "0x0A0",
                "dlc": 8,
                "data_hex": "1122334455667788",
                "label": "normal" if index < 13 else "fuzz",
            })

        with self.csv_path.open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "timestamp",
                    "can_id",
                    "dlc",
                    "data_hex",
                    "label",
                ],
            )
            writer.writeheader()
            writer.writerows(self.records)

        self.metadata = {
            "synthetic": True,
            "transmitted": False,
            "scenario": "fuzz",
            "run_number": 1,
            "run_id": "fuzz_run_01",
            "duration_seconds": 120.0,
            "interval_seconds": 1.0,
            "record_count": 121,
            "baseline_record_count": 13,
            "scenario_record_count": 108,
            "seed": 1051,
            "timestamp_start": "1794301000.000000",
            "timestamp_end": "1794301120.000000",
            "csv_fields": ["timestamp", "can_id", "dlc", "data_hex", "label"],
        }

        self.write_metadata()

    def tearDown(self):
        self.temp.cleanup()

    def write_metadata(self):
        self.metadata_path.write_text(
            json.dumps(self.metadata),
            encoding="utf-8",
        )

    def test_valid_synthetic_metadata(self):
        metadata = validate_metadata(self.csv_path)
        self.assertEqual(metadata["run_id"], "fuzz_run_01")

    def test_unknown_scenario_rejected(self):
        self.metadata["scenario"] = "unknown"
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "scenario"):
            validate_metadata(self.csv_path)

    def test_mismatched_run_id_rejected(self):
        self.metadata["run_id"] = "replay_run_01"
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "run_id"):
            validate_metadata(self.csv_path)

    def test_invalid_record_count_metadata_rejected(self):
        self.metadata["record_count"] = 120
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "record_count"):
            validate_metadata(self.csv_path)

    def test_metadata_must_match_csv_records(self):
        metadata = validate_metadata(self.csv_path)
        self.assertTrue(validate_metadata_records(metadata, self.records))

    def test_metadata_record_count_mismatch_rejected(self):
        metadata = validate_metadata(self.csv_path)
        metadata["record_count"] = 120
        with self.assertRaisesRegex(ValueError, "record count"):
            validate_metadata_records(metadata, self.records)

    def test_metadata_label_counts_mismatch_rejected(self):
        metadata = validate_metadata(self.csv_path)
        metadata["scenario_record_count"] = 107
        with self.assertRaisesRegex(ValueError, "label count"):
            validate_metadata_records(metadata, self.records)

    def test_missing_metadata_rejected(self):
        self.metadata_path.unlink()

        with self.assertRaisesRegex(ValueError, "required"):
            validate_metadata(self.csv_path)

    def test_non_synthetic_metadata_rejected(self):
        self.metadata["synthetic"] = False
        self.write_metadata()

        with self.assertRaisesRegex(ValueError, "synthetic"):
            validate_metadata(self.csv_path)

    def test_previously_transmitted_dataset_rejected(self):
        self.metadata["transmitted"] = True
        self.write_metadata()

        with self.assertRaisesRegex(ValueError, "prior transmission"):
            validate_metadata(self.csv_path)

    def test_wrong_duration_metadata_rejected(self):
        self.metadata["duration_seconds"] = 60
        self.write_metadata()

        with self.assertRaisesRegex(ValueError, "120-second"):
            validate_metadata(self.csv_path)

    def test_valid_record_count_and_duration(self):
        duration = validate_records(self.records)
        self.assertEqual(duration, 120.0)

    def test_empty_records_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_records([])

    def test_excessive_record_count_rejected(self):
        records = self.records + [dict(self.records[-1])]

        with self.assertRaisesRegex(ValueError, "121 frames"):
            validate_records(records)

    def test_wrong_timeline_rejected(self):
        records = [dict(row) for row in self.records]
        records[-1]["timestamp"] += 1

        with self.assertRaisesRegex(ValueError, "120 seconds"):
            validate_records(records)

    def test_dry_run_never_opens_can_socket(self):
        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket") as socket_mock,
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=False,
            )

        self.assertEqual(result, 0)
        socket_mock.assert_not_called()

    def test_dry_run_does_not_create_audit_log(self):
        with patch("vcan_replay.check_vcan0", return_value=True):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=False,
            )

        self.assertEqual(result, 0)
        self.assertFalse(self.audit_path.exists())

    def test_invalid_metadata_prevents_socket_creation(self):
        self.metadata["synthetic"] = False
        self.write_metadata()

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket") as socket_mock,
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 1)
        socket_mock.assert_not_called()

    def test_csv_metadata_mismatch_prevents_socket_creation(self):
        self.metadata["timestamp_end"] = "1794301121.000000"
        self.write_metadata()

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket") as socket_mock,
        ):
            result = run(self.csv_path, self.audit_path, execute=True)

        self.assertEqual(result, 1)
        socket_mock.assert_not_called()

    def test_execute_binds_only_to_vcan0(self):
        fake_socket = MagicMock()

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket", return_value=fake_socket),
            patch("vcan_replay.time.monotonic", return_value=0),
            patch("vcan_replay.time.sleep"),
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 0)
        fake_socket.bind.assert_called_once_with((INTERFACE,))
        self.assertEqual(fake_socket.sendall.call_count, 121)
        fake_socket.close.assert_called_once()

    def test_execute_writes_audit_events(self):
        fake_socket = MagicMock()

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket", return_value=fake_socket),
            patch("vcan_replay.time.monotonic", return_value=0),
            patch("vcan_replay.time.sleep"),
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 0)

        events = [
            json.loads(line)
            for line in self.audit_path.read_text().splitlines()
        ]

        self.assertEqual(events[0]["event"], "run_start")
        self.assertEqual(events[-1]["event"], "run_end")
        self.assertEqual(events[-1]["frames_sent"], 121)

        self.assertEqual(
            sum(event["event"] == "frame_sent" for event in events),
            121,
        )

    def test_run_start_audit_failure_prevents_transmission(self):
        fake_socket = MagicMock()

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket", return_value=fake_socket),
            patch(
                "vcan_replay.write_audit",
                side_effect=OSError("simulated audit failure"),
            ),
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 1)
        fake_socket.sendall.assert_not_called()
        fake_socket.close.assert_not_called()

    def test_frame_audit_failure_stops_further_transmission(self):
        fake_socket = MagicMock()

        audit_calls = 0

        def simulated_audit(path, event, **fields):
            nonlocal audit_calls
            audit_calls += 1

            if event == "frame_sent":
                raise OSError("simulated frame audit failure")

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket", return_value=fake_socket),
            patch("vcan_replay.time.monotonic", return_value=0),
            patch("vcan_replay.time.sleep"),
            patch(
                "vcan_replay.write_audit",
                side_effect=simulated_audit,
            ),
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 1)
        self.assertEqual(fake_socket.sendall.call_count, 1)
        fake_socket.close.assert_called_once()
        self.assertEqual(audit_calls, 3)

    def test_run_end_audit_failure_returns_error(self):
        fake_socket = MagicMock()

        def simulated_audit(path, event, **fields):
            if event == "run_end":
                raise OSError("simulated run-end audit failure")

            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "event": event,
                    **fields,
                }) + "\n")

        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch("vcan_replay.socket.socket", return_value=fake_socket),
            patch("vcan_replay.time.monotonic", return_value=0),
            patch("vcan_replay.time.sleep"),
            patch(
                "vcan_replay.write_audit",
                side_effect=simulated_audit,
            ),
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 1)
        self.assertEqual(fake_socket.sendall.call_count, 121)
        fake_socket.close.assert_called_once()

    def test_socket_failure_returns_error(self):
        with (
            patch("vcan_replay.check_vcan0", return_value=True),
            patch(
                "vcan_replay.socket.socket",
                side_effect=OSError("simulated socket failure"),
            ),
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=True,
            )

        self.assertEqual(result, 1)

    def test_missing_vcan0_rejected(self):
        with (
            patch(
                "vcan_replay.check_vcan0",
                side_effect=RuntimeError("vcan0 unavailable"),
            ),
            patch("vcan_replay.socket.socket") as socket_mock,
        ):
            result = run(
                self.csv_path,
                self.audit_path,
                execute=False,
            )

        self.assertEqual(result, 1)
        socket_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
