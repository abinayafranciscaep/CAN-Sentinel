"""
CAN-Sentinel: unit tests for rules.py and alerts.py.

Run from the repository root:
    python -m pytest ml_engine -q

Author: Abinaya Francisca EP (Team Lead)
"""

import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alerts import make_alert, most_severe, to_json_line  # noqa: E402
from rules import check_window  # noqa: E402

PERIODS = {"0x0A0": 0.020, "0x0B0": 0.010, "0x100": 0.010,
           "0x200": 0.020, "0x300": 0.100, "0x600": 0.100}
ALERT_FIELDS = {"timestamp", "attack_type", "suspect_id", "confidence", "severity",
                "affected_system", "detection_layer", "technique"}


def window(extra=None, skip_id=None):
    rows = []
    for can_id, period in PERIODS.items():
        t = 0.0
        while t < 1.0:
            if not (skip_id == can_id and 0.2 < t < 0.6):
                rows.append({"timestamp": t, "can_id": can_id, "dlc": 8,
                             "data_hex": "3201000000000017"})
            t += period
    rows += extra or []
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    df["dlc_mismatch"] = (df["data_hex"].str.len() != df["dlc"] * 2).astype(int)
    return df


def attack_types(findings):
    return {f["attack_type"] for f in findings}


def test_normal_window_has_no_findings():
    assert check_window(window(), 1.0) == []


def test_flood_detected():
    flood = [{"timestamp": i / 2000, "can_id": "0x000", "dlc": 8,
              "data_hex": "0000000000000000"} for i in range(2000)]
    findings = check_window(window(flood), 1.0)
    assert "flood" in attack_types(findings)
    assert findings[0]["suspect_id"] == "0x000"


def test_fuzz_detected():
    fuzz = [{"timestamp": i / 100, "can_id": f"0x{0x400 + i:03X}", "dlc": 8,
             "data_hex": "A1B2C3D4E5F60718"} for i in range(30)]
    assert "fuzz" in attack_types(check_window(window(fuzz), 1.0))


def test_spoof_brake_detected():
    spoof = [{"timestamp": i * 0.02 + 0.01, "can_id": "0x0A0", "dlc": 8,
              "data_hex": "64FF000000000000"} for i in range(50)]
    findings = check_window(window(spoof), 1.0)
    assert any(f["attack_type"] == "spoof_brake" and f["suspect_id"] == "0x0A0"
               for f in findings)


def test_masquerade_gap_detected():
    findings = check_window(window(skip_id="0x0B0"), 1.0)
    assert any(f["attack_type"] == "masquerade" and f["suspect_id"] == "0x0B0"
               for f in findings)


def test_diagnostic_abuse_detected():
    diag = [{"timestamp": 0.5, "can_id": "0x7DF", "dlc": 8, "data_hex": "0210030000000000"}]
    assert "diag_abuse" in attack_types(check_window(window(diag), 1.0))


def test_dlc_mismatch_detected():
    bad = [{"timestamp": 0.5, "can_id": "0x200", "dlc": 8, "data_hex": "0102"}]
    assert "fuzz" in attack_types(check_window(window(bad), 1.0))


def test_alert_matches_schema():
    alert = make_alert(1791300042.5, "spoof_brake", "0x0A0", 0.94, "rules")
    assert set(alert) == ALERT_FIELDS
    assert alert["severity"] == "critical"
    assert alert["affected_system"] == "brake"
    assert alert["technique"] == "T0855"
    assert json.loads(to_json_line(alert)) == alert


def test_flood_alert_is_bus_wide():
    alert = make_alert(1.0, "flood", "0x000", 0.9, "rules")
    assert alert["affected_system"] == "bus"
    assert alert["severity"] == "high"


def test_most_severe_picks_critical():
    alerts = [make_alert(1.0, "flood", "0x000", 0.99, "rules"),
              make_alert(1.0, "spoof_brake", "0x0A0", 0.6, "rules")]
    assert most_severe(alerts)["attack_type"] == "spoof_brake"
