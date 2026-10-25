# CAN-Sentinel: ML Engine Integration Test (Week 2)

Author: Abinaya Francisca EP (Team Lead)
Date: Oct 24, 2026 (status updated Oct 25, 2026)

## Purpose

End-to-end check that every part of the ML engine works together on one machine:
feature extraction, training, the rules and statistics layers, the Isolation Forest,
alert output, time-to-detect, and the live detector in replay mode.

## Environment

| Item | Value |
|---|---|
| OS / terminal | Windows 11, MSYS2 UCRT64 terminal |
| Branch | lead |

## 1. Unit tests

Command: `python -m pytest ml_engine -q`

| Test file | Tests | Result |
|---|---:|---|
| `ml_engine/test_features.py` (feature extraction) | 5 | Passed |
| `ml_engine/test_rules_alerts.py` (rules layer and alert schema) | 10 | Passed |
| **Total** | **15** | **15 passed** |

Confirmed on the Windows 11 / MSYS2 UCRT64 laptop: `15 passed`. (`test_rules_alerts.py` was first uploaded to the repository root and was moved into `ml_engine/` on Oct 24, after which all 15 tests run together.)

## 2. Synthetic data (development check)

Simulated traffic from `ml_engine/generate_test_traffic.py`; used only to check the
pipeline, not as final results.

| Step | Command | Output |
|---|---|---|
| Normal traffic | `generate_test_traffic.py normal ... --seconds 120` | 38,404 frames |
| All six attacks | `generate_test_traffic.py all ...` | 61,394 frames, 23,991 attack frames |
| Training | `train_model.py train ...` | 239 normal windows, 34 features, threshold -0.5371 |
| False alarms on normal | `detect.py data/synthetic_normal.csv` | 0 alerts |
| Alerts on attacks | `detect.py data/synthetic_all_attacks.csv` | 44 alerts |
| Live detector (replay) | `live_detector.py --replay ...` | 40 alerts, all in the alert JSON schema |

Time to detect (from `detect.py` output):

| Attack | Time to detect |
|---|---|
| flood | 0.50 s |
| spoof_brake | 0.99 s |
| replay | 0.99 s |
| fuzz | 0.50 s |
| masquerade | 0.20 s |
| diag_abuse | 0.50 s |

## 3. Live detector alerts by attack phase (replay of the synthetic attack file)

| Attack phase | Main alert raised | Suspect ID | Layer | Correct? |
|---|---|---|---|---|
| flood (30-40 s) | flood | 0x000 | rules | Yes |
| spoof_brake (45-55 s) | spoof_brake | 0x0A0 | rules | Yes |
| replay (60-70 s) | spoof_brake | 0x0A0 | rules | Detected; named as spoof_brake |
| fuzz (75-85 s) | fuzz | random unknown IDs | rules | Yes |
| masquerade (90-100 s) | masquerade, then unknown_anomaly | 0x0B0, then mixed | rules, statistics | Detected; some later alerts name the wrong ID |
| diag_abuse (105-115 s) | diag_abuse | 0x7DF | rules | Yes |

No alerts were raised outside the attack phases.

## Observations

- Zero false alarms on 2 minutes of normal traffic; every attack detected within 1 second.
- The rules layer named the attack correctly for flood, spoof_brake, fuzz and diag_abuse.
- Replay was detected but labelled spoof_brake: both double the 0x0A0 rate, and the detector does not yet check the rolling counter, which is what tells them apart. Planned: a rolling-counter rule.
- During masquerade, some statistics-layer alerts named 0x0A0 or 0x200 instead of 0x0B0. Attribution for model-only alerts needs improvement.
- The first flood window raised a generic unknown_anomaly before the flood rule fired half a second later, because the window was only partly filled.
- These are simulated-data results; real recordings from the team are needed for the final evaluation.

## Status and next steps

| Item | Status |
|---|---|
| Feature extraction, training, rules, alerts, detector, live detector | Working end to end (this test) |
| Normal datasets from the ECU simulator (Member 1 + Member 3) | Recorded: Oct 16 (555,813 frames) and Oct 23 (554,399 frames). A timestamp-step issue was found in the Oct 16 recordings; a fresh official set with the final simulator and a fixed logger is being recorded |
| Labelled attack recordings (Member 2 + Member 3) | Synthetic attack fixtures and injection log ready; real vcan0 recordings in progress |
| Live input from the C sniffer over `/tmp/can_sentinel.sock` (Member 2) | In progress |
| Dashboard reading `alerts.jsonl` (Member 3) | In progress; sample alert file and format shared on Oct 24 |

Next: retrain on the official normal runs (runs 1-2 for training, run 3 for false-alarm testing), evaluate per attack on the real labelled attack runs, add a rolling-counter rule to separate replay from spoofing, and fill in `docs/evaluation_plan.md`.
