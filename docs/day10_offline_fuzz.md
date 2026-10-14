# Day 10 — Offline CAN Fuzz Test Generation

## Objective
Generate reproducible synthetic CAN test cases for offline validation
of CAN frame formats and detection workflows.

## Files
- `attacker/fuzz_offline.py`: Synthetic CAN CSV generator.
- `attacker/test_fuzz_offline.py`: Automated unit tests.
- Output: `logs/fuzz_offline/synthetic_fuzz_cases.csv` (local, ignored by Git).

## CSV Schema
`timestamp,can_id,dlc,data_hex,label`

- `timestamp`: Increasing synthetic timestamp.
- `can_id`: Standard 11-bit identifier, uppercase hexadecimal with `0x` prefix and three digits.
- `dlc`: Payload length from 0 to 8 bytes.
- `data_hex`: Uppercase hexadecimal payload without spaces.
- `label`: `fuzz`.

## Usage
Generate 20 cases:

`python3 attacker/fuzz_offline.py --count 20 --seed 42`

Generate 50 cases:

`python3 attacker/fuzz_offline.py --count 50 --seed 123 --output logs/fuzz_offline/custom_cases.csv`

The accepted count range is 1–1000. Identical seeds and settings produce reproducible cases.

## Testing
Run fuzz tests:

`python3 -m unittest discover -s attacker -p 'test_fuzz_offline.py' -v`

Run the complete attacker test suite:

`python3 -m unittest discover -s attacker -p 'test_*.py' -v`

Previously, all 18 tests passed. Python syntax compilation and `git diff --check` also passed.

## Safety and Limitations
This module generates offline synthetic records only. It does not open a CAN socket or transmit CAN frames. Generated records are test fixtures, not actual vehicle captures or proof of ECU behaviour.

The generator creates structurally valid standard CAN records. Invalid input handling is tested separately. Live CAN fuzzing and ECU response testing are outside this implementation.
