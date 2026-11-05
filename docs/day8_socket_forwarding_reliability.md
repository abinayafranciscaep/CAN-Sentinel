# Day 8 — Socket Forwarding and Reliability Testing

**Date:** 5 November 2026
**Project:** CAN-Sentinel
**Branch:** member-2

## 1. Objective

Validate communication between the C CAN sniffer and the ML client
through a Unix domain socket. Verify JSON frame forwarding,
multiple CAN IDs, client disconnection, reconnection, and cleanup.

## 2. Environment

- Operating System: Kali Linux
- Interface: vcan0
- Language: C and Python
- Tools: GCC, Python 3, can-utils
- Socket Type: Unix Domain SOCK_STREAM
- Socket Path: /tmp/can_sentinel.sock
- Test Scope: Local virtual CAN interface only

## 3. Compilation

Compiled the C sniffer and socket bridge with strict compiler flags:

    gcc -Wall -Wextra -Wpedantic -Werror -std=c11 \
    sniffer/can_sniffer.c sniffer/socket_bridge.c \
    -o /tmp/can_sniffer_day8

Compilation completed successfully.

## 4. NDJSON Contract Validation

Executed:

    python3 -m unittest -v sniffer/test_socket_receiver.py

Results:
- 10 unit tests passed.
- Valid JSON messages accepted.
- Invalid fields, CAN IDs, DLC values and payloads rejected.
- Newline-delimited JSON format validated.

Result: PASS.

## 5. Socket Connection and Single Frame Forwarding

Started the C sniffer with socket forwarding enabled:

    /tmp/can_sniffer_day8 vcan0 --socket

The Python client connected to /tmp/can_sentinel.sock.

A CAN frame was transmitted:

    cansend vcan0 123#11223344

The ML client received a valid JSON message containing:
- CAN ID: 0x123
- DLC: 4
- Payload: 11223344
- Timestamp: Present

Result: PASS.

## 6. Multiple CAN Frame Forwarding

Tested three different CAN IDs:

| CAN ID | Payload | Result |
|---|---|---|
| 0x123 | 11223344 | PASS |
| 0x456 | AABBCCDD | PASS |
| 0x789 | DEADBEEF | PASS |

All three messages were received by the Python client.

Result: PASS.

## 7. 100-Frame Forwarding Reliability Test

Generated 100 CAN frames using three CAN IDs.

The Python ML client received:

| CAN ID | Received Frames |
|---|---:|
| 0x123 | 33 |
| 0x456 | 34 |
| 0x789 | 33 |
| Total | 100 |

All 100 generated frames were received in this test.

Result: PASS.

## 8. Client Disconnection and Reconnection

Verified:
- ML client successfully connected.
- Client disconnection was detected by the C socket bridge.
- The bridge accepted new client connections.
- A reconnected client successfully received a CAN frame.
- Reconnection forwarding was verified with CAN ID 0x789
  and payload DEADBEEF.

Result: PASS.

## 9. Graceful Shutdown and Cleanup

- The C sniffer was stopped using Ctrl+C.
- No running can_sniffer_day8 process remained.
- The socket file /tmp/can_sentinel.sock was absent after shutdown.
- Socket cleanup was verified.

Result: PASS.

## 10. Safety Scope and Limitations

- All CAN traffic was generated on the local vcan0 interface.
- No physical vehicle or physical CAN bus was used.
- The 100-frame result applies to the tested conditions.
- The test does not establish unlimited throughput or zero packet
  loss under all possible traffic loads.
- Simultaneous multi-client support was not tested or claimed.
- ML detection accuracy was not evaluated.

## 11. Conclusion

The C CAN sniffer successfully forwarded CAN frames to a Python
ML client through a Unix domain socket. The 100-frame forwarding
test, multiple CAN ID validation, client disconnection detection,
reconnection forwarding, and graceful cleanup were verified.
