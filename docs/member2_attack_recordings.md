# Member 2 — CAN Attack Recording Handoff

## 1. Overview

This document describes Chetan's controlled virtual CAN recordings
generated using the CAN-Sentinel sniffer and Python recording client.

All recordings were captured on the local Linux virtual CAN interface
`vcan0`. They are lab-generated test traffic, not recordings from a
real vehicle or production ECU.

## 2. Recording pipeline

CAN frames were captured through:

1. C CAN sniffer listening on `vcan0`.
2. Unix socket bridge at `/tmp/can_sentinel.sock`.
3. Python recording client: `attacker/record_can.py`.
4. Labelled CSV output under `logs/official_capture/`.

## 3. CSV schema

Each CSV contains:

- `timestamp`
- `can_id`
- `dlc`
- `data_hex`
- `label`

## 4. Captured datasets

| File | Label | Frames | CAN ID |
|---|---|---:|---|
| normal_vcan.csv | normal | 10 | 0x0A0 |
| spoof_brake_vcan.csv | spoof_brake | 10 | 0x0A0 |
| replay_vcan.csv | replay | 10 | 0x0A0 |
| fuzz_vcan.csv | fuzz | 10 | 0x0A0 |
| masquerade_vcan.csv | masquerade | 10 | 0x0A0 |
| diag_abuse_vcan.csv | diag_abuse | 10 | 0x7DF |

Total: 60 frames across 6 CSV files.

## 5. Scenario descriptions

- Normal: controlled baseline frames on virtual CAN.
- Spoof Brake: controlled modified-payload test frames labelled
  `spoof_brake`.
- Replay: previously recorded normal frames retransmitted on `vcan0`.
- Fuzz: random 8-byte payloads transmitted on `vcan0`.
- Masquerade: controlled unusual-payload frames labelled
  `masquerade`.
- Diagnostic Abuse: repeated UDS diagnostic session request frames
  (`02 10 03`) sent to functional CAN ID `0x7DF`.

These labels describe the test scenarios used to generate the data.
They do not independently prove a real vehicle attack or malicious
ECU behaviour.

## 6. Validation

All six CSV files passed the local validation script:

- Expected CSV columns present.
- Expected label present in every row.
- DLC equals 8.
- Payload length equals 8 bytes (16 hexadecimal characters).
- Exactly 10 data rows per file.

Validation result: 6/6 files passed; 60 frames total.

## 7. Limitations

- Data was generated on local `vcan0`, not captured from a physical
  vehicle or production CAN bus.
- Payloads are controlled lab test values.
- These files should be identified as virtual CAN lab datasets in
  reports, demonstrations, and downstream model training.
- Real vehicle recordings, if later supplied by the team, must be
  stored and documented separately.

## 8. Files

- `attacker/record_can.py`
- `logs/official_capture/normal_vcan.csv`
- `logs/official_capture/spoof_brake_vcan.csv`
- `logs/official_capture/replay_vcan.csv`
- `logs/official_capture/fuzz_vcan.csv`
- `logs/official_capture/masquerade_vcan.csv`
- `logs/official_capture/diag_abuse_vcan.csv`
