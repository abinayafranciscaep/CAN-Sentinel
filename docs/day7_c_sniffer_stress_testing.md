# Day 7 — C CAN Sniffer Stress and Reliability Testing

**Date:** 4 November 2026
**Project:** CAN-Sentinel
**Branch:** member-2

## 1. Objective

Validate the C CAN sniffer under mixed and sustained CAN traffic.
Verify frame capture, multiple CAN IDs, process stability, graceful
shutdown, and socket cleanup.

## 2. Environment

- Operating System: Kali Linux
- Interface: vcan0
- Tools: can-utils, GCC
- Sniffer: C CAN sniffer with socket bridge
- CAN Type: Classic CAN
- Test Scope: Local virtual CAN interface only

## 3. Compilation

The sniffer was compiled with strict compiler warnings:

    gcc -Wall -Wextra -Wpedantic -Werror -std=c11 \
    sniffer/can_sniffer.c sniffer/socket_bridge.c \
    -o /tmp/can_sniffer_day7

Compilation completed successfully without reported warnings or errors.

## 4. Mixed CAN Traffic Test

Generated 500 CAN frames using three CAN IDs:

| CAN ID | Captured Frames |
|---|---:|
| 0x123 | 166 |
| 0x456 | 167 |
| 0x789 | 167 |
| Total | 500 |

The capture log contained 500 complete CAN ID records.

Result: PASS.

## 5. Sustained Traffic Test

Generated three CAN frames per second for 30 seconds.

| Metric | Result |
|---|---:|
| Duration | 30 seconds |
| Generated frames | 90 |
| Captured frames | 90 |
| Missing frames | 0 |

Result: PASS.

## 6. Basic Capture Test

The sniffer successfully captured a test CAN frame:

- CAN ID: 0x123
- DLC: 4
- Payload: 11 22 33 44

Result: PASS.

## 7. Graceful Shutdown and Cleanup

- Both running sniffer processes were stopped using SIGINT.
- No sniffer process remained after shutdown.
- The socket file `/tmp/can_sentinel.sock` was absent after shutdown.
- Forced termination using SIGKILL was not required.

Result: PASS.

## 8. Additional Test Note

A separate test generated 1,000 CAN frames. The generator completed,
but the exact captured frame count was not verified. Therefore,
this test is not marked as a verified capture pass.

## 9. Safety Scope and Limitations

- All tests used the local vcan0 interface.
- No physical vehicle or physical CAN bus was involved.
- The 500-frame and 90-frame results apply to the tested conditions.
- These tests do not establish unlimited throughput or zero packet
  loss under all possible traffic loads.
- ML detection accuracy was not evaluated in this test.

## 10. Conclusion

The C CAN sniffer successfully captured 500 mixed CAN frames and
90 frames during a 30-second sustained traffic test. Graceful
shutdown and socket cleanup were also verified successfully.
