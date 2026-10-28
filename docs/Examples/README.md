# ML Engine Output Examples

Author: Abinaya Francisca EP (Team Lead)

This folder holds real output from the CAN-Sentinel ML engine, for reference and for
integrating the PyQt dashboard. These are detector results, not hand-written samples.

## Files

| File | What it is |
|---|---|
| `engine_alerts_synthetic_run.jsonl` | 40 alerts produced by `ml_engine/live_detector.py` replaying the synthetic six-attack file (`generate_test_traffic.py all`). Covers flood, spoof_brake, replay, fuzz, masquerade and diag_abuse. |

The traffic in this run is simulated, so the alerts are real detector output on
synthetic data. Final results come from the team's recorded datasets.

## How alerts are produced

| Mode | Command (from the repository root) | Output |
|---|---|---|
| Live, from the sniffer socket | `python ml_engine/live_detector.py --alerts alerts.jsonl` | Appends to `alerts.jsonl` |
| Replay of a recorded CSV | `python ml_engine/live_detector.py --replay data/<file>.csv --alerts alerts.jsonl` | Appends to `alerts.jsonl` |
| Offline batch | `python ml_engine/detect.py data/<file>.csv --out results/<file>_alerts.jsonl` | Writes a new file |

`train_model.py` only trains and evaluates the model; its window-level output is not
meant for the dashboard.

## Alert format

One JSON object per line (design document, Section 5.3):

```json
{"timestamp":1791300045.667,"attack_type":"spoof_brake","suspect_id":"0x0A0","confidence":0.74,"severity":"critical","affected_system":"brake","detection_layer":"rules","technique":"T0855"}
```

| Field | Type | Values |
|---|---|---|
| `timestamp` | float | CAN frame time in seconds; matches CSV timestamps in replay mode |
| `attack_type` | string | flood, spoof_brake, replay, fuzz, masquerade, diag_abuse, unknown_anomaly |
| `suspect_id` | string | CAN ID such as `0x0A0`, or `bus` when no single ID is responsible |
| `confidence` | float | 0.0 to 1.0 |
| `severity` | string | low, medium, high, critical |
| `affected_system` | string | brake, steering, engine, speed, temperature, infotainment, diagnostics, bus |
| `detection_layer` | string | rules, statistics, isolation_forest |
| `technique` | string | MITRE ATT&CK for ICS ID (for example T0855); empty for unknown_anomaly |

Severity follows the affected system: brake and steering are critical; engine, speed,
diagnostics and bus-wide attacks are high; temperature is medium; infotainment is low.

## Reading alerts in the dashboard

- Read only new lines every 0.5 to 1 second, remembering the file position.
- Skip blank or malformed lines without stopping; the file may not exist until the first alert.
- Threat level: the most severe alert in the last 10 seconds; with no alerts for 10 seconds, show no active threat.
- Keep sample alerts (`dashboard/sample_alerts.jsonl`) clearly labelled as samples and separate from `alerts.jsonl`.
- The dashboard is display-only and never sends frames to the CAN bus.
