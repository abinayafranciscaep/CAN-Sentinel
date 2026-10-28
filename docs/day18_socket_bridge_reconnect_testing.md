# Day 18 — Socket Bridge Disconnect and Reconnect Testing

## Objective

Verify that the standalone CAN socket bridge can forward a frame to
one client, accept a subsequent client connection, and forward another
frame after the first client disconnects.

## Environment

- Git branch: `member-2`
- CAN interface: `vcan0`
- Socket path: `/tmp/can_sentinel_day2.sock`
- Bridge binary: `/tmp/can_socket_bridge_day2`

## Test Results

### 1. Strict compilation

The standalone bridge compiled successfully with:

    gcc -Wall -Wextra -Wpedantic -Werror -std=c11 \
      sniffer/can_socket_bridge.c \
      -o /tmp/can_socket_bridge_day2

### 2. First client

The first client connected and received:

    {"timestamp":1793161472.743537,"can_id":"0x123","dlc":4,"data_hex":"11223344"}

Result: the first synthetic frame was received with the expected CAN ID,
DLC, and payload.

### 3. Second client after reconnect

After the first client completed, a second client connected and received:

    {"timestamp":1793161500.902086,"can_id":"0x456","dlc":4,"data_hex":"AABBCCDD"}

Result: the second synthetic frame was received with the expected CAN ID,
DLC, and payload.

### 4. Receiver contract regression tests

Command:

    python -m unittest -v sniffer.test_socket_receiver

Result: 10 tests passed.

### 5. Repository checks

`git diff --check` completed without reported errors. The active branch
was `member-2`.

## Limitations

This was a sequential two-client reconnect test. It does not establish
reliability under repeated reconnect loops, concurrent clients, sustained
traffic, queue saturation, or slow-client conditions.

## Conclusion

The observed test confirms basic frame forwarding to the first client
and successful forwarding to a second client after reconnecting.
Additional reliability testing remains outstanding.
