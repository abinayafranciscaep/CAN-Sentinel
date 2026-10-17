#!/usr/bin/env python3
"""Validate synthetic raw CAN data against its injection log."""

import csv
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "logs" / "synthetic_fixture"
RAW_PATH = BASE / "synthetic_raw.csv"
INJECTION_PATH = BASE / "synthetic_injection_log.csv"

RAW_FIELDS = ["timestamp", "can_id", "dlc", "data_hex", "label"]
INJECTION_FIELDS = ["timestamp", "can_id", "data_hex"]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


class DatasetHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_header, cls.raw_rows = read_csv(RAW_PATH)
        cls.injection_header, cls.injection_rows = read_csv(INJECTION_PATH)

    def test_csv_headers_match_contract(self):
        self.assertEqual(self.raw_header, RAW_FIELDS)
        self.assertEqual(self.injection_header, INJECTION_FIELDS)

    def test_expected_synthetic_record_counts(self):
        self.assertEqual(len(self.raw_rows), 5)
        self.assertEqual(len(self.injection_rows), 2)

    def test_raw_dataset_contains_expected_labels(self):
        labels = [row["label"] for row in self.raw_rows]
        self.assertEqual(labels.count("normal"), 3)
        self.assertEqual(labels.count("spoof_brake"), 2)

    def test_each_injection_matches_a_raw_attack_record(self):
        raw_attack_records = {
            (row["timestamp"], row["can_id"], row["data_hex"])
            for row in self.raw_rows
            if row["label"] == "spoof_brake"
        }
        injection_records = {
            (row["timestamp"], row["can_id"], row["data_hex"])
            for row in self.injection_rows
        }
        self.assertEqual(injection_records, raw_attack_records)

    def test_timestamps_are_ordered_and_unique(self):
        timestamps = [float(row["timestamp"]) for row in self.raw_rows]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertEqual(len(timestamps), len(set(timestamps)))

    def test_records_have_valid_basic_frame_fields(self):
        for row in self.raw_rows:
            self.assertRegex(row["can_id"], r"^0x[0-7][0-9A-F]{2}$")
            self.assertEqual(int(row["dlc"]), 8)
            self.assertEqual(len(row["data_hex"]), 16)
            self.assertRegex(row["data_hex"], r"^[0-9A-F]+$")


if __name__ == "__main__":
    unittest.main()
