# Day 4 - CAN Frame Format and ECU Traffic Notes

## Objective

The objective of Day 4 is to understand the CAN frame format and the baseline ECU traffic defined for the CAN-Sentinel project.

This understanding will be used later when developing the attacker module and C sniffer.

## CAN Environment

CAN-Sentinel uses a virtual SocketCAN environment for development and testing.

The project uses:

- Classic CAN
- 11-bit CAN identifiers
- DLC values from 0 to 8
- Linux virtual CAN interface: `vcan0`
- No real vehicle or physical CAN bus

All attack code is intended to run only on the project's own `vcan0` lab environment.

## CAN Frame Basics

A CAN frame used in this project can be represented using the following important fields:

```text
CAN Frame
+-----------+------+----------------------+
| CAN ID    | DLC  | Data                 |
+-----------+------+----------------------+
| 0x0A0     |  8   | CAN payload bytes    |
+-----------+------+----------------------+
```

### CAN ID

The CAN ID identifies the type of message on the CAN bus.

The CAN-Sentinel baseline uses specific CAN IDs for different ECU signals.

### DLC

DLC means Data Length Code.

For this project, Classic CAN supports DLC values from 0 to 8.

The baseline ECU messages use a DLC of 8.

### Data

The data field contains the payload of the CAN frame.

The project defines proposed payload layouts for the baseline ECU messages.

## ECU Baseline Traffic

The following normal traffic is defined as the project's golden baseline.

| CAN ID | ECU / Signal | Period | DLC | Proposed Payload Layout | Safety Criticality |
|---|---|---:|---:|---|---|
| `0x0A0` | Brake | 20 ms | 8 | B0 = brake pressure (0-100), B1 = brake switch (0/1), B7 = rolling counter | Critical |
| `0x0B0` | Steering | 10 ms | 8 | B0-B1 = steering angle (signed, 0.1 deg), B7 = rolling counter | Critical |
| `0x100` | Engine RPM | 10 ms | 8 | B0-B1 = RPM (0-8000), B7 = rolling counter | High |
| `0x200` | Vehicle Speed | 20 ms | 8 | B0 = speed km/h (0-250), B7 = rolling counter | High |
| `0x300` | Engine Temperature | 100 ms | 8 | B0 = coolant temperature (offset -40 C) | Medium |
| `0x600` | Infotainment Heartbeat | 100 ms | 8 | B0 = status, B7 = rolling counter | Low |
| `0x7DF` | Diagnostic Request | Event only | 8 | Standard OBD-II / UDS request format | High when abused |

## Traffic Timing

The baseline traffic periods are important because the IDS detects deviations from normal traffic behavior.

Examples:

- Brake (`0x0A0`) → every 20 ms
- Steering (`0x0B0`) → every 10 ms
- Engine RPM (`0x100`) → every 10 ms
- Vehicle Speed (`0x200`) → every 20 ms
- Engine Temperature (`0x300`) → every 100 ms
- Infotainment (`0x600`) → every 100 ms
- Diagnostic (`0x7DF`) → event-based, not periodic

The design document recommends realistic variation in normal traffic, including approximately +/- 1 ms timing jitter and changing signal values.

## Rolling Counter

A rolling counter is defined as an optional but recommended field in the baseline design.

It can help the detection rules identify:

- Replay attacks
- Some masquerade attacks

The rolling counter is located at byte B7 for the signals where it is specified.

## Expected Normal Bus Load

The proposed normal traffic produces approximately:

```text
Brake          50 frames/second
Steering       100 frames/second
RPM            100 frames/second
Speed          50 frames/second
Temperature    10 frames/second
Infotainment   10 frames/second
--------------------------------
Total          ~320 frames/second
```

This approximate baseline is important for later detection of abnormal traffic rates.

## Relevance to Member 2

The CAN baseline is important for the attacker and sniffer modules.

The attacker module will later generate controlled malicious traffic on `vcan0`.

The C sniffer will later capture CAN frames and forward structured frame information to the ML engine.

Understanding the normal CAN IDs, timing, DLC and payload structure is therefore required before implementing attack scenarios and traffic monitoring.

## Important Project Note

The payload layouts, final ECU IDs, periods and rolling-counter details are marked as proposed in the Week 1 design document.

The final values are to be confirmed by the ECU simulator owner and team lead.

Therefore, these values should be treated as the current project baseline and not independently changed by Member 2.

## Result

Day 4 established an understanding of:

1. The CAN environment used by CAN-Sentinel.
2. Classic CAN and the 11-bit identifier scope.
3. CAN ID, DLC and payload concepts used in the project.
4. The normal ECU traffic baseline.
5. Message timing and approximate bus load.
6. The purpose of the rolling counter.
7. Why the baseline is important for the attacker and sniffer modules.

This provides the required foundation for the attacker skeleton planned for Day 5.
