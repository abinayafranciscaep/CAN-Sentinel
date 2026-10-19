# Day 15 — C Sniffer CLI and Interface Validation

## Objective
Allow selection of the CAN interface through a command-line argument while retaining vcan0 as the default.

## Implementation
Source: sniffer/can_sniffer.c

- Default interface: vcan0
- Optional interface argument: ./can_sniffer <interface>
- Rejects extra arguments.
- Rejects empty or overlong interface names.
- Reports errors for non-existent interfaces.
- Receives and displays CAN IDs, DLC values, and payload bytes.

## Build
Strict compilation passed:
gcc -Wall -Wextra -Wpedantic -Werror -std=c11 sniffer/can_sniffer.c -o /tmp/can_sniffer_day15

## CLI Validation
- Extra arguments: Usage message, exit code 1 — PASS
- Non-existent interface no_such0: Interface lookup error, exit code 1 — PASS
- Empty interface: Invalid interface message, exit code 1 — PASS

## Live Virtual CAN Tests

### Default interface
Command: /tmp/can_sniffer_day15

Test frame: cansend vcan0 123#11223344

Observed output:
CAN ID: 0x123  DLC: 4  DATA: 11 22 33 44

Result: PASS

### Explicit interface
Command: /tmp/can_sniffer_day15 vcan0

Test frame: cansend vcan0 321#AABBCCDD

Observed output:
CAN ID: 0x321  DLC: 4  DATA: AA BB CC DD

Result: PASS

## Safety and Test Scope
All tests used the local virtual CAN interface vcan0. No physical vehicle or hardware CAN bus was involved.

## Conclusion
Strict compilation, CLI validation, invalid-interface handling, and frame reception using both default and explicit interface selection passed.
