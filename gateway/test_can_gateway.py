"""
CAN-Sentinel: unit tests for the gateway's forwarding decisions.

Run: python3 -m pytest gateway -q

Reference tests by Abinaya Francisca EP (Team Lead) for Member 2.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from can_gateway import GatewayCore  # noqa: E402


def frame(counter, first=0x32):
    return bytes([first, 1, 0, 0, 0, 0, 0, counter])


def test_unknown_ids_never_forwarded():
    gw = GatewayCore()
    assert not gw.decide(0x000, frame(0), 0.0)
    assert not gw.decide(0x45B, frame(0), 0.0)
    assert gw.decide(0x0A0, frame(0), 0.0)
    assert gw.dropped == {"not_allowed": 2}


def test_counter_quarantine_keeps_real_frames_drops_fakes():
    gw = GatewayCore()
    t, counter = 0.0, 250
    gw.decide(0x0A0, frame(counter), t)
    gw.handle_command(
        {"type": "quarantine", "can_id": "0x0A0", "mode": "counter"}, t
    )

    passed_real = passed_fake = 0

    for i in range(1, 20):
        t += 0.010
        passed_fake += gw.decide(0x0A0, frame(0xFF, 0x64), t)

        t += 0.010
        passed_real += gw.decide(
            0x0A0, frame((counter + i) % 256), t
        )

    assert passed_real == 19
    assert passed_fake == 0


def test_counter_quarantine_drops_early_copy_of_next_counter():
    gw = GatewayCore()
    gw.decide(0x0A0, frame(10), 0.000)

    gw.handle_command(
        {"type": "quarantine", "can_id": "0x0A0", "mode": "counter"}, 0.0
    )

    assert not gw.decide(0x0A0, frame(11, 0x64), 0.007)
    assert gw.decide(0x0A0, frame(11), 0.020)


def test_counter_quarantine_tolerates_lost_frame_and_resyncs():
    gw = GatewayCore()

    gw.handle_command(
        {"type": "quarantine", "can_id": "0x0A0", "mode": "counter"}, 0.0
    )

    assert gw.decide(0x0A0, frame(10), 0.00)
    assert gw.decide(0x0A0, frame(12), 0.04)
    assert not gw.decide(0x0A0, frame(90), 0.05)
    assert gw.decide(0x0A0, frame(200), 0.50)


def test_drop_quarantine_and_expiry():
    gw = GatewayCore()

    reply, event = gw.handle_command(
        {
            "type": "quarantine",
            "can_id": "0x7DF",
            "mode": "drop",
            "duration_s": 5,
            "reason": "diag_abuse",
        },
        100.0,
    )

    assert reply["ok"] and event["event"] == "quarantine_start"
    assert not gw.decide(0x7DF, frame(0), 101.0)
    assert gw.expire(104.0) == []
    assert gw.expire(105.0)[0]["event"] == "quarantine_end"
    assert gw.decide(0x7DF, frame(0), 105.1)


def test_renew_and_release_and_bad_command():
    gw = GatewayCore()

    _, first = gw.handle_command(
        {"type": "quarantine", "can_id": "0x0B0", "mode": "drop"}, 0.0
    )

    reply, again = gw.handle_command(
        {"type": "quarantine", "can_id": "0x0B0", "mode": "drop"}, 1.0
    )

    assert first is not None and again is None and reply["renewed"]

    reply, event = gw.handle_command(
        {"type": "release", "can_id": "0x0B0"}, 2.0
    )

    assert reply["released"] and event["why"] == "released"

    reply, _ = gw.handle_command(
        {"type": "quarantine", "can_id": "0x0A0", "mode": "block"}, 0.0
    )

    assert not reply["ok"]
    assert gw.handle_command({"type": "status"}, 3.0)[0]["quarantined"] == []
