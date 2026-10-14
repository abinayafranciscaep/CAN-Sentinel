# ECU Simulator

C-based six-ECU simulator for the CAN-Sentinel project. It uses Linux SocketCAN to
transmit normal, periodic CAN traffic on the virtual bus `vcan0`. This traffic is the
legitimate baseline that the logger records and the intrusion detection engine learns from.

Owner: Abdul Haleem P R (Member 1) | Branch: `member-1` | Source: `ecu_simulator.c`

---

## Quick start

```bash
# 1. Create vcan0 (once per boot)
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# 2. Compile (from the repository root)
gcc -Wall -Wextra -o ecu_sim/ecu_simulator ecu_sim/ecu_simulator.c

# 3. Run, then watch traffic in a second terminal
./ecu_sim/ecu_simulator
candump vcan0
```

Stop the simulator with `Ctrl+C`. It exits cleanly and prints a confirmation message.

---

## Contents

- [Prerequisites](#prerequisites)
- [Configure the virtual CAN interface](#configure-the-virtual-can-interface)
- [Compile](#compile)
- [Run](#run)
- [CAN message protocol](#can-message-protocol)
- [Why these CAN IDs](#why-these-can-ids)
- [Signal payload format](#signal-payload-format)
- [Scheduler and timing behaviour](#scheduler-and-timing-behaviour)
- [Transmission-rate validation](#transmission-rate-validation)
- [Per-ID timing check](#per-id-timing-check)
- [Validate signal variation](#validate-signal-variation)
- [Use with the logger (recording datasets)](#use-with-the-logger-recording-datasets)
- [Known limitations](#known-limitations)
- [Notes](#notes)

---

## Prerequisites

- Kali Linux (or another Linux distribution with SocketCAN support)
- GCC
- `can-utils` (for `candump` and `cansend`)
- An active `vcan0` interface

```bash
sudo apt update
sudo apt install -y gcc can-utils
```

## Configure the virtual CAN interface

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
ip link show vcan0
```

`ip link show vcan0` should report the interface as `UP`. If `ip link add` reports
`File exists`, the interface is already configured and only `ip link set up vcan0` is
needed. `vcan0` is not persistent and must be recreated after a reboot.

## Compile

From the repository root:

```bash
gcc -Wall -Wextra -o ecu_sim/ecu_simulator ecu_sim/ecu_simulator.c
```

From a separate test directory (for example a Kali workspace copy):

```bash
gcc -Wall -Wextra -o ecu_simulator ecu_simulator.c
```

The source compiles with GCC 16.2.0 without warnings or errors. The executable
`ecu_sim/ecu_simulator` is a build artifact; it is listed in `.gitignore` and is
never committed.

## Run

```bash
./ecu_sim/ecu_simulator
```

Expected startup banner:

```text
CAN-Sentinel ECU Simulator Started
CAN interface: vcan0
Protocol: six periodic ECU frames, DLC 8
Signal simulation: enabled
Timing jitter: approximately +/-1 ms
Press Ctrl+C to stop.
```

The simulator transmits continuously until it receives `Ctrl+C` (SIGINT) or SIGTERM.
If `vcan0` is missing or the socket cannot be created, bound or written to, it prints a
clear error and exits with a non-zero status instead of running silently.

## CAN message protocol

Finalized protocol from the team design document (`docs/week1_design.md`, Section 2).

| CAN ID | ECU / signal | Period | Frames/s | DLC |
|---|---|---:|---:|---:|
| `0x0A0` | Brake | 20 ms | 50 | 8 |
| `0x0B0` | Steering | 10 ms | 100 | 8 |
| `0x100` | Engine RPM | 10 ms | 100 | 8 |
| `0x200` | Vehicle speed | 20 ms | 50 | 8 |
| `0x300` | Engine temperature | 100 ms | 10 | 8 |
| `0x600` | Infotainment heartbeat | 100 ms | 10 | 8 |
| | **Total** | | **320** | |

The diagnostic ID `0x7DF` is event-driven and is not sent by the simulator.

## Why these CAN IDs

On a CAN bus, when two nodes transmit at the same time, the frame with the **lower
identifier wins arbitration** and is sent first. Safety-critical messages therefore get
the lowest IDs: brake (`0x0A0`) and steering (`0x0B0`) always win over engine, speed,
temperature and infotainment traffic. The IDs are simulation-specific and do not
represent a production vehicle's CAN database.

## Signal payload format

All frames: DLC 8, multi-byte values big-endian, unused bytes `0x00`, and byte 7 is an
independent rolling counter (0-255, wrapping to 0) for each ECU.

| CAN ID | Payload fields | Simulated range |
|---|---|---|
| `0x0A0` | Byte 0: brake pressure; byte 1: brake switch (0 = off, 1 = on); byte 7: counter | Pressure 0-100 |
| `0x0B0` | Bytes 0-1: signed steering angle in 0.1 degree units; byte 7: counter | -45.0 to +45.0 degrees (-450 to +450) |
| `0x100` | Bytes 0-1: engine RPM; byte 7: counter | 800-4000 RPM |
| `0x200` | Byte 0: vehicle speed in km/h; byte 7: counter | 0-130 km/h |
| `0x300` | Byte 0: engine temperature as degrees C + 40; byte 7: counter | 80-105 degrees C |
| `0x600` | Byte 0: infotainment status; byte 7: counter | 0 or 1 |

Every signal is clamped to its range before encoding, so normal traffic never contains
out-of-range values that the detection engine could mistake for an attack.

Example frames and how to read them:

| Frame | Meaning |
|---|---|
| `0A0#4701000000000066` | Brake pressure 71, brake on, counter 0x66 |
| `0B0#FF4F00000000007F` | Steering -17.7 degrees (0xFF4F = -177), counter 0x7F |
| `100#07A600000000007A` | 1958 RPM, counter 0x7A |
| `300#89000000000000B3` | 137 - 40 = 97 degrees C, counter 0xB3 |

## Scheduler and timing behaviour

- Each ECU has its own nominal period and next deadline.
- The next deadline is calculated from the **previous scheduled deadline**, not from the
  time a frame was actually sent, so small delays do not accumulate into drift.
- If an ECU falls behind by one or more whole periods, the missed deadlines are
  **skipped** instead of being sent as a catch-up burst, which would distort the baseline.
- About +/-1 ms of random jitter is applied to every interval and averages to zero, so the
  long-run rate equals the nominal rate.

Actual timing depends on operating-system scheduling; see the measured results below.

## Transmission-rate validation

With the simulator running, in a second terminal:

```bash
timeout 10s candump -t a vcan0 > /tmp/can_updated_test.log
wc -l /tmp/can_updated_test.log
head -n 1 /tmp/can_updated_test.log
tail -n 1 /tmp/can_updated_test.log
awk '{print $3}' /tmp/can_updated_test.log | sort | uniq -c
```

The measured rate is the frame count divided by the time between the first and last
timestamps. With `candump -t a`, the CAN ID is the third field.

| Capture | Frames | Duration (s) | Measured rate |
|---|---:|---:|---:|
| 1 | 3,199 | 9.994203 | 320.09 frames/s |
| 2 | 3,197 | 9.992603 | 319.94 frames/s |
| 3 | 3,198 | 9.991346 | 320.08 frames/s |
| **Average** | **3,198** | | **320.03 frames/s** |

Per-ID counts (expected values for a 10-second capture):

| CAN ID | Expected | Capture 1 | Capture 2 |
|---|---:|---:|---:|
| `0x0A0` | 500 | 500 | 499 |
| `0x0B0` | 1,000 | 998 | 998 |
| `0x100` | 1,000 | 1,001 | 1,000 |
| `0x200` | 500 | 500 | 500 |
| `0x300` | 100 | 100 | 100 |
| `0x600` | 100 | 100 | 100 |

All three captures contained all six expected IDs; per-ID counts were recorded for the
first two. Every count is within about 0.2 % of nominal, and the average rate of
320.03 frames/s matches the 320 frames/s target. The scheduler change and these
measurements are documented in detail in `docs/member-1/README.md` (Step 8).

## Per-ID timing check

The total rate can look correct even if one ECU is irregular, so check the interval
between frames for each ID:

```bash
awk '{gsub(/[()]/,"",$1); id=$3;
  if (id in last) { d=($1-last[id])*1000; s[id]+=d; n[id]++;
    if (!(id in mn) || d<mn[id]) mn[id]=d; if (d>mx[id]) mx[id]=d }
  last[id]=$1 }
  END { for (i in n) printf "%s  n=%d  avg=%.2f ms  min=%.2f ms  max=%.2f ms\n",
        i, n[i], s[i]/n[i], mn[i], mx[i] }' /tmp/can_updated_test.log | sort
```

Expected: average close to the nominal period (20, 10, 10, 20, 100, 100 ms) and min/max
within about +/-2 ms of it.

| CAN ID | Nominal | Average | Min | Max |
|---|---:|---:|---:|---:|
| `0x0A0` | 20 ms | TO ADD | TO ADD | TO ADD |
| `0x0B0` | 10 ms | TO ADD | TO ADD | TO ADD |
| `0x100` | 10 ms | TO ADD | TO ADD | TO ADD |
| `0x200` | 20 ms | TO ADD | TO ADD | TO ADD |
| `0x300` | 100 ms | TO ADD | TO ADD | TO ADD |
| `0x600` | 100 ms | TO ADD | TO ADD | TO ADD |

Member 3's CSV validator (`dashboard/validate_csv.py` on `member-3`) also reports per-ID
periods for recorded CSV files.

## Validate signal variation

```bash
candump -n 40 vcan0
```

Check that all six IDs appear, every frame shows `[8]`, signal values change over time,
and each ECU's counter in byte 7 increments independently.

## Use with the logger (recording datasets)

The team's normal-traffic datasets are recorded by running the simulator and Member 3's
logger at the same time:

```bash
# Terminal 1: start the simulator
./ecu_sim/ecu_simulator

# Terminal 2: start the logger (Member 3, branch member-3)
python3 dashboard/can_logger.py ...   # confirm the exact arguments with Sadhamail
```

Plan: three 10-minute runs saved as `data/normal_run1_<MMDD>.csv`,
`data/normal_run2_<MMDD>.csv` and `data/normal_run3_<MMDD>.csv`, each checked with the
validator. Runs 1-2 are used for training and run 3 for false-alarm testing.

## Known limitations

- Traffic runs on a virtual bus (`vcan0`); there is no physical CAN hardware, bit timing or
  bus arbitration delay.
- Timing depends on Linux scheduling inside the VM; heavy host load can add jitter.
- Signal values are simulated with bounded random changes, not a physical vehicle model.
- Planned (Step 10 of the Member 1 guide): signals are updated on a fixed interval instead
  of with every brake frame, so the brake switch changes every few seconds rather than
  several times per second; RPM follows vehicle speed; and an optional random seed
  (`./ecu_sim/ecu_simulator 42`) gives repeatable runs. This README will be updated when
  that step is done.

## Notes

- Linux only (uses SocketCAN headers and APIs).
- `vcan0` must be up before starting the simulator.
- Nominal aggregate rate 320 frames/s; measured 320.03 frames/s on average in the Kali test
  environment.
- Results above apply to the recorded test runs and may vary slightly on other systems.
- The simulator does not communicate with any physical vehicle ECU.
