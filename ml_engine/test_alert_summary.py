"""
CAN-Sentinel: unit tests for alert_summary.py.

Run from the repository root:
    python -m pytest ml_engine -q

Author: Abinaya Francisca EP (Team Lead)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alert_summary import group_incidents, to_markdown  # noqa: E402
from alerts import make_alert  # noqa: E402


def test_repeated_alerts_become_one_incident():
    alerts = [make_alert(t, "spoof_brake", "0x0A0", c, "rules") for t, c in ((100, 0.7), (102, 0.74), (104, 0.72))]
    incidents = group_incidents(alerts)
    assert len(incidents) == 1
    inc = incidents[0]
    assert (inc["alerts"], inc["start"], inc["end"]) == (3, 100, 104)
    assert inc["severity"] == "critical" and inc["confidence"] == 0.74


def test_gap_and_different_ids_split_incidents():
    alerts = [make_alert(100, "masquerade", "0x0B0", 0.8, "rules"),
              make_alert(130, "masquerade", "0x0B0", 0.8, "rules"),   # 30 s later
              make_alert(101, "unknown_anomaly", "0x200", 0.6, "statistics")]
    assert len(group_incidents(alerts)) == 3


def test_fuzz_with_changing_ids_is_one_incident():
    alerts = [make_alert(100 + i, "fuzz", f"0x{0x400 + i:03X}", 0.9, "rules") for i in range(5)]
    incidents = group_incidents(alerts)
    assert len(incidents) == 1 and incidents[0]["suspect_id"] == "bus"
    assert "Section 3.4" in to_markdown("x.jsonl", incidents)
