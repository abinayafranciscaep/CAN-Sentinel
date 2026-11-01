# WSL 2 Custom Kernel Setup Guide: SocketCAN & Virtual CAN (vcan0)

**Project:** CAN-Sentinel (Automotive ECU Intrusion Detection System)  
**Target Capability:** Linux SocketCAN (`vcan0`), `can-utils`, ECU Simulator (`ecu_sim`), and Web EV Sport Dashboard  
**Host Platform:** Windows 11 (WSL 2)  
**Distribution:** Kali Linux Rolling (or Ubuntu 22.04 / 24.04 LTS)  
**Author:** Abdul Haleem P R (Member 1) | **Branch:** `member-1`  
**Status:** ✅ Fully Verified & Operational  

---

## 1. Problem Statement & Motivation

CAN-Sentinel simulates automotive Controller Area Network (CAN) bus communication and detects security threats (replay attacks, fuzzing, telemetry spoofing, denial of service). The system relies on Linux **SocketCAN** (`vcan0`) network interfaces.

While a traditional VirtualBox or VMware virtual machine supports SocketCAN out of the box, running CAN-Sentinel inside **WSL 2** provides significant engineering advantages:
- **Instant Boot:** Starts in under 2 seconds without hypervisor overhead.
- **Dynamic Resource Allocation:** Consumes CPU and RAM only when active, avoiding fixed multi-gigabyte memory reservations and battery drain.
- **Native Filesystem Access:** Access Windows project directories seamlessly via `/mnt/c/` and `/mnt/d/`.
- **VS Code Remote Integration:** Direct pair-programming and debugging using the official VS Code WSL extension.

### The WSL 2 Kernel Limitation
Microsoft's standard production WSL 2 kernel is optimized for generic web and cloud workloads, and **CAN networking is disabled by default**:
- `CONFIG_CAN` is not set
- `CONFIG_CAN_RAW` is not set
- `CONFIG_CAN_VCAN` is not set

Attempting to run `sudo modprobe vcan` or `sudo ip link add dev vcan0 type vcan` on an unmodified WSL 2 kernel results in:
```text
modprobe: FATAL: Module vcan not found in directory /lib/modules/...
RTNETLINK answers: Operation not supported
```

This guide details how to compile a tailored Microsoft WSL 2 kernel with native SocketCAN and Virtual CAN enabled, export it to Windows, and run the complete CAN-Sentinel stack directly on Windows 11.

---

## 2. Step-by-Step Installation & Kernel Build

### Step 1: Install WSL 2 and Kali Linux
From an elevated Windows PowerShell or Windows Terminal:
```powershell
# Install WSL with Kali Linux (or Ubuntu)
wsl --install -d kali-linux
```
Reboot Windows if prompted, then launch Kali Linux and configure your username and password.

---

### Step 2: Install Kernel Build Dependencies & CAN Utilities
Inside your WSL 2 terminal, refresh package repositories and install the compiler toolchain, kernel build dependencies, and `can-utils`:

```bash
sudo apt update
sudo apt install -y build-essential flex bison libssl-dev libelf-dev \
                    bc dwarves cpio git can-utils libncurses-dev
```

*(Optional) Shell Optimization:* You can install `zsh`, `zsh-autosuggestions`, and `zsh-syntax-highlighting` for interactive terminal auto-completion:
```bash
sudo apt install -y zsh zsh-autosuggestions zsh-syntax-highlighting
```

---

### Step 3: Clone Microsoft WSL 2 Kernel Source
Clone the official Microsoft WSL 2 Linux kernel repository:
```bash
cd ~
git clone --depth 1 https://github.com/microsoft/WSL2-Linux-Kernel.git
cd WSL2-Linux-Kernel
```

---

### Step 4: Configure the Kernel for SocketCAN
1. Extract the current active WSL 2 kernel configuration:
   ```bash
   zcat /proc/config.gz > .config
   ```

2. Resolve any new configuration options to their safe defaults:
   ```bash
   make olddefconfig
   ```

3. Enable the CAN subsystem, Raw SocketCAN protocol, and Virtual CAN driver:
   ```bash
   ./scripts/config --enable CONFIG_CAN
   ./scripts/config --enable CONFIG_CAN_RAW
   ./scripts/config --enable CONFIG_CAN_VCAN
   ```

4. Verify that the options are set properly in `.config`:
   ```bash
   grep -E "CONFIG_CAN|CONFIG_CAN_RAW|CONFIG_CAN_VCAN" .config
   ```
   *Expected output:*
   ```text
   CONFIG_CAN=y
   CONFIG_CAN_RAW=y
   CONFIG_CAN_VCAN=m   # (or =y)
   ```

---

### Step 5: Compile the Custom Kernel & Modules
Compile the custom kernel using all available CPU threads:
```bash
make -j$(nproc)
```
*Depending on CPU performance, compilation typically takes 5–15 minutes.*

Once the build finishes successfully, install the kernel modules to your WSL root filesystem:
```bash
sudo make modules_install
```

---

### Step 6: Export the Kernel to Windows Host
Copy the compiled kernel binary (`vmlinux`) from WSL to your Windows user directory (replace `<username>` with your Windows user name):

```bash
# Example: Copying to your Windows home folder
cp vmlinux /mnt/c/Users/<username>/vmlinux-wsl2-can
```

---

### Step 7: Configure Windows `.wslconfig`
In Windows, create or edit the file `C:\Users\<username>\.wslconfig` using Notepad or VS Code:

```ini
[wsl2]
kernel=C:\\Users\\<username>\\vmlinux-wsl2-can
```

> [!IMPORTANT]
> Double backslashes (`\\`) must be used in the Windows path inside `.wslconfig`.

---

### Step 8: Restart WSL into the Custom Kernel
In Windows PowerShell, shut down WSL completely:
```powershell
wsl --shutdown
```

Re-open your Kali Linux (or Ubuntu) WSL terminal and verify the active kernel:
```bash
uname -a
```
You should see your newly compiled kernel timestamp with the custom tag (e.g., `Linux ...-microsoft-standard-WSL2+ ...`).

---

## 3. Verifying the CAN-Sentinel Environment

### 1. Activating Virtual CAN (`vcan0`)
Inside WSL 2:
```bash
# Load module and configure interface
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# Verify interface state
ip link show vcan0
```

*Expected output:*
```text
3: vcan0: <NOARP,UP,LOWER_UP> mtu 2060 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can
```
The interface is now **UP** and ready to receive and transmit automotive CAN frames.

---

### 2. Running Automated Unit Tests
Navigate to the project's `ecu_sim` folder (accessible from Windows via `/mnt/d/...` or your local WSL path):

```bash
cd /path/to/CAN-Sentinel/ecu_sim
make clean && make
make test
```

*Result:*
```text
====================================================
   CAN-Sentinel Automated Payload & Protocol Tests
====================================================

[PASS] Test 1: Frame Format (All 6 IDs, DLC 8, reserved bytes 0x00)
[PASS] Test 2: Counter Progression & Wrap-around (255 -> 0)
[PASS] Test 3: Steering Angle Encoding (-45.0 to +45.0 deg signed)
[PASS] Test 4: Engine Temperature Encoding (+40 offset, 80-105 C)
[PASS] Test 5: Brake Pressure & Switch Dynamic Coupling (0-100)
[PASS] Test 6: Engine RPM & Vehicle Speed Coupling (RPM = 800 + speed*25)
[PASS] Test 7: Deterministic Seed Reproducibility (Identical payloads)

====================================================
Results: 7 / 7 tests passed (0 failed).
====================================================
```

---

### 3. Running the Multi-Threaded ECU Simulator
Start the simulator with real-time multi-threading and the in-place digital instrument cluster:

```bash
./ecu_simulator --threads
```

In a second WSL terminal window, monitor live CAN bus traffic:
```bash
candump vcan0
```
You will observe all six ECUs (`0x0A0` Brake, `0x0B0` Steering, `0x100` Engine RPM, `0x200` Speed, `0x300` Temp, and `0x600` Infotainment) transmitting at the nominal aggregate rate of ~320 frames per second.

---

### 4. Running the Real-Time EV Sport Digital Dashboard
The Python WebSocket bridge and browser dashboard connect directly between WSL 2 and Windows without port forwarding complications:

```bash
cd /path/to/CAN-Sentinel/ecu_sim
make dashboard
```

*Output:*
```text
[SUCCESS] Bound to Linux SocketCAN interface 'vcan0'. Awaiting ECU frames...
[SERVER] CAN-Sentinel EV Dashboard Server running on ('0.0.0.0', 8080)
[SERVER] Dashboard URL: http://localhost:8080
[SERVER] WebSocket URL: ws://localhost:8080/ws
[WS] Client connected. Total active dashboard displays: 1
```

Open your favorite Windows browser (Chrome, Edge, Firefox) and navigate to:  
👉 **`http://localhost:8080`**

You will see the 60 FPS Porsche Taycan / Audi e-tron style digital instrument dashboard animating in real time with swept radial dials, articulated front wheel steering, active brake lighting, and bus load monitoring.

---

## 4. Daily Startup Cheatsheet

Once configured, bringing up the virtual CAN bus and simulator on WSL 2 requires only three simple commands:

```bash
# 1. Bring up vcan0 interface (run once per WSL session)
sudo modprobe vcan && sudo ip link add dev vcan0 type vcan 2>/dev/null; sudo ip link set up vcan0

# 2. Run ECU Simulator (Terminal 1)
cd /path/to/CAN-Sentinel/ecu_sim
./ecu_simulator --threads

# 3. Optional: Run EV Sport Web Dashboard (Terminal 2)
make dashboard
# View in Windows browser at http://localhost:8080
```

---

## 5. Summary & Technical Benefits

| Metric | VirtualBox VM | WSL 2 (Custom Kernel) |
|---|:---:|:---:|
| **Startup Time** | ~30–45 seconds | < 2 seconds |
| **RAM Usage** | 4–6 GB dedicated | Dynamic (~300 MB idle) |
| **File Access** | Shared folders / manual copy | Direct Windows drive mounts (`/mnt/c/`, `/mnt/d/`) |
| **SocketCAN Support** | Native | Native (with custom kernel) |
| **GUI Dashboard Integration** | Host port-forwarding | Zero-config localhost (`http://localhost:8080`) |
| **Automated Testing (`make test`)** | 100% Passed (7/7) | 100% Passed (7/7) |
