# ECU Simulator

## Overview

The ECU Simulator is a C-based component of the CAN-Sentinel project. It uses Linux SocketCAN to simulate six automotive Electronic Control Units (ECUs) and transmit Controller Area Network (CAN) frames through the virtual CAN interface `vcan0`.

The simulator generates periodic CAN traffic with varying signal values, independent rolling counters, and approximately ±1 ms timing jitter. It is intended to generate normal baseline traffic for testing and developing the CAN-Sentinel intrusion detection system.

The source code is located at `ecu_simulator.c`.

## Prerequisites

The following tools and components are required:

- Kali Linux or another Linux distribution with SocketCAN support
- GCC compiler
- `can-utils` package for monitoring CAN frames
- A configured and active `vcan0` virtual CAN interface

## Configure the Virtual CAN Interface

If `vcan0` has not already been configured, run:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

If the interface already exists, do not run the `ip link add` command again.

Verify the interface status using:

```bash
ip link show vcan0
```

The interface must be active before starting the simulator.

## Compile the ECU Simulator

From the root directory of the CAN-Sentinel repository, compile the source code using:

```bash
gcc -Wall -Wextra -o ecu_sim/ecu_simulator ecu_sim/ecu_simulator.c
```

The `-Wall` and `-Wextra` options enable additional compiler warnings.

A successful compilation should complete without compiler errors or warnings.

## Run the ECU Simulator

From the repository root, execute:

```bash
./ecu_sim/ecu_simulator
```

The simulator should display startup information identifying the `vcan0` interface, the six periodic ECU frames, the eight-byte payload format, and the configured timing jitter.

Press `Ctrl+C` to stop the simulator.

## Verify CAN Frames

Open a separate terminal and run:

```bash
candump vcan0
```

Keep the simulator running in the first terminal while monitoring traffic in the second terminal.

Verify that the captured traffic contains all six expected CAN identifiers:

| CAN ID | ECU / Signal | Transmission Period | DLC |
|---|---|---:|---:|
| `0x0A0` | Brake | 20 ms | 8 |
| `0x0B0` | Steering | 10 ms | 8 |
| `0x100` | Engine RPM | 10 ms | 8 |
| `0x200` | Vehicle speed | 20 ms | 8 |
| `0x300` | Engine temperature | 100 ms | 8 |
| `0x600` | Infotainment | 100 ms | 8 |

All six periodic messages use a data length code (DLC) of 8 bytes. Byte 7 contains an independent rolling counter for each ECU.

## Signal Payload Format

| CAN ID | Payload Fields |
|---|---|
| `0x0A0` | Byte 0: brake pressure (0–100); byte 1: brake switch (0 or 1); byte 7: rolling counter |
| `0x0B0` | Bytes 0–1: signed steering angle in 0.1-degree units; byte 7: rolling counter |
| `0x100` | Bytes 0–1: engine RPM; byte 7: rolling counter |
| `0x200` | Byte 0: vehicle speed in km/h; byte 7: rolling counter |
| `0x300` | Byte 0: engine temperature encoded as Celsius + 40; byte 7: rolling counter |
| `0x600` | Byte 0: infotainment status; byte 7: rolling counter |

Unused payload bytes are zero-filled.

## Validate Signal Variation

To capture a limited number of frames for inspection, run:

```bash
candump -n 40 vcan0
```

Inspect the output to verify that:

- All six expected CAN identifiers appear during the capture.
- Each frame has DLC `[8]`.
- Signal values vary over time where applicable.
- Each ECU's rolling counter increments independently.

## Notes

- Compile and run the simulator on Linux because it uses Linux SocketCAN headers and APIs.
- Ensure that `vcan0` is active before running the simulator.
- The nominal aggregate transmission rate calculated from the configured periods is approximately 320 frames per second. This target must be confirmed through a measured capture.
- The configured timing jitter is approximately ±1 ms; actual scheduling behavior should be evaluated during testing.
- This simulator generates virtual CAN traffic and does not communicate directly with a physical vehicle ECU.
- Record build, runtime, timing, and transmission-rate results only after they have been verified in the test environment.