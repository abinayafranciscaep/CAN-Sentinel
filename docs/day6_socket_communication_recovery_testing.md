# Day 6: Socket Communication & Recovery Testing

## Objective
Validate Unix domain socket communication, CAN frame forwarding,
client disconnect handling, reconnection, and socket cleanup.

## Environment
- Branch: member-2
- CAN Interface: vcan0
- Socket Type: Unix Domain Stream Socket
- Sniffer: can_sniffer
- Test Binary: /tmp/can_sniffer_day6

## 1. Strict Compilation
Compiled the CAN sniffer and socket bridge using:

gcc -Wall -Wextra -Wpedantic -Werror -std=c11 \
sniffer/can_sniffer.c sniffer/socket_bridge.c \
-o /tmp/can_sniffer_day6

Result: PASS

## 2. Socket Connection
Started the sniffer with socket forwarding enabled.

Result: ML client successfully connected.

## 3. Live CAN Traffic Forwarding
Tested CAN frames:

- CAN ID: 0x123
- DLC: 4
- Data: 11223344

- CAN ID: 0x456
- DLC: 4
- Data: AABBCCDD

Both frames were received by the Python ML client in JSON format.

Result: PASS

## 4. Client Disconnect Handling
Disconnected the ML client while the sniffer was running.

Observed:
ML client disconnected; awaiting reconnect.

Result: PASS

## 5. Client Reconnection
Connected a new ML client after disconnection.

Result: PASS

## 6. Traffic After Reconnection
Sent CAN frame:

- CAN ID: 0x789
- DLC: 4
- Data: DEADBEEF

The reconnected client successfully received the frame.

Result: PASS

## 7. Repeated Reconnection
Performed five sequential client connection and disconnection cycles.

All five cycles completed without an observed sniffer crash.

Result: PASS

## 8. Graceful Socket Cleanup
Stopped the sniffer using Ctrl+C.

Verified that the Unix socket file was removed.

Output:
PASS: Socket cleanup successful

Result: PASS

## Design Observation
The current socket bridge maintains one active ML client.
A newly accepted client replaces the previous active client.
Simultaneous multi-client forwarding was not validated.

## Conclusion
Day 6 socket communication and recovery tests completed.
Live CAN forwarding, disconnect detection, reconnection,
repeated reconnect cycles, and graceful socket cleanup
were successfully validated.
