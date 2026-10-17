"""
CAN-Sentinel: alert builder.

Turns a detection into the alert JSON agreed in docs/week1_design.md
(Section 5.3), which the PyQt dashboard reads. Every alert carries the
attack type, suspect CAN ID, confidence, severity, affected system,
the detection layer that fired and the MITRE ATT&CK for ICS technique.

Author: Abinaya Francisca EP (Team Lead)
"""

import json

AFFECTED_SYSTEM = {
    "0x0A0": "brake", "0x0B0": "steering", "0x100": "engine", "0x200": "speed",
    "0x300": "temperature", "0x600": "infotainment", "0x7DF": "diagnostics",
}

# Severity guide from the design doc: brake/steering critical, RPM/speed/
# diagnostics/bus-wide high, temperature medium, infotainment low.
SYSTEM_SEVERITY = {
    "brake": "critical", "steering": "critical", "engine": "high", "speed": "high",
    "diagnostics": "high", "bus": "high", "temperature": "medium", "infotainment": "low",
}

# ATT&CK for ICS techniques from the threat register (to be verified at attack.mitre.org)
TECHNIQUE = {
    "spoof_brake": "T0855", "replay": "T0855", "masquerade": "T0856",
    "fuzz": "T0836", "flood": "T0814", "diag_abuse": "T0858", "unknown_anomaly": "",
}

SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def affected_system(attack_type, suspect_id):
    if attack_type in ("flood", "fuzz") and suspect_id not in AFFECTED_SYSTEM:
        return "bus"
    return AFFECTED_SYSTEM.get(suspect_id, "bus")


def make_alert(timestamp, attack_type, suspect_id, confidence, detection_layer):
    system = affected_system(attack_type, suspect_id)
    return {
        "timestamp": round(float(timestamp), 6),
        "attack_type": attack_type,
        "suspect_id": suspect_id or "unknown",
        "confidence": round(float(confidence), 2),
        "severity": SYSTEM_SEVERITY.get(system, "medium"),
        "affected_system": system,
        "detection_layer": detection_layer,
        "technique": TECHNIQUE.get(attack_type, ""),
    }


def to_json_line(alert):
    """One alert per line (newline-delimited JSON) for the dashboard."""
    return json.dumps(alert, separators=(",", ":"))


def most_severe(alerts):
    """Pick the alert the dashboard's threat gauge should show."""
    if not alerts:
        return None
    return max(alerts, key=lambda a: (SEVERITY_ORDER.index(a["severity"]), a["confidence"]))
