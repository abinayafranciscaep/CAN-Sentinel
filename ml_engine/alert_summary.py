"""
CAN-Sentinel: incident summary from an alerts file.

The detector writes one alert per detection, so one attack produces several
alerts. This tool groups them into incidents (same attack type and suspect CAN
ID, with no more than 10 s between alerts) and prints the incident log used in
docs/incident_response_playbook.md (Section 5), with the playbook section the
analyst should follow for each incident.

Usage (from the repository root):
    python ml_engine/alert_summary.py alerts.jsonl
    python ml_engine/alert_summary.py results_run1.jsonl --md docs/incidents_run1.md

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
from datetime import datetime, timezone

from alerts import SEVERITY_ORDER
from evaluate_alerts import read_alerts

INCIDENT_GAP_SECONDS = 10.0
BUS_WIDE = ("flood", "fuzz")  # changing IDs: one incident for the whole bus

PLAYBOOK_SECTION = {
    "flood": "3.1", "spoof_brake": "3.2", "replay": "3.3", "fuzz": "3.4",
    "masquerade": "3.5", "diag_abuse": "3.6", "unknown_anomaly": "3.7",
}


def group_incidents(alerts, gap=INCIDENT_GAP_SECONDS):
    """Group alerts into incidents, oldest first."""
    open_incidents, incidents = {}, []
    for a in sorted(alerts, key=lambda x: x["timestamp"]):
        key = (a["attack_type"], "bus" if a["attack_type"] in BUS_WIDE else a["suspect_id"])
        inc = open_incidents.get(key)
        if inc is None or a["timestamp"] - inc["end"] > gap:
            inc = {"attack_type": key[0], "suspect_id": key[1], "start": a["timestamp"],
                   "end": a["timestamp"], "alerts": 0, "severity": "low", "confidence": 0.0,
                   "layers": set(), "technique": a.get("technique", ""),
                   "affected_system": a.get("affected_system", "")}
            open_incidents[key] = inc
            incidents.append(inc)
        inc["end"] = a["timestamp"]
        inc["alerts"] += 1
        if SEVERITY_ORDER.index(a["severity"]) > SEVERITY_ORDER.index(inc["severity"]):
            inc["severity"] = a["severity"]
        inc["confidence"] = max(inc["confidence"], a["confidence"])
        inc["layers"].add(a["detection_layer"])
    return incidents


def clock(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def to_markdown(path, incidents):
    lines = [f"Incident log from `{path}`: {len(incidents)} incident(s)", "",
             "| # | Start | Duration | Attack | Suspect ID | System | Severity | Alerts | Max confidence | Layers | ATT&CK | Playbook |",
             "|---:|---|---:|---|---|---|---|---:|---:|---|---|---|"]
    for i, inc in enumerate(incidents, 1):
        lines.append(
            f"| {i} | {clock(inc['start'])} | {inc['end'] - inc['start']:.1f} s | {inc['attack_type']} | "
            f"{inc['suspect_id']} | {inc['affected_system']} | {inc['severity']} | {inc['alerts']} | "
            f"{inc['confidence']:.2f} | {', '.join(sorted(inc['layers']))} | {inc['technique'] or '-'} | "
            f"Section {PLAYBOOK_SECTION.get(inc['attack_type'], '2')} |")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="CAN-Sentinel incident summary")
    p.add_argument("alerts_jsonl", help="alerts written by detect.py or live_detector.py")
    p.add_argument("--gap", type=float, default=INCIDENT_GAP_SECONDS,
                   help="seconds between alerts that still count as one incident")
    p.add_argument("--md", help="also write the incident log to this Markdown file")
    a = p.parse_args()

    incidents = group_incidents(read_alerts(a.alerts_jsonl), a.gap)
    text = to_markdown(a.alerts_jsonl, incidents)
    print(text)
    if a.md:
        with open(a.md, "w") as f:
            f.write(text + "\n")
        print(f"\nWritten to {a.md}")


if __name__ == "__main__":
    main()
