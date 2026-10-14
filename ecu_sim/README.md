# ECU Simulator

## Overview

The ECU Simulator is a C-based component of the CAN-Sentinel project. It uses Linux SocketCAN to simulate six automotive Electronic Control Units (ECUs) and transmit Controller Area Network (CAN) frames through the virtual CAN interface `vcan0`.

The simulator generates periodic CAN traffic with varying signal values, independent rolling counters, and approximately ±1 ms timing jitter. Its scheduling logic advances from previous deadlines and skips missed deadlines to reduce accumulated timing drift and avoid bursts of catch-up frames.

The simulator is designed to generate normal baseline CAN traffic for testing and developing the CAN-Sentinel intrusion detection system.

Source file: `ecu_simulator.c`

## Prerequisites

The following tools and components are required:

- Kali Linux or another Linux distribution with SocketCAN support
- GCC compiler
- `can-utils` package for monitoring CAN frames
- A configured and active `vcan0` virtual CAN interface

The compiler and CAN utilities can be installed with:

```bash
sudo apt update
sudo apt install -y gcc can-utils
```

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

The interface must be active before starting the simulator. `vcan0` is not persistent and must be recreated after a reboot.

## Compile the ECU Simulator

From the root directory of the CAN-Sentinel repository, compile the source code using:

```bash
gcc -Wall -Wextra -o ecu_sim/ecu_simulator ecu_sim/ecu_simulator.c
```

The `-Wall` and `-Wextra` options enable additional compiler warnings.

If the source file has been copied into a separate test directory (for example, a Kali Linux workspace), compile from that directory instead:

```bash
gcc -Wall -Wextra -o ecu_simulator ecu_simulator.c
```

The finalized source code was compiled successfully with GCC 16.2.0 without compiler warnings or errors. The compiled executable is a build artifact and should not be committed to the repository.

## Run the ECU Simulator

From the repository root, execute:

```bash
./ecu_sim/ecu_simulator
```

The simulator prints a startup banner and then transmits periodic CAN frames through `vcan0` using the configured ECU identifiers, payload formats, transmission periods, and timing jitter.

Press `Ctrl+C` to stop the simulator. It stops gracefully and prints a confirmation message.

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

Multi-byte values are big-endian.

| CAN ID | Payload Fields |
|---|---|
| `0x0A0` | Byte 0: brake pressure (0–100); byte 1: brake switch (0 or 1); byte 7: rolling counter |
| `0x0B0` | Bytes 0–1: signed steering angle in 0.1-degree units; byte 7: rolling counter |
| `0x100` | Bytes 0–1: engine RPM; byte 7: rolling counter |
| `0x200` | Byte 0: vehicle speed in km/h; byte 7: rolling counter |
| `0x300` | Byte 0: engine temperature encoded as Celsius + 40; byte 7: rolling counter |
| `0x600` | Byte 0: infotainment status; byte 7: rolling counter |

Unused payload bytes are zero-filled.

The simulated signal ranges are:

| Signal | Range |
|---|---|
| Brake pressure | 0–100 |
| Steering angle | −45.0° to +45.0° (−450 to +450 in 0.1° units) |
| Engine RPM | 800–4000 |
| Vehicle speed | 0–130 km/h |
| Engine temperature | 80–105 °C |
| Infotainment status | 0 or 1 |

## Scheduler and Timing Behavior

The simulator uses periodic scheduling with approximately ±1 ms timing jitter.

The updated scheduler calculates each subsequent deadline from the previous scheduled deadline rather than resetting it based on the time at which a frame was transmitted. When a deadline has been missed, the scheduler advances past missed deadlines instead of attempting to transmit catch-up frames in bursts.

The jitter is applied to every interval and averages to zero. Each interval therefore stays within the nominal period ±1 ms and the long-run rate equals the nominal rate, although absolute transmission times can wander slowly relative to the start time.

This approach helps reduce accumulated timing drift and maintain a transmission rate close to the nominal target. Actual performance depends on operating-system scheduling and runtime conditions.

## Transmission-Rate Validation

The nominal aggregate transmission rate is calculated from the six configured ECU periods:

- Brake: 50 frames/s
- Steering: 100 frames/s
- Engine RPM: 100 frames/s
- Vehicle speed: 50 frames/s
- Engine temperature: 10 frames/s
- Infotainment: 10 frames/s

**Nominal aggregate rate: 320 frames/s**

Each capture lasts approximately 10 seconds. With the simulator running, the following commands were used in a second terminal:

```bash
timeout 10s candump -t a vcan0 > /tmp/can_updated_test.log
wc -l /tmp/can_updated_test.log
head -n 1 /tmp/can_updated_test.log
tail -n 1 /tmp/can_updated_test.log
awk '{print $3}' /tmp/can_updated_test.log | sort | uniq -c
```

The measured rate is the frame count divided by the time between the first and last timestamps. With the `candump -t a` output format, the CAN identifier is the third field.

Three captures were performed:

| Capture | Frames Captured | Duration (s) | Measured Rate |
|---|---:|---:|---:|
| First | 3,199 | 9.994203 | 320.09 frames/s |
| Second | 3,197 | 9.992603 | 319.94 frames/s |
| Third | 3,198 | 9.991346 | 320.08 frames/s |
| **Average** | **3,198** | — | **320.03 frames/s** |

The measured average rate was approximately 320.03 frames/s, close to the nominal target of 320 frames/s. All three captures contained traffic from all six expected CAN identifiers.

Per-identifier counts for the first two captures were:

| CAN ID | Expected in 10 s | First Capture | Second Capture |
|---|---:|---:|---:|
| `0x0A0` | 500 | 500 | 499 |
| `0x0B0` | 1,000 | 998 | 998 |
| `0x100` | 1,000 | 1,001 | 1,000 |
| `0x200` | 500 | 500 | 500 |
| `0x300` | 100 | 100 | 100 |
| `0x600` | 100 | 100 | 100 |

These results were measured in the Kali Linux test environment using the updated scheduler.

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
- The nominal aggregate transmission rate is 320 frames/s; measured performance may vary slightly.
- The scheduler skips missed deadlines to reduce timing drift and prevent catch-up bursts.
- The configured timing jitter is approximately ±1 ms.
- This simulator generates virtual CAN traffic and does not communicate directly with a physical vehicle ECU.
- The transmission-rate results above apply to the recorded test runs and are not a guarantee of identical performance on every system.
