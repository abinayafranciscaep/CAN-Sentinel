#!/usr/bin/env python3
"""Tests for offline synthetic CAN scenario run generation."""

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from generate_attack_runs import (
    FIELDS,
    SCENARIOS,
    generate_run,
    write_run,
    main,
)


class AttackRunTests(unittest.TestCase):

    def test_all_scenarios_are_supported(self):
        self.assertEqual(
            set(SCENARIOS),
            {"spoof_brake", "replay", "fuzz", "masquerade", "diag_abuse"},
        )

    def test_two_minute_run_contains_121_records(self):
        for scenario in SCENARIOS:
            records, metadata = generate_run(
                scenario, 1, 120.0, 1.0, 42
            )
            with self.subTest(scenario=scenario):
                self.assertEqual(len(records), 121)
                self.assertEqual(metadata["record_count"], 121)
                self.assertEqual(metadata["duration_seconds"], 120.0)

    def test_timestamps_cover_zero_to_120_seconds(self):
        records, metadata = generate_run(
            "fuzz", 1, 120.0, 1.0, 42
        )
        timestamps = [float(row["timestamp"]) for row in records]

        self.assertAlmostEqual(timestamps[0], float(metadata["timestamp_start"]))
        self.assertAlmostEqual(timestamps[-1], float(metadata["timestamp_end"]))
        self.assertAlmostEqual(timestamps[-1] - timestamps[0], 120.0)

    def test_csv_schema_is_exact(self):
        records, _ = generate_run("replay", 1, 120.0, 1.0, 42)
        self.assertEqual(list(records[0].keys()), FIELDS)

    def test_labels_have_normal_baseline_and_scenario(self):
        for scenario in SCENARIOS:
            records, metadata = generate_run(
                scenario, 1, 120.0, 1.0, 42
            )
            labels = [row["label"] for row in records]

            with self.subTest(scenario=scenario):
                self.assertEqual(labels[0], "normal")
                self.assertIn(scenario, labels)
                self.assertEqual(
                    labels.count("normal"),
                    metadata["baseline_record_count"],
                )
                self.assertEqual(
                    labels.count(scenario),
                    metadata["scenario_record_count"],
                )

    def test_frame_fields_are_valid(self):
        for scenario in SCENARIOS:
            records, _ = generate_run(
                scenario, 1, 120.0, 1.0, 42
            )
            for row in records:
                with self.subTest(scenario=scenario, row=row):
                    self.assertEqual(row["can_id"], "0x0A0")
                    self.assertEqual(row["dlc"], "8")
                    self.assertEqual(len(row["data_hex"]), 16)
                    self.assertTrue(
                        all(c in "0123456789ABCDEF" for c in row["data_hex"])
                    )

    def test_same_seed_is_reproducible(self):
        first, first_meta = generate_run(
            "fuzz", 1, 120.0, 1.0, 42
        )
        second, second_meta = generate_run(
            "fuzz", 1, 120.0, 1.0, 42
        )
        self.assertEqual(first, second)
        self.assertEqual(first_meta, second_meta)

    def test_different_seeds_produce_different_payloads(self):
        first, _ = generate_run("fuzz", 1, 120.0, 1.0, 42)
        second, _ = generate_run("fuzz", 1, 120.0, 1.0, 43)
        self.assertNotEqual(
            [row["data_hex"] for row in first],
            [row["data_hex"] for row in second],
        )

    def test_run_ids_are_distinct(self):
        ids = set()
        for scenario in SCENARIOS:
            for run_number in range(1, 4):
                _, metadata = generate_run(
                    scenario, run_number, 120.0, 1.0, 42
                )
                ids.add(metadata["run_id"])
        self.assertEqual(len(ids), 15)

    def test_metadata_marks_data_synthetic_and_not_transmitted(self):
        _, metadata = generate_run(
            "spoof_brake", 1, 120.0, 1.0, 42
        )
        self.assertIs(metadata["synthetic"], True)
        self.assertIs(metadata["transmitted"], False)

    def test_invalid_scenario_rejected(self):
        with self.assertRaises(ValueError):
            generate_run("unknown", 1, 120.0, 1.0, 42)

    def test_invalid_run_number_rejected(self):
        for number in (0, -1, True):
            with self.subTest(number=number):
                with self.assertRaises(ValueError):
                    generate_run("fuzz", number, 120.0, 1.0, 42)

    def test_invalid_duration_rejected(self):
        for duration in (0, -1, float("nan"), float("inf")):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    generate_run("fuzz", 1, duration, 1.0, 42)

    def test_invalid_interval_rejected(self):
        for interval in (0, -1, float("nan"), float("inf")):
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    generate_run("fuzz", 1, 120.0, interval, 42)

    def test_invalid_duration_types_rejected(self):
        for duration in ("120", None, True):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    generate_run("fuzz", 1, duration, 1.0, 42)

    def test_invalid_interval_types_rejected(self):
        for interval in ("1", None, True):
            with self.subTest(interval=interval):
                with self.assertRaises(ValueError):
                    generate_run("fuzz", 1, 120.0, interval, 42)

    def test_invalid_seed_rejected(self):
        for seed in (-1, True, 1.5, "42", None):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    generate_run("fuzz", 1, 120.0, 1.0, seed)

    def test_non_divisible_duration_rejected(self):
        with self.assertRaisesRegex(ValueError, "exact multiple"):
            generate_run("fuzz", 1, 120.5, 1.0, 42)

    def test_excessive_record_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "100000"):
            generate_run("fuzz", 1, 100001.0, 1.0, 42)

    def test_write_run_creates_csv_and_metadata(self):
        records, metadata = generate_run(
            "masquerade", 1, 120.0, 1.0, 42
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path, metadata_path = write_run(
                Path(directory), "masquerade", 1, records, metadata
            )

            self.assertTrue(csv_path.is_file())
            self.assertTrue(metadata_path.is_file())

            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, FIELDS)
                self.assertEqual(len(list(reader)), 121)

            saved_metadata = json.loads(
                metadata_path.read_text(encoding="utf-8")
            )
            self.assertEqual(saved_metadata, metadata)

    def test_cli_generates_three_runs_for_each_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "sys.argv",
                [
                    "generate_attack_runs.py",
                    "--output-dir", directory,
                    "--runs", "3",
                    "--duration", "120",
                    "--interval", "1",
                ],
            ):
                result = main()

            self.assertIsNone(result)

            for scenario in SCENARIOS:
                for run_number in range(1, 4):
                    stem = f"run_{run_number:02d}"
                    run_dir = Path(directory) / scenario
                    self.assertTrue((run_dir / f"{stem}.csv").is_file())
                    self.assertTrue(
                        (run_dir / f"{stem}.metadata.json").is_file()
                    )

    def test_cli_rejects_invalid_run_count(self):
        with patch(
            "sys.argv",
            ["generate_attack_runs.py", "--runs", "0"],
        ):
            with self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
