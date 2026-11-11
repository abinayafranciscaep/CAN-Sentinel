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

# 2. Build binaries & execute automated unit tests (7/7 PASS)
make
make test

# 3. Launch the multi-threaded ECU Simulator (Terminal 1)
./ecu_simulator --threads

# 4. Launch the Web-Based EV Sport Dashboard (Terminal 2)
make dashboard
# Then open in host browser: http://localhost:8080
```

Stop the simulator with `Ctrl+C`. It exits cleanly and joins all threads.

---

## Directory Structure

The `ecu_sim` module is completely self-contained for Member 1 deliverables:

```text
ecu_sim/
├── ecu_simulator.c        # Multi-threaded C SocketCAN 6-ECU simulator (pthreads, atomics)
├── test_payloads.c        # Automated unit verification suite (7/7 tests passed)
├── can_sentinel.dbc       # Vector DBC specification defining all 6 messages & signals
├── Makefile               # Unified build automation (make, test, dashboard, clean)
├── README.md              # Complete architecture, protocol, and usage documentation
└── dashboard/             # Self-contained EV Sport Digital Dashboard
    ├── bridge.py          # Native Linux SocketCAN-to-WebSocket bridge & HTTP server
    ├── index.html         # Hardware-accelerated Taycan / e-tron style digital cluster
    └── README.md          # Web dashboard architecture and WebSocket JSON schema
```

---

## Contents

- [Directory Structure](#directory-structure)
- [Prerequisites & Supported Environments](#prerequisites--supported-environments)
- [Windows 11 / WSL 2 Development Environment](#windows-11--wsl-2-development-environment)
- [Configure the virtual CAN interface](#configure-the-virtual-can-interface)
- [Compile & Build Automation](#compile)
- [Run](#run)
- [CAN message protocol](#can-message-protocol)
- [Why these CAN IDs](#why-these-can-ids)
- [Signal payload format](#signal-payload-format)
- [Scheduler and timing behaviour](#scheduler-and-timing-behaviour)
- [Transmission-rate validation](#transmission-rate-validation)
- [Per-ID timing check](#per-id-timing-check)
- [Validate signal variation](#validate-signal-variation)
- [Use with the logger (recording datasets)](#use-with-the-logger-recording-datasets)
- [Real-Time Web-Based EV Sport Digital Dashboard (`ecu_sim/dashboard/`)](#real-time-web-based-ev-sport-digital-dashboard-ecu_simdashboard)
- [Known limitations](#known-limitations)
- [Notes](#notes)

---

## Prerequisites & Supported Environments

The simulator requires a Linux environment with SocketCAN kernel support, GCC, and `can-utils`:

| Environment | Description | Setup Guide |
|---|---|---|
| **VirtualBox / VMware VM** | Traditional Kali Linux or Ubuntu virtual machine with native SocketCAN | Standard Linux package installation (`apt install can-utils gcc`) |
| **Windows 11 WSL 2** | Fast, lightweight Linux environment directly integrated with Windows host | Complete step-by-step [WSL 2 Custom Kernel Setup Guide](../docs/member-1/wsl2_setup.md) |

```bash
sudo apt update
sudo apt install -y gcc can-utils
```

---

## Windows 11 / WSL 2 Development Environment

While traditional Linux virtual machines (VirtualBox/VMware) support SocketCAN out-of-the-box, running tests in **Windows Subsystem for Linux 2 (WSL 2)** provides near-instant boot times, minimal RAM footprint, and native port forwarding to the Windows host (`http://localhost:8080`).

### Why Default WSL 2 Lacks Virtual CAN
Microsoft's default WSL 2 kernel intentionally leaves CAN bus networking disabled:
* `CONFIG_CAN` is not set (`n`)
* `CONFIG_CAN_RAW` is not set (`n`)
* `CONFIG_CAN_VCAN` is not set (`n`)

Running `sudo modprobe vcan` on default WSL 2 fails with: `modprobe: FATAL: Module vcan not found`.

### Running on the Tailored WSL 2 Kernel
A custom WSL 2 kernel was compiled from Microsoft's kernel source with CAN networking enabled:
* `CONFIG_CAN=y`
* `CONFIG_CAN_RAW=y`
* `CONFIG_CAN_VCAN=m`

Point your Windows host `C:\Users\<username>\.wslconfig` to the compiled `vmlinux` binary:
```ini
[wsl2]
kernel=C:\\Users\\<username>\\vmlinux-wsl2-can
```

### Daily Activation & Verification in WSL 2
1. **Bring up `vcan0`:**
   ```bash
   sudo modprobe vcan && sudo ip link add dev vcan0 type vcan 2>/dev/null; sudo ip link set up vcan0
   ip link show vcan0
   ```
2. **Execute Automated Unit Tests:**
   ```bash
   cd ecu_sim
   make test
   # Results: 7 / 7 tests passed (0 failed).
   ```
3. **Launch the Web Dashboard:**
   ```bash
   make dashboard
   ```
   Open `http://localhost:8080` directly in Windows Chrome / Edge (no VirtualBox network adapters or port forwarding needed).

> [!NOTE]
> For the comprehensive end-to-end kernel compilation instructions, build dependencies, and troubleshooting logs, refer to the dedicated [WSL 2 Custom Kernel Setup Guide](../docs/member-1/wsl2_setup.md).

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
| `make` / `make all` | Compile binaries | Builds `ecu_simulator` and `test_payloads` with `-Wall -Wextra -Wpedantic -std=c11 -O2 -pthread` |
| `make test` | Run test suite | Compiles and executes the 7/7 automated unit test suite |
| `make dashboard` | Launch dashboard | Launches the EV Sport Digital Dashboard & WebSocket bridge (`http://localhost:8080`) |
| `make setup-vcan` | Setup network | Checks and configures the Linux `vcan0` virtual interface |
| `make clean` | Clean workspace | Safely deletes compiled executable binaries |
| `make help` | Help menu | Prints target descriptions and usage guide |

### Alternative: Manual Compilation (without Make)

You can also compile individual binaries manually using direct `gcc` commands:

From the repository root:

```bash
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -pthread -o ecu_sim/ecu_simulator ecu_sim/ecu_simulator.c -lpthread -lrt
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -o ecu_sim/test_payloads ecu_sim/test_payloads.c
```

From a separate test directory (for example a Kali workspace copy):

```bash
gcc -Wall -Wextra -Wpedantic -std=c11 -O2 -pthread -o ecu_simulator ecu_simulator.c -lpthread -lrt
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
| `0x0A0` | Byte 0: brake pressure; byte 1: brake switch (0 = off, 1 = on); byte 7: counter | Pressure 0-100; Counter 0-255 |
| `0x0B0` | Bytes 0-1: signed steering angle in 0.1 degree units; byte 7: counter | -45.0 to +45.0 degrees (-450 to +450); Counter 0-255 |
| `0x100` | Bytes 0-1: engine RPM; byte 7: counter | 800-4000 RPM; Counter 0-255 |
| `0x200` | Byte 0: vehicle speed in km/h; byte 7: counter | 0-130 km/h; Counter 0-255 |
| `0x300` | Byte 0: engine temperature as degrees C + 40; byte 7: counter | 80-105 degrees C; Counter 0-255 |
| `0x600` | Byte 0: infotainment status; byte 7: counter | Status 0 or 1; Counter 0-255 |

> [!NOTE]
> **Byte 7 Counter Range Clarification:**
> Byte 7 carries an independent 8-bit unsigned integer (`uint8_t`) rolling counter with an explicit range of **`0 to 255` (`0x00` to `0xFF`)**, wrapping from `255 → 0`. It does **not** use a 4-bit nibble (`0–15`). Each ECU increments its counter independently per frame.

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

## Multi-Threaded Concurrency Architecture (`pthreads` & C11 Atomics)

The simulator features a high-concurrency multi-threaded distributed architecture that models real-world automotive ECUs as independent POSIX threads (`pthread`).

### Command-Line Execution Options

```bash
# 1. Default: in-place visual ANSI instrument cluster (single-threaded)
./ecu_sim/ecu_simulator

# 2. Multi-threaded mode: 6 autonomous ECU threads + 1 physics thread with live cluster
./ecu_sim/ecu_simulator --threads

# 3. Plain scrolling text telemetry (disables dashboard; recommended for file logging)
./ecu_sim/ecu_simulator --plain

# 4. Multi-threaded mode with deterministic seed and 60-second auto-stop duration
./ecu_sim/ecu_simulator --threads --duration 60 42

# 5. Live visual cluster with simultaneous background file logging
./ecu_sim/ecu_simulator --threads --log telemetry.log
```

## Modern ANSI Digital Instrument Cluster

The simulator features a real-time in-place terminal instrument cluster that transforms standard terminal output into an automotive digital dashboard.

### Key Cluster Features:
* **Zero-Flicker In-Place Redraw:** Uses ANSI cursor addressing (`\033[H`) to refresh the dashboard at 10 Hz without clearing the screen or causing terminal flicker.
* **Dynamic Multi-Tier ANSI Color Grading & Alert Thresholds:** Adheres to automotive display ergonomics (ISO 15008 / ISO 2575) using dynamic peripheral color grading across all gauges:
  * **Engine RPM:** Transitions from Cool Blue (`800–2,400 RPM`, Nominal) to Amber Warning (`2,401–3,200 RPM`, High Load) to Bold Redline Alert (`> 3,200 RPM`, `[⚠ REDLINE LIMIT]`).
  * **Coolant Temperature:** Dynamically shifts across 4 thermal zones: Cold Warmup Blue (`< 85 °C`, `[WARMUP PHASE]`), Optimal Green (`85–98 °C`, `[COOLANT NOMINAL]`), Elevated Amber (`98.1–102 °C`, `[⚠ ELEVATED TEMP]`), and Overheating Red (`> 102 °C`, `[🔥 OVERHEAT WARN]`).
  * **Braking Force:** Color-grades from Muted Gray (`0%`, `[○ RELEASED]`) to Amber (`1–50%`, `[● BRAKE ENGAGED]`) to Emergency Red (`> 50%`, `[🚨 HARD BRAKE]`).
  * **Vehicle Speed & Steering:** Speed dynamically shifts from City Green (`0–60 km/h`) to Highway Cyan (`61–100 km/h`) to High Speed Amber (`> 100 km/h`, `[⚡ HIGH SPEED]`). Steering shifts to Amber during severe lock angles (`> 35°`).
* **Progressive Multi-Zone Color Gradients:** Rather than rendering each bar in a single flat color, gauges physically illuminate through dedicated automotive operational color zones:
  * **Speed Bar:** Progressive build-up from City Green (`0–60 km/h`) $\rightarrow$ Highway Cruise Cyan (`61–100 km/h`) $\rightarrow$ High Speed Amber (`> 100 km/h`).
  * **RPM Rev Bar:** Progressive build-up from Cruise Cyan (`800–2,400 RPM`) $\rightarrow$ Powerband Amber (`2,401–3,200 RPM`) $\rightarrow$ Redline Alert Red (`> 3,200 RPM`).
  * **Braking Bar:** Progressive build-up from Normal Service Braking Amber (`1–50%`) $\rightarrow$ Emergency Redline Red (`> 50%`).
  * **Coolant Temp:** Progressive build-up from Warmup Cyan (`< 85 °C`) $\rightarrow$ Nominal Green (`85–98 °C`) $\rightarrow$ Elevated Amber (`98.1–102 °C`) $\rightarrow$ Overheat Red (`> 102 °C`).
* **Visual Polish & Ergonomic Spacing:** Designed with comfortable vertical row spacing between gauges, full-height dark charcoal solid LCD blocks (`█`) for unlit segments, modern rounded box borders (`╭───╮` / `╰───╯`), and an artificial horizon steering dial (`[◄───────────│►►●───────►]`).
* **Simultaneous Live Telemetry History Feed:** Integrates a rolling 50-second interval diagnostic telemetry event log (10 rolling snapshot rows) directly inside the cluster, displaying historical frames, transmission rates, speeds, RPMs, and braking engagement without screen tearing or visual flicker. Color grading carries over into the rolling log.
* **Dynamic PRND Transmission & Automatic Gear Indicator:** Automatic gear selector (`( P )`, `( R )`, `( N )`, `◄[ D1 ]►`–`◄[ D5 ]►`) coupled to vehicle speed and braking state, with active drive mode indicators (`[PARK ENGAGED]`, `[NEUTRAL IDLE]`, `[FORWARD D-1]`–`[FORWARD D-5]`).
* **Dynamic Graphical Gauges:** Live progress bars for Vehicle Speed, Engine RPM, Brake Pressure, and a center-aligned bidirectional Steering Angle indicator.
* **Per-ECU Real-Time Activity:** Real-time transmission metrics and frame counters for all 6 CAN IDs alongside their Linux scheduling policies (`SCHED_FIFO` vs `SCHED_OTHER`).
* **Smart Terminal Detection (`isatty`):** Automatically switches to plain text output if `stdout` is piped to a file (`./ecu_simulator > log.txt`) or a non-interactive CI runner, preventing escape character pollution.
* **Dual Architecture Support:** Automatically adapts its header and metrics whether running in Single-Threaded or Multi-Threaded distributed mode.

#### Dynamic Threshold Architecture

| Subsystem | Metric Range | ANSI Escape | Dynamic Status Badge | Operational Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Engine RPM** | `800 – 2,400 RPM`<br>`2,401 – 3,200 RPM`<br>`> 3,200 RPM` | `\033[1;36m` (Ice Cyan)<br>`\033[1;33m` (Amber)<br>`\033[1;31m` (Red) | `(Cruise: Nominal)`<br>` HIGH LOAD ZONE `<br>` ⚠ REDLINE LIMIT ` | Powertrain load state and redline proximity. |
| **Coolant Temp** | `< 85.0 °C`<br>`85.0 – 98.0 °C`<br>`98.1 – 102.0 °C`<br>`> 102.0 °C` | `\033[1;36m` (Ice Cyan)<br>`\033[1;32m` (Green)<br>`\033[1;33m` (Amber)<br>`\033[1;31m` (Red) | `[WARMUP PHASE]`<br>`[COOLANT NOMINAL]`<br>` ⚠ ELEVATED TEMP `<br>` 🔥 OVERHEAT WARN ` | Engine thermal management and cooling loop health. |
| **Brake System** | `0 %` (Switch OFF)<br>`1 – 50 %`<br>`> 50 – 100 %` | `\033[0;90m` (Gray)<br>`\033[1;33m` (Amber)<br>`\033[1;31m` (Red) | `[○ RELEASED]`<br>` ● BRAKE ENGAGED `<br>` 🚨 HARD BRAKE ` | Hydraulic line pressure and emergency stopping alert. |
| **Vehicle Speed** | `0 – 60 km/h`<br>`61 – 100 km/h`<br>`> 100 km/h` | `\033[1;32m` (Green)<br>`\033[1;36m` (Cyan)<br>`\033[1;33m` (Amber) | `(City Zone)`<br>`(Highway Cruise)`<br>` ⚡ HIGH SPEED ` | Road speed profile and overspeed advisory. |

```text
╭────────────────────────────────────────────────────────────────────────────────────────╮
│  ► CAN-SENTINEL AUTOMOTIVE ECU CLUSTER  (MULTI-THREADED DISTRIBUTED)                   │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  Interface: vcan0  │  Kernel: SocketCAN  │  Workers: 7 pthreads (C11 Lock-Free)        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  VEHICLE TELEMETRY DYNAMICS                                                            │
│                                                                                        │
│  GEAR  : ( P )  ( R )  ( N )  ◄[ D4 ]►   DRIVE MODE: [FORWARD D-4]                     │
│                                                                                        │
│  SPEED : [████████████████████████]  105 km/h   ⚡ HIGH SPEED                           │
│                                                                                        │
│  RPM   : [████████████████████████]  3350 RPM   ⚠ REDLINE LIMIT                        │
│                                                                                        │
│  BRAKE : [████████████████████████]  100 %      🚨 HARD BRAKE                          │
│                                                                                        │
│  STEER : [◄───────────│►►●───────►]   +1.2 deg  (Straight  )                           │
│                                                                                        │
│  TEMP  : [████████████████████████]   99.5 °C   ⚠ ELEVATED TEMP                        │
│                                                                                        │
│  INFO  : [● MEDIA ON ] Nav Gateway: Route Guidance Active                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  PER-ECU TRANSMISSION STATUS & REAL-TIME SCHEDULING                                    │
│                                                                                        │
│  [●] 0x0A0  Brake Controller     20 ms ( 50 Hz) │ Frames:     768 │ SCHED_FIFO (80)    │
│  [●] 0x0B0  Steering Gateway     10 ms (100 Hz) │ Frames:    1536 │ SCHED_FIFO (80)    │
│  [●] 0x100  Powertrain Engine    10 ms (100 Hz) │ Frames:    1530 │ SCHED_FIFO (50)    │
│  [●] 0x200  Speed Sensor         20 ms ( 50 Hz) │ Frames:     768 │ SCHED_FIFO (50)    │
│  [●] 0x300  Thermal Mgmt        100 ms ( 10 Hz) │ Frames:     153 │ SCHED_OTHER (0)    │
│  [●] 0x600  Infotainment Media  100 ms ( 10 Hz) │ Frames:     153 │ SCHED_OTHER (0)    │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  LIVE TELEMETRY FEED (ROLLING 50-SECOND WINDOW / 10 RECENT SNAPSHOTS)                  │
│                                                                                        │
│  [00:00] Frames:       0 │   0.0 fps │ Speed:  60 km/h │ RPM: 2300 │ Brake: OFF        │
│  [00:05] Frames:    1602 │ 320.1 fps │ Speed:  48 km/h │ RPM: 2010 │ Brake: OFF        │
│  [00:10] Frames:    3203 │ 320.1 fps │ Speed:  35 km/h │ RPM: 1680 │ Brake: ON (64%)   │
│  [00:15] Frames:    4804 │ 320.0 fps │ Speed:  22 km/h │ RPM: 1350 │ Brake: ON (100%)  │
│  [00:20] Frames:    6405 │ 320.0 fps │ Speed:  18 km/h │ RPM: 1250 │ Brake: ON (100%)  │
│  [00:25] Frames:    8006 │ 320.1 fps │ Speed:  32 km/h │ RPM: 1600 │ Brake: OFF        │
│  [00:30] Frames:    9607 │ 320.1 fps │ Speed:  45 km/h │ RPM: 1920 │ Brake: OFF        │
│  [00:35] Frames:   11208 │ 320.0 fps │ Speed:  58 km/h │ RPM: 2250 │ Brake: OFF        │
│  [00:40] Frames:   12809 │ 320.1 fps │ Speed:  62 km/h │ RPM: 2350 │ Brake: OFF        │
│  [00:45] Frames:   14410 │ 320.0 fps │ Speed: 105 km/h │ RPM: 3350 │ Brake: ON (100%)  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│  TIME: 00:45 / 01:00  [████████████]   75% │ TOTAL:   14410 frames (Rate: 320.0 fps) │
╰────────────────────────────────────────────────────────────────────────────────────────╯
 [Press Ctrl+C to stop simulation cleanly]
```

### Concurrency Design & Thread Allocation

| Thread | Subsystem | Period / Rate | Scheduling Policy | Real-Time Priority | Functional Safety |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `thread_brake` | Brake ECU (`0x0A0`) | 20 ms (50 Hz) | `SCHED_FIFO` | 80 | ASIL-D (Chassis Safety) |
| `thread_steer` | Steering ECU (`0x0B0`) | 10 ms (100 Hz) | `SCHED_FIFO` | 80 | ASIL-D (Chassis Safety) |
| `thread_engine` | Engine ECU (`0x100`) | 10 ms (100 Hz) | `SCHED_FIFO` | 50 | ASIL-B (Powertrain) |
| `thread_speed` | Speed ECU (`0x200`) | 20 ms (50 Hz) | `SCHED_FIFO` | 50 | ASIL-B (Powertrain) |
| `thread_temp` | Thermal ECU (`0x300`) | 100 ms (10 Hz) | `SCHED_OTHER` | 0 | QM (Monitoring) |
| `thread_info` | Infotainment (`0x600`) | 100 ms (10 Hz) | `SCHED_OTHER` | 0 | QM (Comfort) |
| `thread_physics` | Vehicle Dynamics Engine | 50 ms (20 Hz) | `SCHED_OTHER` | 0 | Physics Generator |
| `main` | Supervisor & Telemetry | 5000 ms (0.2 Hz) | `SCHED_OTHER` | 0 | Watchdog & Telemetry |

### Key Architectural Strengths

1. **Independent Sockets per ECU:** Each ECU worker thread opens and binds its own dedicated SocketCAN socket (`socket(PF_CAN, SOCK_RAW, CAN_RAW)`), eliminating kernel-level socket transmit lock contention.
2. **Lock-Free Concurrency (`<stdatomic.h>`):** Shared vehicle dynamics (speed, RPM, steering angle, brake state) are synchronized using C11 atomics with memory barrier semantics (`memory_order_acquire` / `memory_order_release`). No mutexes are used, eliminating lock contention and priority inversion.
3. **Absolute Monotonic Sleep (`clock_nanosleep`):** Each ECU thread sleeps using `CLOCK_MONOTONIC` and `TIMER_ABSTIME`, completely preventing cumulative timer drift.
4. **Graceful Multi-Thread Teardown:** Upon `SIGINT` (`Ctrl+C`), all threads are joined via `pthread_join()`, ensuring zero memory or file descriptor leaks on exit.

## Real-Time Web-Based EV Sport Digital Dashboard (`ecu_sim/dashboard/`)

In addition to the in-place ANSI terminal cluster, the `ecu_sim` module includes a self-contained, interactive browser-based digital instrument dashboard (Porsche Taycan / Audi e-tron GT style) located in `ecu_sim/dashboard/`.

### Directory Layout
```text
ecu_sim/dashboard/
├── bridge.py     # Native Python SocketCAN reader, JSON decoder, WebSocket & HTTP server
├── index.html    # 60 FPS HTML5 Canvas / WebGL dark glassmorphic dashboard UI
└── README.md     # Dedicated dashboard documentation and WebSocket payload specification
```

### Quick Launch with Make

```bash
# From the ecu_sim directory:
make dashboard
```

Once started, navigate to:
* **Under Windows 11 WSL 2:** `http://localhost:8080` (native port forward out-of-the-box)
* **Inside Kali Linux VM:** `http://localhost:8080`
* **From Windows host browser to VM:** `http://<kali-ip>:8080` (find your IP via `hostname -I`), or `http://localhost:8080` if VirtualBox forwarded port 8080.

---

### The 6 Decoded ECUs & Live WebSocket Protocol

The bridge (`bridge.py`) binds to the Linux `vcan0` interface using raw `AF_CAN` sockets, decodes all 6 baseline CAN message identifiers, tracks rolling sequence counters, calculates physical bus load, and broadcasts a unified JSON telemetry packet over RFC 6455 WebSockets (`ws://localhost:8080/ws`) at 20 Hz (every 50 ms):

| CAN ID | ECU Subsystem | Signals Decoded | Encoding & Engineering Units | UI Representation |
| :---: | :--- | :--- | :--- | :--- |
| **`0x0A0`** | **Brake Controller** | `brake_switch`<br>`brake_pressure` | Byte 0 (0: OFF, 1: ON)<br>Byte 1 (0–100 %) | Rear continuous LED lightbar glows neon red; numerical pressure display |
| **`0x0B0`** | **Steering Gateway** | `steering_angle` | Bytes 0–1 signed 16-bit big-endian (`-450` to `+450` deci-deg, factor 0.1) | Front virtual vehicle wheels turn dynamically; horizon steering needle |
| **`0x100`** | **Powertrain Engine** | `engine_rpm` | Bytes 0–1 unsigned 16-bit big-endian (800–4000 RPM) | Left 60 FPS swept radial tachometer dial with progressive amber/redline glow |
| **`0x200`** | **Speed Sensor** | `vehicle_speed` | Byte 0 unsigned integer (0–130 km/h) | Right 60 FPS swept radial speedometer dial with digital center readout |
| **`0x300`** | **Thermal Mgmt** | `engine_temp` | Byte 0 unsigned (+40 °C offset, range 80–105 °C) | Coolant temperature bar with dynamic nominal/overheat warning |
| **`0x600`** | **Infotainment** | `media_status` | Byte 0 (0: Inactive, 1: Active route guidance) | Route guidance banner & audio media indicator |

All 6 frames also feature an independent rolling sequence counter in **Byte 7 (0–255, wrapping $255 \rightarrow 0$)** that the bridge monitors for transmission continuity and packet loss.

### Physical Bus Load Monitoring
In addition to telemetry, the bridge calculates real-time physical CAN bus utilization at 500 kbps:
$$\text{Bit Overhead per Frame} \approx (47\text{ fixed bits} + 64\text{ data bits}) \times 1.2\text{ (bit stuffing factor)} \approx 133\text{ bits}$$
At the nominal baseline rate of 320 frames/sec:
$$\text{Bus Bandwidth} = 320 \times 133 = 42,560\text{ bps} \implies \approx 8.51\%\text{ physical bus load}$$
The dashboard visualizes this on a dedicated **Bus Load Gauge** (`0–100%`). When attack traffic occurs (such as a DoS flood attack by Member 2), the gauge surges into the red zone ($>80\%$), visibly demonstrating bus congestion and denial of service.

### Live WebSocket JSON Payload Schema
At 20 Hz, `bridge.py` emits the following structured JSON frame to all connected web clients:
```json
{
  "timestamp": 1793614174.998,
  "telemetry": {
    "speed": 65,
    "rpm": 2425,
    "brake_switch": 1,
    "brake_pressure": 75,
    "steering_angle": 12.4,
    "engine_temp": 94.5,
    "infotainment": 1,
    "gear": "D3"
  },
  "metrics": {
    "fps": 320.1,
    "total_frames": 19200,
    "bus_load_pct": 8.5,
    "active_ecus": 6
  }
}
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