# CAN-Sentinel: ML Engine Integration Test (Week 2)

Author: Abinaya Francisca EP (Team Lead)
Date: Oct 24, 2026
Branch: lead

## Purpose

End-to-end check that every part of the ML engine works together on one machine:
feature extraction, training, the rules and statistics layers, the Isolation Forest,
alert output, time-to-detect, and the live detector in replay mode.

## Environment

| Item | Value |
|---|---|
| OS / terminal | FILL (for example Windows 11, MSYS2 UCRT64) |
| Python version | FILL (output of `python --version`) |
| Commit tested | FILL (output of `git log --oneline -1`) |

## 1. Unit tests

Command: `python -m pytest ml_engine -q`

| Result | Value |
|---|---|
| Tests passed | FILL (expected 15 passed) |

## 2. Synthetic data (development check)

Simulated traffic from `ml_engine/generate_test_traffic.py`; used only to check the
pipeline, not as final results.

| Step | Command | Output |
|---|---|---|
| Normal traffic | `generate_test_traffic.py normal ... --seconds 120` | FILL frames |
| All six attacks | `generate_test_traffic.py all ...` | FILL frames, FILL attack frames |
| Training | `train_model.py train ...` | FILL normal windows, FILL features |
| False alarms on normal | `detect.py data/synthetic_normal.csv` | FILL alerts |
| Alerts on attacks | `detect.py data/synthetic_all_attacks.csv` | FILL alerts |
| Live detector (replay) | `live_detector.py --replay ...` | FILL alerts |

Time to detect (from `detect.py` output):

| Attack | Time to detect |
|---|---|
| flood | FILL |
| spoof_brake | FILL |
| replay | FILL |
| fuzz | FILL |
| masquerade | FILL |
| diag_abuse | FILL |

## 3. Team stand-in dataset (Member 3)

`standin_normal_run1_1010.csv`, 10 minutes, recorded with the logger from the stand-in
sender (skip this section if the file is not available).

| Check | Result |
|---|---|
| Frames read | FILL |
| Feature windows | FILL |
| Average bus rate | FILL frames/s (about 332 expected because of the 3.7% WSL2 clock skew) |
| Alerts when run through `detect.py` after training on it | FILL |

## Observations

- FILL: anything unexpected (errors, warnings, alerts on normal traffic)

## Status and next steps

| Item | Status |
|---|---|
| Feature extraction, training, rules, alerts, detector, live detector | Working end to end (this test) |
| Real normal datasets from the final ECU simulator (Member 1 + Member 3) | Waiting |
| Real labelled attack recordings (Member 2) | Waiting |
| Live input from the C sniffer over `/tmp/can_sentinel.sock` (Member 2) | In progress |

Next: retrain on the real normal runs, evaluate per attack on the real attack runs,
and fill in `docs/evaluation_plan.md` before the mid review (Oct 27-30).
