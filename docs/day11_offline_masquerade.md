# Day 11 — Offline Masquerade Simulation

## Objective
Generate synthetic CAN records representing normal traffic followed by
a longer timing gap and subsequent plausible-looking records.

## Files
- `attacker/masquerade_offline.py`: Offline synthetic record generator.
- `attacker/test_masquerade_offline.py`: Automated unit tests.
- Output: `logs/masquerade_offline/synthetic_masquerade.csv` (local, ignored by Git).

## Dataset Format
The output uses the project CSV schema:

`timestamp,can_id,dlc,data_hex,label`

The fixture contains six records:
- Three records labelled `normal`.
- Three records labelled `masquerade`.
- All records use CAN ID `0x0A0` and DLC 8.
- Normal records use 20 ms intervals, followed by a 100 ms gap.

## Usage
Generate the synthetic dataset:

`python3 attacker/masquerade_offline.py`

Run focused tests:

`python3 -m unittest discover -s attacker -p 'test_masquerade_offline.py' -v`

Run all attacker tests:

`python3 -m unittest discover -s attacker -p 'test_*.py' -v`

## Verification
The five masquerade tests passed. The full regression suite passed
all 23 tests. Python syntax compilation and `git diff --check`
also completed successfully.

## Safety and Limitations
This is a synthetic offline dataset, not a real CAN capture.
The generator does not open a CAN socket, silence an ECU, impersonate
an ECU, or transmit CAN frames. The timing gap is a test example,
not evidence of real ECU takeover or IDS detection performance.

Diagnostic-abuse implementation remains pending team scope confirmation.
