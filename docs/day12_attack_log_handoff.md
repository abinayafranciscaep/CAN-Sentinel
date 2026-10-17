# Day 12 — Attack Logs and Dataset Handoff

## Objective

Validate the synthetic CAN dataset and injection log against the
project's documented CSV interface contracts.

## Files

- `attacker/generate_synthetic_fixture.py`
- `attacker/test_dataset_handoff.py`
- `logs/synthetic_fixture/synthetic_raw.csv`
- `logs/synthetic_fixture/synthetic_injection_log.csv`

The CSV files are generated locally and are not committed as captured
vehicle traffic. They contain synthetic examples only.

## CSV schemas

Raw dataset:

`timestamp,can_id,dlc,data_hex,label`

Injection log:

`timestamp,can_id,data_hex`

The injection log uses the three-column format requested for the
dataset-labeling workflow.

## Validation performed

Automated tests verify:

- Both CSV headers match their expected schemas.
- The raw dataset contains five records: three `normal` and two
  `spoof_brake`.
- The injection log contains two entries.
- Injection timestamps, CAN IDs, and payloads match the corresponding
  `spoof_brake` records in the raw dataset.
- Raw timestamps are numeric, ordered, and unique.
- CAN IDs, DLC values, and payload formats are valid for these fixtures.

## Test results

- Dataset handoff tests: 6 passed.
- Full attacker regression suite: 29 passed.
- Python syntax compilation: passed.
- `git diff --check`: passed.

## Limitations and handoff status

These fixtures are synthetic and are not evidence of a real CAN capture
or a live attack.

The repository currently contains only `dashboard/.gitkeep`; the
dashboard dataset-labeling implementation was not available during
this validation. Compatibility with that implementation remains
unverified and should be checked when the labeler is available.

No dashboard files were modified.
No CAN frames were transmitted during this offline validation.
