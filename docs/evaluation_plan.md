# CAN-Sentinel: Detection Evaluation Plan

Author: Abinaya Francisca EP (Team Lead, Security Lead)
Status: Draft v1

This plan defines how we measure whether CAN-Sentinel works, per attack and
per detection layer, so the results in the final report are reproducible.

## 1. Questions we answer

1. Does each attack get detected, and how quickly?
2. How often does the system raise false alarms on normal traffic?
3. Which detection layer (rules, statistics, Isolation Forest) catches which attack?
4. Where are the blind spots?

## 2. Datasets

| Dataset | Runs | Duration | Source | Use |
|---|---|---|---|---|
| Normal | 3 | 10 min each | Logger (Member 3) on ECU simulators (Member 1) | Training (runs 1-2), false-alarm test (run 3) |
| flood | 3 | 2 min each | Attacker (Member 2) | Testing |
| spoof_brake | 3 | 2 min each | Attacker | Testing |
| replay | 3 | 2 min each | Attacker | Testing |
| fuzz | 3 | 2 min each | Attacker | Testing |
| masquerade | 3 | 2 min each | Attacker | Testing |
| diag_abuse | 3 | 2 min each | Attacker | Testing (if in scope) |

Rules:
- Each attack run starts with about 30 seconds of normal traffic so time-to-detect can be measured.
- Training never uses attack runs or the held-out normal run 3.
- Every CSV passes Member 3's validator before use.

## 3. Metrics

| Metric | Definition | Target |
|---|---|---|
| Window recall | Attack windows flagged / all attack windows | At least 0.90 for flood, spoof_brake, fuzz |
| Precision | Flagged attack windows / all flagged windows | At least 0.90 |
| False alarm rate | Alerts per minute on held-out normal traffic | Below 1 per 10 minutes |
| Time-to-detect | First alert during the attack minus first attack frame | Below 1 second |
| Attribution accuracy | Alerts naming the correct suspect CAN ID / all alerts during the attack | Report per attack |

## 4. Procedure

From the repository root:

1. Features: `python ml_engine/features.py data/<run>.csv data/features_<run>.csv`
2. Train on normal runs 1-2: `python ml_engine/train_model.py train data/features_normal_run1.csv data/features_normal_run2.csv`
3. Window metrics per attack run: `python ml_engine/train_model.py evaluate data/features_<attack>_run<N>.csv`
4. Alerts and time-to-detect: `python ml_engine/detect.py data/<attack>_run<N>.csv --out results/<attack>_run<N>.jsonl`
5. False alarms: `python ml_engine/detect.py data/normal_run3.csv --out results/normal_run3.jsonl` and count alerts
6. Unit tests before every evaluation: `python -m pytest ml_engine -q`

## 5. Results tables (to fill in Week 2-3)

### 5.1 Per attack

| Attack | Window recall | Time-to-detect (s) | Correct suspect ID | Main layer |
|---|---|---|---|---|
| flood | | | | |
| spoof_brake | | | | |
| replay | | | | |
| fuzz | | | | |
| masquerade | | | | |
| diag_abuse | | | | |

### 5.2 Normal traffic

| Run | Duration | Alerts | False alarms per 10 min |
|---|---|---|---|
| normal_run3 | 10 min | | |

### 5.3 Layer contribution

| Attack | Rules | Statistics | Isolation Forest |
|---|---|---|---|
| flood | | | |
| spoof_brake | | | |
| replay | | | |
| fuzz | | | |
| masquerade | | | |
| diag_abuse | | | |

## 6. Baseline from simulated traffic (development check)

Measured on simulated traffic while building the engine, before team datasets were available:

| Attack | Detected | Time-to-detect |
|---|---|---|
| flood | Yes | 0.5 s |
| spoof_brake | Yes | 0.5 s |
| fuzz | Yes | 0.5 s |
| diag_abuse | Yes | 0.5 s |
| masquerade (with timing gap) | Yes | 0.2 s |
| Normal traffic (2 min) | 0 false alarms | - |

These numbers are a sanity check only; the real results come from Section 5.

## 7. Known limitations to report

- Replay with valid payloads is hard to see without rolling counters or message authentication.
- Masquerade after a clean takeover (same rate and timing) may be invisible to timing features.
- The Isolation Forest alone is weak on values far outside training range; the statistics layer covers this.
- All tests run on a virtual bus (vcan0) with simulated ECUs, not real vehicle hardware.
