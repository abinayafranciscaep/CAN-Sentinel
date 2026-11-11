"""
CAN-Sentinel: unit tests for gateway_client.py.

Run from the repository root:
    python -m pytest ml_engine -q

Author: Abinaya Francisca EP (Team Lead)
"""

import json
import os
import socket
import sys
import tempfile
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alerts import make_alert  # noqa: E402
from gateway_client import GatewayClient, decide_action  # noqa: E402


def test_spoof_and_replay_use_counter_mode():
    for attack in ("spoof_brake", "replay"):
        cmd = decide_action(make_alert(1.0, attack, "0x0A0", 0.9, "rules"))
        assert (cmd["type"], cmd["can_id"], cmd["mode"]) == ("quarantine", "0x0A0", "counter")
        assert cmd["alert"]["attack_type"] == attack and "T0855" in cmd["reason"]


def test_masquerade_and_diag_use_drop_mode():
    assert decide_action(make_alert(1.0, "masquerade", "0x0B0", 0.8, "rules"))["mode"] == "drop"
    cmd = decide_action(make_alert(1.0, "diag_abuse", "0x7DF", 0.7, "rules"))
    assert (cmd["can_id"], cmd["mode"]) == ("0x7DF", "drop")


def test_no_blocking_for_weak_or_unexplained_alerts():
    assert decide_action(make_alert(1.0, "unknown_anomaly", "0x0A0", 0.95, "statistics")) is None
    assert decide_action(make_alert(1.0, "spoof_brake", "0x0A0", 0.95, "isolation_forest")) is None
    assert decide_action(make_alert(1.0, "spoof_brake", "0x0A0", 0.5, "rules")) is None
    assert decide_action(make_alert(1.0, "masquerade", "0x600", 0.9, "rules")) is None  # low severity


def test_flood_on_unknown_id_left_to_allowlist():
    assert decide_action(make_alert(1.0, "flood", "0x000", 1.0, "rules")) is None
    assert decide_action(make_alert(1.0, "flood", "0x100", 1.0, "rules"))["mode"] == "drop"


def test_gateway_down_does_not_crash():
    client = GatewayClient(path=os.path.join(tempfile.mkdtemp(), "missing.sock"))
    assert client.send({"type": "status"}) is None


@pytest.mark.skipif(sys.platform == "win32" or not hasattr(socket, "AF_UNIX"),
                    reason="Unix domain sockets need Linux; skipped on Windows")
def test_command_and_reply_over_socket():
    path = os.path.join(tempfile.mkdtemp(), "gw.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(1)
    received = []

    def gateway():
        conn, _ = server.accept()
        line = conn.makefile().readline()
        received.append(json.loads(line))
        conn.sendall(b'{"type":"ack","ok":true,"can_id":"0x0A0","mode":"counter"}\n')
        conn.close()

    threading.Thread(target=gateway, daemon=True).start()
    cmd = decide_action(make_alert(1.0, "replay", "0x0A0", 0.9, "rules"))
    reply = GatewayClient(path=path, timeout=2).send(cmd)
    server.close()
    assert reply["ok"] and received[0]["mode"] == "counter"
