"""
CAN-Sentinel: unit tests for the live detector's socket input.

Run from the repository root:
    python -m pytest ml_engine -q

Author: Abinaya Francisca EP (Team Lead)
"""

import os
import socket
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from live_detector import frames_from_socket, parse_line, split_lines  # noqa: E402

GOOD = '{"timestamp": 1793382184.865339, "can_id": "0x100", "dlc": 8, "data_hex": "0A5A00000000004F"}'


def test_parse_valid_frame():
    frame = parse_line(GOOD)
    assert frame["can_id"] == "0x100" and frame["dlc"] == 8
    assert isinstance(frame["timestamp"], float)


def test_parse_skips_bad_lines():
    assert parse_line("") is None
    assert parse_line('{"timestamp": 1.0, "can_id": "0x1') is None   # cut off
    assert parse_line('{"timestamp": 1.0, "can_id": "0x100"}') is None  # missing fields
    assert parse_line("hello") is None


def test_split_lines_keeps_partial_line():
    lines, rest = split_lines("", GOOD + "\n" + GOOD[:20])
    assert lines == [GOOD] and rest == GOOD[:20]
    lines, rest = split_lines(rest, GOOD[20:] + "\n")
    assert lines == [GOOD] and rest == ""


@pytest.mark.skipif(sys.platform == "win32" or not hasattr(socket, "AF_UNIX"),
                    reason="Unix domain sockets need Linux (vcan0 setup); skipped on Windows")
def test_socket_stream_skips_bad_line():
    path = os.path.join(tempfile.mkdtemp(), "test.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)

    def sniffer():
        conn, _ = server.accept()
        conn.sendall((GOOD + "\nnot json\n" + GOOD + "\n").encode())
        conn.close()

    threading.Thread(target=sniffer, daemon=True).start()
    frames = list(frames_from_socket(path, retries=3, wait=0.1, reconnect=False))
    server.close()
    assert len(frames) == 2
