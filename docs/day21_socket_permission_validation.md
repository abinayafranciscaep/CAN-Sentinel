# Day 21 - Unix Socket Permission Validation

## Objective
Remove the requirement for manually running `sudo chmod 666`
after starting the CAN sniffer.

## Implementation
Updated `sniffer/socket_bridge.c`.

After successfully binding the Unix domain socket, the sniffer
automatically applies restricted permissions:

- Owner: Read and write
- Group: Read and write
- Others: No access
- Permission mode: 0660

## Validation

1. Compiled the CAN sniffer with strict GCC warnings:
   -Wall -Wextra -Wpedantic -Werror -std=c11

2. Started the sniffer without sudo:
   `/tmp/can_sniffer vcan0 --socket --socket-path /tmp/can_sentinel.sock`

3. Verified socket permissions:
   `srw-rw---- 660 chetan chetan`

4. Sent a CAN frame:
   `cansend vcan0 456#AABBCCDD`

5. Connected a Python Unix socket client without manually
   changing socket permissions.

6. Successfully received:
   - CAN ID: 0x456
   - DLC: 4
   - Data: AABBCCDD

## Unit Tests
Command:
`python -m unittest -v sniffer.test_socket_receiver`

Result: 10 tests passed.

## Additional Validation
- Strict GCC compilation: Passed
- git diff --check: Passed
- Manual sudo chmod 666: Not required during validation

## Result
The sniffer now applies restricted Unix socket permissions
automatically after socket creation.

Dashboard and ML clients must run as the socket owner or
belong to the socket's group to access it.
