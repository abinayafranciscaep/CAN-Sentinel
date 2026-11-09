#!/usr/bin/env python3
"""Unit tests for offline synthetic CAN fuzz case generation."""

import csv
import tempfile
import unittest
from pathlib import Path

from fuzz_offline import FIELDS, generate_cases, write_cases


class FuzzOfflineTests(unittest.TestCase):

    def test_default_generation_count(self):
        self.assertEqual(len(generate_cases()), 20)

    def test_same_seed_produces_same_cases(self):
        self.assertEqual(
            generate_cases(count=20, seed=42),
            generate_cases(count=20, seed=42),
        )

    def test_different_seeds_produce_different_cases(self):
        self.assertNotEqual(
            generate_cases(count=20, seed=42),
            generate_cases(count=20, seed=43),
        )

    def test_invalid_counts_rejected(self):
        for count in (0, -1, 1001):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    generate_cases(count=count)

    def test_can_ids_are_standard_11_bit_ids(self):
        for record in generate_cases(count=100):
            can_id = record["can_id"]
            self.assertEqual(len(can_id), 5)
            self.assertTrue(can_id.startswith("0x"))
            self.assertLessEqual(int(can_id[2:], 16), 0x7FF)

    def test_dlc_matches_payload_length(self):
        for record in generate_cases(count=100):
            self.assertGreaterEqual(record["dlc"], 0)
            self.assertLessEqual(record["dlc"], 8)
            self.assertEqual(
                len(record["data_hex"]), record["dlc"] * 2
            )
            self.assertEqual(
                record["data_hex"], record["data_hex"].upper()
            )
            self.assertTrue(
                all(c in "0123456789ABCDEF"
                    for c in record["data_hex"])
            )

    def test_timestamps_increase_and_labels_are_fuzz(self):
        records = generate_cases(count=20)
        timestamps = [float(row["timestamp"]) for row in records]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertEqual(len(set(timestamps)), len(timestamps))
        self.assertTrue(all(row["label"] == "fuzz" for row in records))

    def test_csv_output_has_expected_schema(self):
        records = generate_cases(count=5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fuzz.csv"
            write_cases(path, records)

            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, FIELDS)
                rows = list(reader)

            self.assertEqual(len(rows), 5)
            self.assertTrue(all(row["label"] == "fuzz" for row in rows))


    def test_negative_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(count=2, start_timestamp=-1)

    def test_zero_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(count=2, start_timestamp=0)

    def test_nan_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(count=2, start_timestamp=float("nan"))

    def test_infinite_timestamp_rejected(self):
        with self.assertRaisesRegex(ValueError, "finite and positive"):
            generate_cases(count=2, start_timestamp=float("inf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
