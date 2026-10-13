# Day 8 — Offline Synthetic CAN Fixture and Validation

**Project:** CAN-Sentinel
**Branch:** member-2

## 1. Objective

Create an offline synthetic CAN dataset and a matching event log
to validate CSV formatting, timestamp matching, and dataset-labeling
workflow requirements.

## 2. Scope and Safety

This exercise uses generated example data only.
No CAN socket is opened and no CAN frames are transmitted.
The generated files are not real CAN captures or vehicle telemetry.

## 3. Files

- `attacker/generate_synthetic_fixture.py`
- `attacker/test_synthetic_fixture.py`
- `logs/synthetic_fixture/synthetic_raw.csv`
- `logs/synthetic_fixture/synthetic_injection_log.csv`

Generated files are stored under the ignored `logs/` directory.

## 4. CSV Contracts

Raw dataset columns:

`timestamp,can_id,dlc,data_hex,label`

Synthetic event-log columns:

`timestamp,can_id,data_hex`

Timestamps use Unix epoch seconds with six decimal places.
CAN IDs use uppercase hexadecimal with a `0x` prefix and three
hexadecimal digits. Data bytes are represented as uppercase
hexadecimal without spaces.

## 5. Reproduction

Generate the fixtures:

    python3 attacker/generate_synthetic_fixture.py

Run validation:

    python3 -m unittest attacker.test_synthetic_fixture -v

Check syntax:

    python3 -m py_compile attacker/generate_synthetic_fixture.py attacker/test_synthetic_fixture.py

## 6. Validation Results

The five automated tests verify:

- Exact CSV headers
- Expected row counts
- CAN ID, DLC, payload length and hexadecimal format
- Matching timestamps, CAN IDs and payloads between synthetic
  labeled events and the synthetic event log
- Numeric positive timestamps

All five tests passed in the recorded run.

## 7. Limitations

- The data is synthetic and deterministic.
- No live CAN recording was produced.
- Compatibility with the dashboard labeler remains unverified
  because its implementation was not present in the inspected
  dashboard directory.
- These tests validate the fixture format, not attack detection,
  vehicle behavior, or ML performance.

## 8. Conclusion

The offline fixture generator and its five validation tests passed.
The fixture can be used to test basic CSV handling, but it must not
be represented as real CAN traffic.
