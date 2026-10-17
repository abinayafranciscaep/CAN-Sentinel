# Day 13 — C CAN Sniffer Skeleton

## Objective

Create and validate a basic C SocketCAN sniffer that receives CAN
frames from the local virtual CAN interface `vcan0`.

## Implementation

Source file: `sniffer/can_sniffer.c`

The program:
- Creates a raw SocketCAN socket.
- Looks up the `vcan0` interface index.
- Binds the socket to `vcan0`.
- Reads incoming CAN frames.
- Prints the CAN identifier, DLC, and payload bytes.
- Reports socket, interface lookup, bind, and read errors.

The program receives frames only; it does not transmit CAN frames.

## Local virtual CAN test

A test frame was sent on the local virtual interface:

`cansend vcan0 123#11223344`

Observed sniffer output:

`CAN ID: 0x123  DLC: 4  DATA: 11 22 33 44`

## Validation

- GCC compilation with `-Wall -Wextra -Wpedantic`: passed.
- Strict compilation with `-Werror`: passed.
- Local `vcan0` receive test: passed.
- `git diff --check`: passed.

## Scope and limitations

Testing was performed on a local virtual CAN interface, not a physical
vehicle. This is a basic receive-only skeleton, not a production-ready
sniffer. The compiled binary is generated locally and is not committed.
