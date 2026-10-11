# Day 7 — Flood Testing, Timestamped Logging and Cleanup

**Date:** 11 October 2026  
**Project:** CAN-Sentinel  
**Branch:** member-2

## 1. Objective

Test the bounded flood module on the local virtual CAN interface,
record transmission timestamps, verify frame counts, and check
basic safety restrictions.

## 2. Environment and Tools

- Operating system: Kali Linux
- Python: 3.14.7
- Interface: vcan0
- CAN receiver: candump (can-utils)
- Logging format: JSON Lines (JSONL)
- CAN type: Classic CAN
- Test scope: Local virtual CAN interface only

## 3. Flood Configuration

| Parameter | Value |
|---|---|
| Interface | vcan0 |
| CAN ID | 0x000 |
| DLC | 8 bytes |
| Payload | 11 22 33 44 55 66 77 88 |
| Duration | 1 second |
| Requested rate | 10 frames/second |
| Maximum frames per run | 10 |

The attacker module restricts transmission to vcan0, limits each
run to at most 5 seconds and 100 frames/second, and enforces a
maximum calculated frame count of 500.

## 4. Test Commands

Check the interface:

    python3 attacker/attacker.py --check-interface

Dry run:

    python3 attacker/attacker.py --attack flood --duration 1 --rate 10

Execute the bounded local test:

    python3 attacker/attacker.py --attack flood --duration 1 --rate 10 --execute

Receive CAN frames:

    candump -n 10 vcan0

Inspect timestamped logs:

    tail -n 25 logs/flood_test.jsonl

## 5. Verified Results

- The interface check succeeded.
- The dry run completed without transmitting CAN frames.
- Two actual execution runs each reported 10 frames sent.
- The first execution reported 0.901 seconds elapsed.
- The second execution reported 0.902 seconds elapsed.
- The log contained 20 frame_sent records across the two runs.
- Each execution had a run_start record and a completed run_end record.
- Frame log entries included UTC timestamps, frame number, interface,
  CAN ID, DLC and payload.
- candump displayed 10 frames per invocation with CAN ID 0x000,
  DLC 8 and payload 11 22 33 44 55 66 77 88.
- Python bytecode compilation succeeded.
- git diff --check completed without warnings.

The candump commands were run after the sender executions, so their
output confirms that 10 matching frames were read per invocation,
but does not independently correlate each receiver output with a
specific execution run.

## 6. Safety Scope

All transmission tests were restricted to the local vcan0 interface.
No physical vehicle or physical CAN bus was used. The module retains
its interface restriction and bounded duration, rate and frame count.

## 7. Logging and Cleanup

Timestamped JSONL logging records run metadata, individual successful
send calls, and execution summaries. The log is generated locally and
is not intended as a source-controlled project artifact.

The CAN socket is closed in a finally block after execution.

## 8. Known Limitations

- The test uses a virtual CAN interface, not real vehicle hardware.
- The fixed payload is test data, not a validated automotive message.
- Receiver output was not captured concurrently with each sender run.
- This test does not validate ECU behavior or detection by the ML model.
- Other planned attack modules remain unimplemented.

## 9. Conclusion

The bounded flood module completed two local execution runs, sending
10 frames per run. Timestamped JSONL records were written, and the
basic syntax and whitespace checks passed.
