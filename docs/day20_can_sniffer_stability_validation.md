# Day 4 — CAN Sniffer Stability and Traffic Validation

## Objective
To validate the CAN sniffer's ability to capture CAN frames,
process message information, forward data to an ML client,
and clean up resources after shutdown.

## Test Environment
- Operating System: Kali Linux
- CAN Interface: vcan0
- Programming Language: C
- CAN Framework: Linux SocketCAN
- Communication: Unix Domain Socket
- Git Branch: member-2

## Activities Performed

### 1. CAN Sniffer Code Inspection
Inspected the existing can_sniffer.c implementation and verified
its CAN socket creation, interface binding, signal handling,
frame processing, timestamp generation, and socket forwarding logic.

### 2. Strict Compilation
Compiled the CAN sniffer and socket bridge using:
- -Wall
- -Wextra
- -Wpedantic
- -Werror
- -std=c11

Both compilations completed successfully.

### 3. Live CAN Traffic Capture
Executed the CAN sniffer on vcan0 and verified these frames:

- CAN ID 0x123, DLC 4, DATA 11 22 33 44
- CAN ID 0x456, DLC 4, DATA AA BB CC DD
- CAN ID 0x321, DLC 8, DATA 01 02 03 04 05 06 07 08

The sniffer correctly displayed CAN IDs, DLC values, and payloads.

### 4. Unix Socket Forwarding
Enabled socket forwarding and connected a Python ML client
through a Unix domain socket.

Successfully received three CAN messages in JSON format,
including timestamps, CAN IDs, DLC values, and hexadecimal payloads.

### 5. Socket Cleanup Verification
After stopping the sniffer, verified that the Unix socket path
was removed successfully.

### 6. Automated Testing
Executed:

python3 -m unittest -v sniffer.test_socket_receiver

Result: All 10 unit tests passed.

### 7. Code Quality Checks
- CAN sniffer strict compilation: Successful
- Socket bridge strict compilation: Successful
- Socket receiver tests: 10 passed
- git diff --check: No errors

## Outcome
Successfully validated live CAN frame capture, message parsing,
JSON forwarding to the ML client, and socket path cleanup.

## Scope and Limitations
This validation covers the CAN sniffer and socket forwarding
workflow using the virtual CAN interface. It does not establish
successful attack detection or complete end-to-end ML integration.

## GitHub
Branch: member-2
