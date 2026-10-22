#!/usr/bin/env python3
"""Unit tests for the proposed CAN-Sentinel NDJSON message contract."""

import json
import re
import unittest

REQUIRED_FIELDS = {"timestamp", "can_id", "dlc", "data_hex"}


def validate_message(message):
    if not isinstance(message, dict):
        return False

    if set(message) != REQUIRED_FIELDS:
        return False

    timestamp = message["timestamp"]
    can_id = message["can_id"]
    dlc = message["dlc"]
    data_hex = message["data_hex"]

    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
        return False

    if not isinstance(can_id, str) or not re.fullmatch(r"0x[0-7][0-9A-F]{2}", can_id):
        return False

    if isinstance(dlc, bool) or not isinstance(dlc, int) or not 0 <= dlc <= 8:
        return False

    if not isinstance(data_hex, str):
        return False

    if len(data_hex) != dlc * 2:
        return False

    if not re.fullmatch(r"[0-9A-F]*", data_hex):
        return False

    return True


class SocketMessageValidationTests(unittest.TestCase):
    def setUp(self):
        self.valid_message = {
            "timestamp": 1791300000.123456,
            "can_id": "0x0A0",
            "dlc": 8,
            "data_hex": "3201000000000017",
        }

    def test_valid_frame_message(self):
        self.assertTrue(validate_message(self.valid_message))

    def test_json_line_ends_with_newline(self):
        encoded = (json.dumps(self.valid_message) + "\n").encode("utf-8")
        self.assertTrue(encoded.endswith(b"\n"))
        self.assertEqual(len(encoded.splitlines()), 1)
        self.assertEqual(json.loads(encoded.decode().strip()), self.valid_message)

    def test_label_is_not_part_of_socket_contract(self):
        self.assertNotIn("label", self.valid_message)

    def test_rejects_missing_field(self):
        message = dict(self.valid_message)
        del message["dlc"]
        self.assertFalse(validate_message(message))

    def test_rejects_extra_field(self):
        message = dict(self.valid_message, label="normal")
        self.assertFalse(validate_message(message))

    def test_rejects_invalid_can_id(self):
        for can_id in ("0xa0", "0x0GG", "0x800", "123"):
            with self.subTest(can_id=can_id):
                message = dict(self.valid_message, can_id=can_id)
                self.assertFalse(validate_message(message))

    def test_rejects_invalid_dlc(self):
        for dlc in (-1, 9, 1.5, True):
            with self.subTest(dlc=dlc):
                message = dict(self.valid_message, dlc=dlc)
                self.assertFalse(validate_message(message))

    def test_rejects_payload_length_mismatch(self):
        message = dict(self.valid_message, data_hex="AABB")
        self.assertFalse(validate_message(message))

    def test_rejects_non_hex_or_lowercase_payload(self):
        for payload in ("GG", "aa", "A A"):
            with self.subTest(payload=payload):
                message = dict(self.valid_message, dlc=len(payload) // 2, data_hex=payload)
                self.assertFalse(validate_message(message))

    def test_accepts_zero_length_payload(self):
        message = dict(self.valid_message, dlc=0, data_hex="")
        self.assertTrue(validate_message(message))


if __name__ == "__main__":
    unittest.main()
