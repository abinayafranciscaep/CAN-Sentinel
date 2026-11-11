# ML Engine

Owner: Abinaya Francisca EP (Team Lead) | Branch: `lead`

The ML engine reads CAN traffic (a recorded CSV or the live sniffer socket), checks
it in one-second windows with three detection layers, and writes one alert JSON
line per detection for the dashboard.

## Detection layers

| Layer | What it checks | Strength |
|---|---|---|
| Rules (R1-R9) | Unknown IDs, DLC mismatch, diagnostic requests, per-ID rate, silent IDs, rolling counter, early frames | Fast; names the attack and the CAN ID |
| Statistics | Any of 34 window features outside its normal range (50% margin) | Large, obvious changes |
| Isolation Forest | Unusual combinations of features, trained on normal traffic only | Subtle changes; needs 2 abnormal windows in a row |

| Rule | Detects |
|---|---|
| R1 | Unknown ID; flood when the bus is above 2x its normal rate |
| R2 | Fuzzing: 5 or more unknown IDs in a window |
| R3 | Fuzzing: payload length does not match DLC |
| R4 | Diagnostic abuse: 0x7DF while driving |
| R5 | Spoofing: a baseline ID above 1.5x its normal rate |
| R6 | Masquerade: a baseline ID silent for 5 of its periods |
| R7 | Replay: extra frames carry their own valid counter sequence |
| R8 | Masquerade: normal rate but the real ECU's counter sequence is gone |
| R9 | Low-rate injection: frames arriving early with a broken counter while the real ECU still sends |

Alerts for the same attack and ID are not repeated within 2 seconds; flood and fuzz
alerts are grouped for the whole bus. See `docs/threat_detection_coverage.md` for how
each rule maps to the threat register, and `docs/gateway_design.md` for the planned
next step: blocking confirmed attacks at a security gateway.

## Files

| File | Purpose |
|---|---|
| `features.py` | CAN CSV -> one feature row per window (1 s window, 0.5 s step) |
| `train_model.py` | Train the statistics layer and Isolation Forest on normal traffic; window-level evaluation |
| `rules.py` | Rules R1-R9 |
| `alerts.py` | Alert JSON: severity, affected system, ATT&CK technique |
| `detect.py` | Offline detector over a CSV; prints time to detect |
| `live_detector.py` | Live detector on the sniffer socket (or `--replay` a CSV) |
| `evaluate_alerts.py` | Per-attack scores from the alerts: detection, time to detect, right type, right ID, false alarms |
| `retrain.py` | One command: data checks, features, training and false-alarm test on the official runs |
| `alert_summary.py` | Groups alerts into incidents with the playbook section to follow |
| `counter_check.py` | Rolling-counter check on a recording |
| `generate_test_traffic.py` | Synthetic normal and attack traffic for development tests (including `lowrate_spoof`) |
| `test_*.py` | Unit tests |

## Setup

Run every command from the repository root.

```
pip install -r ml_engine/requirements.txt
python -m pytest ml_engine -q
```

The tests should end with `32 passed` on Linux. On Windows the one socket test is skipped (`31 passed, 1 skipped`).

## Typical use

Train on the official normal runs (runs 1-2) and test false alarms on run 3:

```
python ml_engine/retrain.py --train data/normal_run1_MMDD.csv data/normal_run2_MMDD.csv --test data/normal_run3_MMDD.csv --report docs/retrain_report.md
```

It stops if a run has counter breaks, backward timestamps or a gap over 1 second.

Detect attacks in a recording and score the result:

```
python ml_engine/detect.py data/attacks_run1.csv --out results_run1.jsonl
python ml_engine/evaluate_alerts.py data/attacks_run1.csv --alerts results_run1.jsonl --md docs/results_run1.md
```

Live, with the sniffer running (waits for the sniffer, reconnects if it restarts):

```
python ml_engine/live_detector.py --alerts alerts.jsonl
```

Group the alerts into incidents (for the incident log in `docs/incident_response_playbook.md`):

```
python ml_engine/alert_summary.py alerts.jsonl --md docs/incidents.md
```

Replay a recording through the live code path:

```
python ml_engine/live_detector.py --replay data/attacks_run1.csv --alerts alerts.jsonl
```

## Input and output formats

CSV and socket input (`docs/week1_design.md`, Sections 5.1 and 5.2):

```
timestamp,can_id,dlc,data_hex,label
1791300000.123456,0x0A0,8,3201000000000017,normal
```

Alert output (Section 5.3), one JSON object per line:

```json
{"timestamp":1791300045.667,"attack_type":"replay","suspect_id":"0x0A0","confidence":0.9,"severity":"critical","affected_system":"brake","detection_layer":"rules","technique":"T0855"}
```

## Status

| Item | Status |
|---|---|
| Rules R1-R9, statistics layer, Isolation Forest | Done; tested on simulated data |
| Incident summary | Done |
| Security gateway (detect -> block) | Designed: `docs/gateway_design.md` (message format, blocking policy); gateway logic tested offline on simulated data, not yet live |
| Live detector on the sniffer socket | Done; live test with the sniffer pending |
| Evaluation and retraining tools | Done; waiting for the official recordings |
| Results on real team recordings | Pending: official normal runs and labelled attack runs |

Current simulated-data result: 6/6 attacks detected within 1 second (spoofing and
replay in 0.49 s), 0 false alarms, precision 1.0; low-rate spoofing also detected. Final results will come from the team's recordings.
