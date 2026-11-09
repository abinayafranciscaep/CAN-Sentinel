
#!/usr/bin/env python3
"""Unit tests for the CAN-Sentinel attacker framework."""

import contextlib
import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("attacker.py")

SPEC = importlib.util.spec_from_file_location(
    "attacker_framework",
    MODULE_PATH,
)

framework = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(framework)


class AttackerFrameworkTests(unittest.TestCase):

    # ---------------------------------------------------------
    # Flood validation and dry-run tests
    # ---------------------------------------------------------

    def test_valid_duration_and_rate_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "flood.jsonl"

            with patch.object(
                framework, "check_interface", return_value=True
            ):
                result = framework.run_flood(2, 10, False, log)

            self.assertEqual(result, 0)
            self.assertTrue(log.exists())

    def test_zero_duration_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                0, 10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_excessive_duration_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                6, 10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_excessive_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, 101, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_zero_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, 0, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_wrong_interface_rejected(self):
        self.assertFalse(framework.check_interface("can0"))

    def test_missing_interface_rejected(self):
        with patch.object(
            framework.subprocess,
            "run",
            return_value=type("Result", (), {"returncode": 1})(),
        ):
            self.assertFalse(framework.check_interface("vcan0"))

    # ---------------------------------------------------------
    # Audit logging tests
    # ---------------------------------------------------------

    def test_write_log_creates_valid_jsonl_record(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"

            result = framework.write_log(
                log,
                "test_event",
                interface="vcan0",
                frames_sent=5,
            )

            self.assertTrue(result)

            record = json.loads(log.read_text().strip())

            self.assertEqual(record["event"], "test_event")
            self.assertEqual(record["interface"], "vcan0")
            self.assertEqual(record["frames_sent"], 5)
            self.assertIn("timestamp", record)

    def test_write_log_returns_false_on_os_error(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)
            log.mkdir(exist_ok=True)

            result = framework.write_log(log, "test_event")

        self.assertFalse(result)

    def test_initial_log_failure_prevents_socket_creation(self):
        with (
            patch.object(framework, "check_interface", return_value=True),
            patch.object(framework, "write_log", return_value=False),
            patch.object(framework.socket, "socket") as socket_mock,
        ):
            result = framework.run_flood(
                1, 10, True, Path("/tmp/test_initial_failure.jsonl")
            )

        self.assertEqual(result, 1)
        socket_mock.assert_not_called()

    def test_frame_log_failure_stops_further_transmission(self):
        with (
            patch.object(framework, "check_interface", return_value=True),
            patch.object(
                framework,
                "write_log",
                side_effect=[True, False, True],
            ),
            patch.object(framework.socket, "socket") as socket_mock,
        ):
            mock_socket = socket_mock.return_value

            result = framework.run_flood(
                1, 10, True, Path("/tmp/test_frame_failure.jsonl")
            )

        self.assertEqual(result, 1)
        self.assertEqual(mock_socket.send.call_count, 1)
        mock_socket.close.assert_called_once()

    def test_final_log_failure_returns_error(self):
        with (
            patch.object(framework, "check_interface", return_value=True),
            patch.object(
                framework, "write_log", side_effect=[True, False]
            ),
        ):
            result = framework.run_flood(
                1, 10, False, Path("/tmp/test_final_failure.jsonl")
            )

        self.assertEqual(result, 1)

    # ---------------------------------------------------------
    # Duration validation tests
    # ---------------------------------------------------------

    def test_negative_duration_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                -1, 10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_nan_duration_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                float("nan"), 10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_infinite_duration_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                float("inf"), 10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_boolean_duration_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                True, 10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    # ---------------------------------------------------------
    # Rate validation tests
    # ---------------------------------------------------------

    def test_negative_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, -10, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_boolean_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, True, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_float_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, 10.5, False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_nan_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, float("nan"), False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    def test_infinite_rate_rejected(self):
        with patch.object(framework, "check_interface", return_value=True):
            result = framework.run_flood(
                1, float("inf"), False, Path("/tmp/test.jsonl")
            )
        self.assertEqual(result, 1)

    # ---------------------------------------------------------
    # Socket failure tests
    # ---------------------------------------------------------

    def test_socket_creation_failure_returns_error(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "creation_failure.jsonl"

            with (
                patch.object(framework, "check_interface", return_value=True),
                patch.object(
                    framework.socket,
                    "socket",
                    side_effect=OSError(
                        "simulated socket creation failure"
                    ),
                ),
            ):
                result = framework.run_flood(1, 10, True, log)

            self.assertEqual(result, 1)

            records = [
                json.loads(line)
                for line in log.read_text().splitlines()
            ]

            self.assertEqual(records[-1]["status"], "error")

    def test_socket_bind_failure_closes_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "bind_failure.jsonl"

            with (
                patch.object(framework, "check_interface", return_value=True),
                patch.object(framework.socket, "socket") as socket_mock,
            ):
                mock_socket = socket_mock.return_value

                mock_socket.bind.side_effect = OSError(
                    "simulated bind failure"
                )

                result = framework.run_flood(1, 10, True, log)

            self.assertEqual(result, 1)
            mock_socket.close.assert_called_once()

    # ---------------------------------------------------------
    # CLI helper
    # ---------------------------------------------------------

    def run_cli(self, arguments):
        output = io.StringIO()

        with (
            patch("sys.argv", ["attacker.py"] + arguments),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(output),
        ):
            result = framework.main()

        return result, output.getvalue()

    # ---------------------------------------------------------
    # Replay CLI tests
    # ---------------------------------------------------------

    def test_cli_replay_validates_and_exports_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "input.csv"
            output = Path(directory) / "output.jsonl"

            recording.write_text(
                "timestamp,can_id,dlc,data_hex,label\n"
                "1791300100.0,0x123,8,"
                "1122334455667788,normal\n"
            )

            result, _ = self.run_cli([
                "--attack", "replay",
                "--recording", str(recording),
                "--output", str(output),
            ])

            self.assertEqual(result, 0)
            self.assertTrue(output.exists())

            record = json.loads(output.read_text().strip())
            self.assertEqual(record["can_id"], "0x123")

    def test_cli_replay_requires_recording(self):
        with self.assertRaises(SystemExit) as error:
            self.run_cli(["--attack", "replay"])

        self.assertEqual(error.exception.code, 2)

    # ---------------------------------------------------------
    # Offline generator CLI tests
    # ---------------------------------------------------------

    def test_cli_fuzz_generates_requested_count(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fuzz.csv"

            result, _ = self.run_cli([
                "--attack", "fuzz",
                "--count", "25",
                "--seed", "42",
                "--output", str(output),
            ])

            self.assertEqual(result, 0)

            with output.open(newline="") as file:
                records = list(csv.DictReader(file))

            self.assertEqual(len(records), 25)

    def test_cli_masquerade_generates_six_records(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "masquerade.csv"

            result, _ = self.run_cli([
                "--attack", "masquerade",
                "--output", str(output),
            ])

            self.assertEqual(result, 0)

            with output.open(newline="") as file:
                records = list(csv.DictReader(file))

            self.assertEqual(len(records), 6)

    def test_cli_spoof_brake_generates_synthetic_records(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "spoof.csv"

            result, _ = self.run_cli([
                "--attack", "spoof_brake",
                "--output", str(output),
            ])

            self.assertEqual(result, 0)

            with output.open(newline="") as file:
                records = list(csv.DictReader(file))

            self.assertEqual(len(records), 3)
            self.assertTrue(
                all("synthetic" in row["label"] for row in records)
            )

    def test_cli_diag_abuse_generates_synthetic_records(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "diag.csv"

            result, _ = self.run_cli([
                "--attack", "diag_abuse",
                "--output", str(output),
            ])

            self.assertEqual(result, 0)

            with output.open(newline="") as file:
                records = list(csv.DictReader(file))

            self.assertEqual(len(records), 3)
            self.assertTrue(
                all("synthetic" in row["label"] for row in records)
            )

    # ---------------------------------------------------------
    # Offline safety tests
    # ---------------------------------------------------------

    def test_offline_attacks_never_open_can_socket(self):
        cases = [
            ["--attack", "fuzz"],
            ["--attack", "masquerade"],
            ["--attack", "spoof_brake"],
            ["--attack", "diag_abuse"],
        ]

        for arguments in cases:
            with self.subTest(arguments=arguments):
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory) / "output.csv"
                    args = arguments + ["--output", str(output)]

                    with patch.object(
                        framework.socket,
                        "socket",
                        side_effect=AssertionError(
                            "Offline mode must not open a CAN socket"
                        ),
                    ):
                        result, _ = self.run_cli(args)

                    self.assertEqual(result, 0)
                    self.assertTrue(output.exists())

    def test_offline_attack_execute_flag_is_rejected(self):
        for attack in (
            "replay",
            "fuzz",
            "masquerade",
            "spoof_brake",
            "diag_abuse",
        ):
            with self.subTest(attack=attack):
                arguments = ["--attack", attack, "--execute"]

                if attack == "replay":
                    with tempfile.TemporaryDirectory() as directory:
                        recording = Path(directory) / "input.csv"

                        recording.write_text(
                            "timestamp,can_id,dlc,data_hex,label\n"
                            "1791300100.0,0x123,8,"
                            "1122334455667788,normal\n"
                        )

                        arguments += ["--recording", str(recording)]

                        with self.assertRaises(SystemExit) as error:
                            self.run_cli(arguments)

                else:
                    with self.assertRaises(SystemExit) as error:
                        self.run_cli(arguments)

                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

