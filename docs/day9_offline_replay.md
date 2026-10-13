# Day 9 — Offline Replay Processing and Validation

**Project:** CAN-Sentinel
**Branch:** member-2

## 1. Objective

Implement offline processing for a recorded CAN CSV file.
Validate the input schema, CAN identifiers, DLC, payload format,
and timestamp ordering before writing validated records to JSONL.

## 2. Scope and Safety

This implementation processes files only.
It does not open a CAN socket or transmit CAN frames.
The synthetic input is not a real CAN capture.

## 3. Files

- `attacker/replay_offline.py`
- `attacker/test_replay_offline.py`
- `logs/synthetic_fixture/replay_processed.jsonl`

The generated JSONL file is stored under the ignored `logs/`
directory and is not committed.

## 4. Validation Rules

- CSV header must be `timestamp,can_id,dlc,data_hex,label`.
- Timestamps must be positive and non-decreasing.
- Standard CAN identifiers must use uppercase `0x` notation
  and fit within the 11-bit identifier range.
- DLC must be between 0 and 8.
- Payload length must equal twice the DLC.
- Payload characters must be uppercase hexadecimal.
- Label must not be empty.

## 5. Reproduction

Process the synthetic fixture:

    python3 attacker/replay_offline.py logs/synthetic_fixture/synthetic_raw.csv --output logs/synthetic_fixture/replay_processed.jsonl

Run automated tests:

    python3 -m unittest discover -s attacker -p 'test_replay_offline.py' -v

Run syntax checks:

    python3 -m py_compile attacker/replay_offline.py attacker/test_replay_offline.py

## 6. Test Results

Five automated tests passed:

- Valid recording accepted
- Incorrect CSV header rejected
- DLC/payload length mismatch rejected
- Invalid CAN identifier rejected
- Out-of-order timestamps rejected

The processor validated five synthetic input records.
JSONL output preserves timestamps formatted to six decimal places.

## 7. Limitations

- The input is synthetic, not captured from a live CAN bus.
- This is offline parsing and validation, not CAN replay transmission.
- Replay detection accuracy and ML integration have not been tested.
- Compatibility with the dashboard labeler remains unverified.

## 8. Conclusion

The offline recording processor and its five tests passed.
No CAN frames were transmitted.
