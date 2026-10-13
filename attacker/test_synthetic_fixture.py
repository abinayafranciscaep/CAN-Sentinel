#!/usr/bin/env python3
"""Validate offline synthetic CAN fixture CSV files."""

import csv
import unittest
from pathlib import Path

FIXTURE_DIR = Path("logs/synthetic_fixture")
RAW_FILE = FIXTURE_DIR / "synthetic_raw.csv"
INJECTION_FILE = FIXTURE_DIR / "synthetic_injection_log.csv"


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class SyntheticFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RAW_FILE.is_file() or not INJECTION_FILE.is_file():
            raise RuntimeError(
                "Fixture files missing. Run "
                "python3 attacker/generate_synthetic_fixture.py first."
            )

        cls.raw_rows = read_csv(RAW_FILE)
        cls.injection_rows = read_csv(INJECTION_FILE)

    def test_csv_headers(self):
        with RAW_FILE.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(
                next(csv.reader(handle)),
                ["timestamp", "can_id", "dlc", "data_hex", "label"],
            )

        with INJECTION_FILE.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(
                next(csv.reader(handle)),
                ["timestamp", "can_id", "data_hex"],
            )

    def test_expected_row_counts(self):
        self.assertEqual(len(self.raw_rows), 5)
        self.assertEqual(len(self.injection_rows), 2)

    def test_raw_frame_format(self):
        for row in self.raw_rows:
            self.assertEqual(row["can_id"], "0x0A0")
            self.assertEqual(int(row["dlc"]), 8)
            self.assertEqual(len(row["data_hex"]), 16)
            self.assertTrue(
                all(char in "0123456789ABCDEF" for char in row["data_hex"])
            )
            self.assertIn(row["label"], {"normal", "spoof_brake"})
            self.assertEqual(f'{float(row["timestamp"]):.6f}', row["timestamp"])

    def test_injection_events_match_raw_rows(self):
        raw_events = {
            (row["timestamp"], row["can_id"], row["data_hex"])
            for row in self.raw_rows
            if row["label"] == "spoof_brake"
        }
        logged_events = {
            (row["timestamp"], row["can_id"], row["data_hex"])
            for row in self.injection_rows
        }

        self.assertEqual(len(logged_events), len(self.injection_rows))
        self.assertEqual(logged_events, raw_events)

    def test_all_timestamps_are_numeric(self):
        for row in self.raw_rows + self.injection_rows:
            self.assertGreater(float(row["timestamp"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
