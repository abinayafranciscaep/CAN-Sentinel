# CAN-Sentinel // Web-Based EV Sport Digital Dashboard

An interactive, real-time digital instrument cluster designed in the aesthetic of a **Porsche Taycan / Audi e-tron GT** for the **CAN-Sentinel** automotive intrusion detection system.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   C ECU Simulator (vcan0)   |
                      |    320 frames/sec baseline  |
                      +--------------+--------------+
                                     |
                                     v
                        [ Linux Virtual CAN: vcan0 ]
                                     |
                                     v
             +-----------------------------------------------+
             |       Python SocketCAN Bridge (bridge.py)     |
             |  - Native Linux AF_CAN raw socket reader      |
             |  - 6-ECU Telemetry & Protocol Decoder         |
             |  - Physical Bus Load Calculator (~8.2%)       |
             |  - RFC 6455 WebSocket Server (ws://...:8080) |
             |  - Static Asset HTTP Server (http://...:8080) |
             +-----------------------+-----------------------+
                                     |
                                     v
             +-----------------------------------------------+
             |      EV Sport Digital Frontend (index.html)   |
             |  - Dark Glassmorphic Taycan / e-tron UI       |
             |  - 60 FPS Dual Radial Swept Gauges            |
             |  - Articulated Front Wheels (0x0B0 Steering)  |
             |  - Active Neon Red Rear Brakes (0x0A0 Brake)  |
             |  - Holographic Transmission (P/R/N/D1-D5)     |
             |  - Physical Bus Load & 6-ECU Matrix           |
             |  - Web Audio Synthesized EV Sound Engine      |
             +-----------------------------------------------+
```

---

## CAN Protocol Baseline

The bridge and dashboard decode all 6 periodic ECUs broadcast at 320 frames/sec:

| CAN ID | ECU Name | Nominal Period | Frequency | Decoded Signals |
|---|---|---|---|---|
| `0x0A0` | Brake Controller | 20 ms | 50 Hz | Byte 0: Brake Pressure (0–100%), Byte 1: Switch (0/1), Byte 7: Rolling Counter |
| `0x0B0` | Steering Gateway | 10 ms | 100 Hz | Bytes 0–1: Signed Angle (-45.0° to +45.0°, 0.1° scale, big-endian), Byte 7: Counter |
| `0x100` | Powertrain ECM | 10 ms | 100 Hz | Bytes 0–1: Engine/Motor RPM (800–4000 RPM, big-endian), Byte 7: Counter |
| `0x200` | Speed Sensor | 20 ms | 50 Hz | Byte 0: Vehicle Speed (0–130 km/h), Byte 7: Counter |
| `0x300` | Thermal Management | 100 ms | 10 Hz | Byte 0: Coolant Temp (80–105 °C, DBC offset +40), Byte 7: Counter |
| `0x600` | Infotainment Gateway | 100 ms | 10 Hz | Byte 0: Route/Media Status (0=Off, 1=Active), Byte 7: Counter |

**Total Nominal Frame Rate:** `50 + 100 + 100 + 50 + 10 + 10 = 320 frames/sec`  
**Physical Bus Load @ 500 kbps:** `(320 frames/sec * 128 bits/frame) / 500,000 bps * 100% = ~8.19%`

---

## How to Run

### Option 1: On Kali Linux (Live SocketCAN `vcan0`)

1. Ensure `vcan0` is up (or run `make setup-vcan` in `ecu_sim`):
   ```bash
   sudo modprobe vcan
   sudo ip link add dev vcan0 type vcan 2>/dev/null || true
   sudo ip link set up vcan0
   ```
2. Start the C ECU simulator (in Terminal 1):
   ```bash
   cd ~/CAN-Sentinel/ecu-simulator
   make clean && make
   ./ecu_simulator --threads
   ```
3. Start the Web Dashboard Bridge (in Terminal 2):
   ```bash
   cd ~/CAN-Sentinel/ecu-simulator
   make dashboard
   ```
   *(Or alternatively, directly from inside `dashboard/`: `python3 bridge.py --interface vcan0 --port 8080`)*

4. Open the dashboard in Kali Firefox or your browser:
   ```
   http://localhost:8080
   ```
   * **From Windows host browser:** Open `http://<kali-ip>:8080` (find your VM's IP in Kali by running `hostname -I`).
   * **Tip for VirtualBox NAT:** In VirtualBox VM Settings $\rightarrow$ Network $\rightarrow$ Advanced $\rightarrow$ Port Forwarding, add a rule with Host Port `8080` and Guest Port `8080`. Then you can open `http://localhost:8080` directly in Windows!

### Option 2: On Windows or Test Environment (Without vcan0)

`bridge.py` includes an automatic zero-dependency high-fidelity physics simulator fallback.

```bash
python bridge.py --port 8080
```
Then navigate to:
```
http://localhost:8080
```

Alternatively, `index.html` can be opened directly in any modern browser (`Chrome`, `Edge`, `Firefox`), with built-in instant client-side physics simulation.

---

## Interactive Features

- **Speedometer (0–140 km/h):** Sweeping luminous needle, cyan arc trail, digital HUD, MPH conversion, and acceleration G-meter.
- **Tachometer (0–5000 RPM):** Power/RPM gauge with progressive amber and redline glow (> 3800 RPM).
- **Steering Wheel Articulation:** Front left and right wheels physically turn left/right in real time (-45° to +45°).
- **Rear Brake Glow:** Continuous rear LED lightbar and tail lamps illuminate neon red when braking engages.
- **Holographic Transmission:** `[ P ] [ R ] [ N ] ◄[ D1-D5 ]►` automatic gear calculation.
- **Bus Load & 6-ECU Health:** Real-time bus load percentage, frame counter, and per-node health cards with rolling counters.
- **Synthesized EV Sound:** Click the **EV SOUND** button in the header for real-time Web Audio EV motor synthesis modulated by speed and RPM.

---

## Visual Verification

![Web-Based EV Sport Dashboard](../screenshots/45-web-ev-dashboard.png)

*Real-time EV Sport Dashboard running side-by-side with SocketCAN 320 fps simulation.*
