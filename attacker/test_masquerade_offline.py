#!/usr/bin/env python3
"""Unit tests for offline synthetic masquerade records."""

import csv
import tempfile
import unittest
from pathlib import Path

from masquerade_offline import FIELDS, generate_cases, write_cases


class MasqueradeOfflineTests(unittest.TestCase):

    def test_expected_number_of_records(self):
        self.assertEqual(len(generate_cases()), 6)

    def test_expected_labels_and_order(self):
        records = generate_cases()
        labels = [row["label"] for row in records]
        self.assertEqual(
            labels,
            ["normal", "normal", "normal",
             "masquerade", "masquerade", "masquerade"],
        )

    def test_gap_is_larger_than_normal_interval(self):
        records = generate_cases()
        timestamps = [float(row["timestamp"]) for row in records]
        intervals = [
            timestamps[i] - timestamps[i - 1]
            for i in range(1, len(timestamps))
        ]
        self.assertAlmostEqual(intervals[0], 0.02, places=5)
        self.assertAlmostEqual(intervals[1], 0.02, places=5)
        self.assertGreater(intervals[2], intervals[1] * 2)

    def test_frame_format_is_consistent(self):
        for row in generate_cases():
            self.assertEqual(row["can_id"], "0x0A0")
            self.assertEqual(row["dlc"], 8)
            self.assertEqual(len(row["data_hex"]), row["dlc"] * 2)
            self.assertTrue(
                all(c in "0123456789ABCDEF" for c in row["data_hex"])
            )

    def test_csv_schema_and_written_rows(self):
        records = generate_cases()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "masquerade.csv"
            write_cases(path, records)

            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, FIELDS)
                rows = list(reader)

            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[3]["label"], "masquerade")


    def test_negative_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(start_timestamp=-1)

    def test_zero_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(start_timestamp=0)

    def test_nan_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(start_timestamp=float("nan"))

    def test_infinite_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(start_timestamp=float("inf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
