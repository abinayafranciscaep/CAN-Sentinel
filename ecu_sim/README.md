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

### Standard Build Automation (`Makefile`)

The primary and recommended build method uses the unified `Makefile`:

```bash
# Compile both the simulator and the automated test runner
make

# Or from repository root:
make -C ecu_sim
```

Available build targets:

| Command | Action | Description |
| :--- | :--- | :--- |
| `make` / `make all` | Compile binaries | Builds `ecu_simulator` and `test_payloads` with `-Wall -Wextra -Wpedantic -std=c11 -O2` |
| `make test` | Run test suite | Compiles and executes the 7/7 automated unit test suite |
| `make setup-vcan` | Setup network | Checks and configures the Linux `vcan0` virtual interface |
| `make clean` | Clean workspace | Safely deletes compiled executable binaries |
| `make help` | Help menu | Prints target descriptions and usage guide |

### Alternative: Manual Compilation (without Make)

You can also compile individual binaries manually using direct `gcc` commands:

From the repository root:

```bash
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -o ecu_sim/ecu_simulator ecu_sim/ecu_simulator.c
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -o ecu_sim/test_payloads ecu_sim/test_payloads.c
```

From a separate test directory (for example a Kali workspace copy):

```bash
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -o ecu_simulator ecu_simulator.c
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -o test_payloads test_payloads.c
```

The source compiles with GCC without warnings or errors under `-Wall -Wextra -Wpedantic -std=c11 -O2`. The compiled binaries (`ecu_simulator` and `test_payloads`) are build artifacts listed in `.gitignore` and are never committed.

## Run

### Default execution (random seed from current time)

```bash
./ecu_sim/ecu_simulator    # Or ./ecu_simulator in ~/CAN-Sentinel/ecu-simulator
```

### Reproducible execution (explicit random seed)

To reproduce a previous simulation run or generate identical baseline signal patterns for deterministic testing:

```bash
./ecu_sim/ecu_simulator 12345    # Or ./ecu_simulator 12345 in ~/CAN-Sentinel/ecu-simulator
```

Expected startup banner:

```text
Random seed: 12345
CAN-Sentinel ECU Simulator Started
CAN interface: vcan0
Protocol: six periodic ECU frames, DLC 8
Signal simulation: enabled
Timing jitter: approximately +/-1 ms
Press Ctrl+C to stop.
```

### Live Telemetry and Execution Summary

While transmitting, the simulator outputs an automated telemetry status line every 5 seconds, displaying runtime `[MM:SS]`, cumulative frame count, real-time transmission rate, vehicle speed, coupled engine RPM, steering angle, and brake pedal engagement:

```text
[TELEMETRY] [00:05] Frames:    1600 | Rate: 320.0 fps | Speed:  18 km/h | RPM: 1245 | Steer:  +4.5 deg | Brake: OFF
[TELEMETRY] [00:10] Frames:    3201 | Rate: 320.1 fps | Speed:  32 km/h | RPM: 1590 | Steer:  +8.0 deg | Brake: OFF
[TELEMETRY] [00:15] Frames:    4801 | Rate: 320.0 fps | Speed:  46 km/h | RPM: 1945 | Steer: +12.5 deg | Brake: ON (64%)
[TELEMETRY] [00:20] Frames:    6401 | Rate: 320.0 fps | Speed:  35 km/h | RPM: 1680 | Steer:  +9.0 deg | Brake: ON (64%)
```

Upon stopping (`Ctrl+C` or SIGTERM), the simulator outputs a final execution summary confirming total frames, total elapsed time, and average throughput:

```text
CAN-Sentinel ECU Simulator stopped.
Execution summary: 9602 frames transmitted in 30.00 seconds (average rate: 320.07 fps).
```

The simulator prints the active seed upon startup and transmits continuously until it receives `Ctrl+C` (SIGINT) or SIGTERM. If invalid arguments or values outside 32-bit unsigned bounds are passed, or if `vcan0` is missing, it prints a clear error and exits with a non-zero status instead of running silently:

```bash
$ ./ecu_sim/ecu_simulator abc
Invalid seed: abc

$ ./ecu_sim/ecu_simulator 10 20
Usage: ./ecu_sim/ecu_simulator [seed]
```

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
- If an ECU falls behind, a bounded slack window (`SCHEDULER_SLACK_PERIODS 5`) allows
  VM scheduling delays (up to 50 ms) to recover without discarding frames, while larger pauses
  are skipped to avoid burst flooding.
- For short intervals (< 2 ms), `sched_yield()` is used instead of `nanosleep()` to prevent
  hypervisor timer oversleep on high-frequency frames.
- Process scheduling priority is elevated via `nice(-10)` to protect transmission timing
  from background logging load.
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

| CAN ID | Expected | Capture 1 | Capture 2 | Capture 3 |
|---|---:|---:|---:|---:|
| `0x0A0` | 500 | 500 | 499 | 499 |
| `0x0B0` | 1,000 | 998 | 998 | 998 |
| `0x100` | 1,000 | 1,001 | 1,000 | 1,000 |
| `0x200` | 500 | 500 | 500 | 500 |
| `0x300` | 100 | 100 | 100 | 100 |
| `0x600` | 100 | 100 | 100 | 100 |

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
| `0x0A0` | 20 ms | 20.06 ms | 8.98 ms | 43.04 ms |
| `0x0B0` | 10 ms | 10.12 ms | 1.31 ms | 35.79 ms |
| `0x100` | 10 ms | 10.10 ms | 0.53 ms | 39.96 ms |
| `0x200` | 20 ms | 20.12 ms | 8.99 ms | 46.41 ms |
| `0x300` | 100 ms | 99.99 ms | 93.24 ms | 105.80 ms |
| `0x600` | 100 ms | 100.00 ms | 90.74 ms | 107.88 ms |

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

## Automated payload and protocol tests (Step 12)

A dedicated test suite (`test_payloads.c`) tests frame formats, 255 -> 0 counter wrapping, signed steering decoding, +40 temperature offset, dynamic coupling, and deterministic seed reproducibility without requiring a live SocketCAN network:

```bash
# Recommended: build and execute test suite with Make
make test

# Alternative manual build & run
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -o ecu_sim/test_payloads ecu_sim/test_payloads.c
./ecu_sim/test_payloads    # Or ./test_payloads in ~/CAN-Sentinel/ecu-simulator
```

## CAN Database (can_sentinel.dbc)

The CAN network specification is formalized in [`can_sentinel.dbc`](can_sentinel.dbc) using the industry-standard Vector DBC database format. This enables automated decoding of live SocketCAN traffic in Wireshark, Vector CANoe, or Python (`cantools`).

### Database Message and Signal Mapping

| CAN ID (Hex) | Message Name | Cycle Time | Signal Name | Bit Start / Len | Endianness | Scale & Offset | Physical Range & Unit |
| :---: | :--- | :---: | :--- | :---: | :---: | :---: | :---: |
| `0x0A0` (160) | `Brake_Message` | 20 ms | `Brake_Pressure`<br>`Brake_Switch`<br>`Brake_Rolling_Counter` | `7 \| 8`<br>`15 \| 8`<br>`63 \| 8` | Big (Motorola)<br>Big (Motorola)<br>Big (Motorola) | `1.0, 0`<br>`1.0, 0`<br>`1.0, 0` | `0` to `100 %`<br>`0` (Released) or `1` (Pressed)<br>`0` to `255` |
| `0x0B0` (176) | `Steering_Message` | 10 ms | `Steering_Angle`<br>`Steering_Rolling_Counter` | `7 \| 16`<br>`63 \| 8` | Big (Motorola, signed)<br>Big (Motorola) | `0.1, 0`<br>`1.0, 0` | `-45.0` to `+45.0 deg`<br>`0` to `255` |
| `0x100` (256) | `Engine_Message` | 10 ms | `Engine_RPM`<br>`Engine_Rolling_Counter` | `7 \| 16`<br>`63 \| 8` | Big (Motorola)<br>Big (Motorola) | `1.0, 0`<br>`1.0, 0` | `800` to `4000 RPM`<br>`0` to `255` |
| `0x200` (512) | `Speed_Message` | 20 ms | `Vehicle_Speed`<br>`Speed_Rolling_Counter` | `7 \| 8`<br>`63 \| 8` | Big (Motorola)<br>Big (Motorola) | `1.0, 0`<br>`1.0, 0` | `0` to `130 km/h`<br>`0` to `255` |
| `0x300` (768) | `Temperature_Message` | 100 ms | `Engine_Temperature`<br>`Temp_Rolling_Counter` | `7 \| 8`<br>`63 \| 8` | Big (Motorola)<br>Big (Motorola) | `1.0, -40`<br>`1.0, 0` | `80` to `105 degC`<br>`0` to `255` |
| `0x600` (1536) | `Infotainment_Message` | 100 ms | `Infotainment_Status`<br>`Info_Rolling_Counter` | `7 \| 8`<br>`63 \| 8` | Big (Motorola)<br>Big (Motorola) | `1.0, 0`<br>`1.0, 0` | `0` (Inactive) or `1` (Active)<br>`0` to `255` |

### Decoding in Python (`cantools`)

```python
import cantools

# Load the database
db = cantools.database.load_file("ecu_sim/can_sentinel.dbc")

# Decode a sample Brake frame: 0A0#4701000000000066
decoded = db.decode_message(0x0A0, bytes.fromhex("4701000000000066"))
print(decoded)
# Output: {'Brake_Pressure': 71, 'Brake_Switch': 'PRESSED', 'Brake_Rolling_Counter': 102}
```

## Known limitations

- Traffic runs on a virtual bus (`vcan0`); there is no physical CAN hardware, bit timing or
  bus arbitration delay.
- Timing depends on Linux scheduling inside the VM; heavy host load can add jitter.
- Signal values are simulated with bounded random changes, not a physical vehicle model.
- Realistic signal simulation (Step 10): Signals update on a fixed 50 ms schedule (`SIGNAL_UPDATE_US`), the brake switch holds state for 2–6 seconds with responsive brake pressure, engine RPM is derived from vehicle speed, and an optional random seed parameter (`./ecu_sim/ecu_simulator [seed]`) guarantees repeatable signal sequences for deterministic testing.

## Notes

- Linux only (uses SocketCAN headers and APIs).
- `vcan0` must be up before starting the simulator.
- Nominal aggregate rate 320 frames/s; measured 320.03 frames/s on average in the Kali test
  environment.
- Results above apply to the recorded test runs and may vary slightly on other systems.
- The simulator does not communicate with any physical vehicle ECU.