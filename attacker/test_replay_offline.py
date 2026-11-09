#!/usr/bin/env python3
"""Tests for offline recorded-CAN CSV validation."""

import csv
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from replay_offline import read_recording

FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]


class ReplayOfflineTests(unittest.TestCase):
    def write_csv(self, directory, rows, fields=FIELDS):
        path = Path(directory) / "recording.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fields})
        return path

    def valid_row(self, **overrides):
        row = {
            "timestamp": "1791300000.123456",
            "can_id": "0x0A0",
            "dlc": "8",
            "data_hex": "3201000000000017",
            "label": "normal",
        }
        row.update(overrides)
        return row

    def test_valid_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                [self.valid_row(), self.valid_row(
                    timestamp="1791300000.133456"
                )],
            )
            records = read_recording(path)
            self.assertEqual(len(records), 2)

    def test_wrong_header_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory,
                [self.valid_row()],
                fields=["timestamp", "can_id", "data_hex"],
            )
            with self.assertRaisesRegex(ValueError, "CSV header"):
                read_recording(path)

    def test_invalid_dlc_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory, [self.valid_row(dlc="7")]
            )
            with self.assertRaisesRegex(ValueError, "payload length"):
                read_recording(path)

    def test_invalid_can_id_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory, [self.valid_row(can_id="0xZZZ")]
            )
            with self.assertRaisesRegex(ValueError, "CAN ID"):
                read_recording(path)

    def test_out_of_order_timestamps_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [
                self.valid_row(timestamp="1791300000.200000"),
                self.valid_row(timestamp="1791300000.100000"),
            ]
            path = self.write_csv(directory, rows)
            with self.assertRaisesRegex(ValueError, "non-decreasing"):
                read_recording(path)


    def test_empty_recording_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(directory, [])
            with self.assertRaisesRegex(ValueError, "at least one data row"):
                read_recording(path)

    def test_nan_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory, [self.valid_row(timestamp="NaN")]
            )
            with self.assertRaisesRegex(ValueError, "timestamp must be finite"):
                read_recording(path)

    def test_infinite_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_csv(
                directory, [self.valid_row(timestamp="Infinity")]
            )
            with self.assertRaisesRegex(ValueError, "timestamp must be finite"):
                read_recording(path)


    def test_jsonl_export_contains_valid_records(self):
        import json
        from replay_offline import main

        with tempfile.TemporaryDirectory() as directory:
            input_path = self.write_csv(directory, [self.valid_row()])
            output_path = Path(directory) / "output" / "validated.jsonl"

            with patch(
                "sys.argv",
                ["replay_offline.py", str(input_path), "--output", str(output_path)],
            ):
                result = main()

            self.assertEqual(result, 0)
            records = [
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["can_id"], "0x0A0")
            self.assertEqual(records[0]["label"], "normal")

    def test_jsonl_export_write_failure_returns_error(self):
        from replay_offline import main

        with tempfile.TemporaryDirectory() as directory:
            input_path = self.write_csv(directory, [self.valid_row()])
            output_path = Path(directory) / "blocked.jsonl"

            with (
                patch(
                    "sys.argv",
                    ["replay_offline.py", str(input_path), "--output", str(output_path)],
                ),
                patch.object(Path, "open", side_effect=OSError("simulated write failure")),
            ):
                result = main()

            self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
