# Day 14 — C Sniffer Testing

## Objective

Verify that the C SocketCAN sniffer receives multiple CAN frames from
the local virtual CAN interface and handles an invalid interface name.

## Tests performed

### 1. Strict compilation

The sniffer compiled successfully with:

`gcc -Wall -Wextra -Wpedantic -Werror -std=c11`

### 2. Multiple-frame receive test

Two test frames were sent on local `vcan0`.

First frame:

`cansend vcan0 123#11223344`

Observed output:

`CAN ID: 0x123  DLC: 4  DATA: 11 22 33 44`

Second frame:

`cansend vcan0 321#AABBCCDD`

Observed output:

`CAN ID: 0x321  DLC: 4  DATA: AA BB CC DD`

Both frames were received and printed as expected.

### 3. Invalid-interface error test

A temporary test build used the interface name `no_such0`.
The original project source was not changed for this test.

Observed error:

`ioctl(SIOCGIFINDEX): No such device`

Captured exit code: `1`.

Result: expected failure status confirmed.

## Scope and limitations

All CAN tests used the local virtual interface `vcan0`.
No physical vehicle was connected. The sniffer receives frames only
and does not transmit CAN frames itself.

These tests verify basic receive behavior and interface-lookup error
handling; they do not constitute production or vehicle validation.
