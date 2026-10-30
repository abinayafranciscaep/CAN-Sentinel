# Day 3 — Repeated Client Reconnection Testing

## Objective
To validate CAN message forwarding across multiple sequential client
connections using the CAN socket bridge and virtual CAN interface.

## Test Environment
- Operating System: Kali Linux
- CAN Interface: vcan0
- CAN Utility: can-utils
- Implementation: C
- Communication: Unix Domain Socket
- Git Branch: member-2

## Activities Performed

### 1. Virtual CAN Setup
Loaded the vcan kernel module, created the vcan0 interface,
and brought it up successfully.

### 2. Socket Bridge Compilation
Compiled sniffer/can_socket_bridge.c using strict compiler flags:
- -Wall
- -Wextra
- -Wpedantic
- -Werror
- -std=c11

Compilation completed successfully.

### 3. Sequential Client Connection Testing
Started the CAN socket bridge and tested three sequential clients.

- Client 1 connected and received CAN messages.
- Client 1 disconnected.
- Client 2 reconnected and received new CAN messages.
- Client 2 disconnected.
- Client 3 reconnected and received new CAN messages.

### 4. CAN Message Forwarding
Verified that CAN frames were forwarded to connected clients
in JSON format through the Unix domain socket.

Tested CAN IDs and payloads included:
- 0x123 — 11223344
- 0x456 — AABBCCDD
- 0x789 — DEADBEEF
- 0x321 — DEADBEEF
- 0x654 — AABBCCDD
- 0x777 — 11223344
- 0x688 — AABBCCDD

An attempted 0x888 test was observed as 0x088 by candump
and the bridge. A separate 0x688 test was used for verification.

### 5. Automated Unit Testing
Executed:

python3 -m unittest -v sniffer.test_socket_receiver

Result: All 10 tests passed.

### 6. Code Quality Checks
- Strict C compilation: Successful
- Socket receiver unit tests: 10 passed
- git diff --check: No errors

## Outcome
Successfully validated sequential client connection,
disconnection, reconnection, and CAN message forwarding
through the socket bridge using the virtual CAN interface.

## Scope and Limitations
This test validates sequential client reconnection and message
forwarding. It does not establish simultaneous multi-client
support or successful attack detection.

## GitHub
Branch: member-2
