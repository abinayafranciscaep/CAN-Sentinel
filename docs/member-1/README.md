## Step 1: Configure Kali Linux on VirtualBox

The CAN-Sentinel Member 1 module is developed using **Kali Linux Rolling** running inside **Oracle VirtualBox**. The virtual machine provides an isolated Linux environment for implementing the **SocketCAN-based virtual CAN network**, developing the **C-based ECU simulators**, generating normal CAN traffic, and performing CAN traffic monitoring.

The virtual machine is configured with sufficient CPU, memory, and storage resources to support CAN network simulation, C compilation, traffic generation, packet monitoring, and integration with the other CAN-Sentinel modules.

### System Configuration

The Kali Linux virtual machine is configured approximately as follows:

* **Operating System:** Kali GNU/Linux Rolling
* **Kali Version:** 2026.3
* **Kernel:** 7.1.5+kali-amd64
* **Architecture:** x86_64
* **Platform:** Oracle VirtualBox
* **CPU:** 2+ cores
* **RAM:** 4 GB or more
* **Storage:** 40 GB or more
* **Network:** NAT
* **Terminal:** Kali Linux Terminal
* **Compiler:** GCC
* **CAN Framework:** Linux SocketCAN

![Kali Linux Running in VirtualBox](screenshots/step-01-kali-running.png)

**Screenshot 1:** Kali Linux virtual machine running in Oracle VirtualBox with the configured development environment.

### Step 1.1: Open the Kali Terminal

After starting the Kali Linux virtual machine, open the Kali Linux terminal.

Navigate to:

**Applications → System Tools → Terminal**

The terminal will be used throughout the Member 1 implementation to configure the virtual CAN interface, compile the C-based ECU simulator programs, generate CAN traffic, and perform system-level verification.

### Step 1.2: Verify the Linux Kernel and System Architecture

First, verify the currently running Linux kernel and system architecture:

```bash
uname -a
```

This command displays information about the Linux kernel, hostname, kernel build, and system architecture.

Example output:

```text
Linux kali 7.1.5+kali-amd64 #1 SMP PREEMPT_DYNAMIC Kali 7.1.5-1kali1 (2026-07-29) x86_64 GNU/Linux
```

The output confirms that the system is running the expected Kali Linux kernel on an **x86_64** architecture.

### Step 1.3: Verify the Kali Linux Operating System

Next, verify the installed Kali Linux distribution and version:

```bash
cat /etc/os-release
```

This command displays the operating system identification and release information.

Example output:

```text
PRETTY_NAME="Kali GNU/Linux Rolling"
NAME="Kali GNU/Linux"
VERSION_ID="2026.3"
VERSION="2026.3"
VERSION_CODENAME=kali-rolling
ID=kali
ID_LIKE=debian
```

This confirms that the development environment is based on **Kali GNU/Linux Rolling**.

### Step 1.4: Verify the GCC Compiler

Finally, verify that the GCC compiler is installed:

```bash
gcc --version
```

GCC is required to compile the C-based ECU simulator programs developed for the CAN-Sentinel Member 1 module.

Example output:

```text
gcc (Debian 16.2.0-3) 16.2.0
```

The successful GCC version output confirms that the C compilation environment is available.

![Kali Linux System and GCC Verification](screenshots/step-01-kali-configuration.png)

**Screenshot 2:** Terminal showing the Linux kernel, Kali Linux operating system, and GCC compiler verification.

### Step 1 Completion

The Kali Linux development environment has been successfully configured and verified. The system is ready for the next stage of the CAN-Sentinel Member 1 implementation, including **SocketCAN configuration, virtual CAN interface creation, and C-based ECU simulator development**.

## Step 2: Install Required Packages

After configuring the Kali Linux virtual machine, install the packages required for the **SocketCAN-based virtual CAN network** and **C-based ECU simulator development**. These packages provide the CAN utilities and development tools required to create, compile, test, and monitor the CAN traffic generated during the CAN-Sentinel Member 1 implementation.

The required packages are installed using the Kali Linux package manager. The installation includes **can-utils** for working with CAN interfaces, **GCC** for compiling C-based ECU simulator programs, and **Make** for supporting automated compilation.

### Step 2.1: Update the Package Repository

First, update the Kali Linux package repository information:

```bash
sudo apt update
```

This command refreshes the local package index and ensures that the latest available package information is used when installing the required tools.

### Step 2.2: Install the Required Packages

Install the required CAN utilities, GCC compiler, and Make build tool:

```bash
sudo apt install -y can-utils gcc make
```

The installed packages provide the following functionality:

* **can-utils** — Provides utilities such as `candump`, `cansend`, and `cangen` for monitoring, transmitting, and generating CAN traffic.
* **GCC** — Compiles the C-based ECU simulator programs developed for the CAN-Sentinel Member 1 module.
* **Make** — Supports automated compilation and management of the ECU simulator build process.

### Step 2.3: Verify the GCC Compiler

After installation, verify that GCC is available:

```bash
gcc --version
```

The installed GCC version was successfully verified:

```text
gcc (Debian 16.2.0-3) 16.2.0
```

The successful version output confirms that the C compiler required for developing the ECU simulator programs is installed and available.

![GCC Version Verification](screenshots/step-02-gcc-version.png)

**Screenshot 3:** Terminal showing the installed GCC version and confirming the C compiler is available.

### Step 2.4: Verify the CAN Utilities

Next, verify that the `candump` utility provided by the **can-utils** package is available:

```bash
candump --help
```

On this system, `candump` reports an invalid option for `--help` and subsequently displays its usage information and available options. This confirms that the `candump` utility is installed correctly and can be executed from the terminal.

The `candump` utility will later be used to monitor CAN frames transmitted through the `vcan0` virtual CAN interface.

![candump Usage Output](screenshots/step-02-candump-help.png)

**Screenshot 4:** Terminal showing the `candump` usage information and available options, confirming that the `can-utils` package is installed.

### Step 2 Completion

The required CAN and development tools have been successfully installed and verified. The Kali Linux environment now contains **can-utils**, **GCC**, and **Make**, providing the necessary tools for CAN communication, C-based ECU simulator development, compilation, and CAN traffic monitoring.

The environment is now ready for the next stage of the CAN-Sentinel Member 1 implementation: **creating and configuring the `vcan0` virtual CAN interface**.

## Step 3: Create and Configure the Virtual CAN Interface

After installing the required CAN utilities and development tools, the next step is to create the **virtual CAN interface** required for the CAN-Sentinel Member 1 implementation.

Linux **SocketCAN** provides the framework for CAN communication, while the **Virtual CAN (`vcan`)** driver allows CAN communication to be simulated without requiring physical CAN hardware. The `vcan0` interface will serve as the virtual CAN bus on which the C-based ECU simulators will later generate and exchange CAN frames.

### Step 3.1: Load the Virtual CAN Kernel Module

First, load the **Virtual CAN (`vcan`) kernel module**:

```bash
sudo modprobe vcan
```

The `modprobe` command loads the `vcan` kernel module into the running Linux kernel. This enables the system to create virtual CAN network interfaces.

### Step 3.2: Create the `vcan0` Interface

Create a virtual CAN interface named `vcan0`:

```bash
sudo ip link add dev vcan0 type vcan
```

This command creates a new virtual CAN network interface using the Linux `vcan` driver.

The interface is named **`vcan0`** and will be used as the virtual CAN bus for the CAN-Sentinel ECU simulation environment.

### Step 3.3: Bring the `vcan0` Interface Up

Enable the newly created virtual CAN interface:

```bash
sudo ip link set up vcan0
```

This command changes the state of the `vcan0` interface to **UP**, allowing it to participate in CAN communication.

### Step 3.4: Verify the Virtual CAN Interface

Finally, verify that the `vcan0` interface has been created and configured successfully:

```bash
ip link show vcan0
```

The verification command produced the following output:

```text
3: vcan0: <NOARP,UP,LOWER_UP> mtu 2060 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can
```

The output confirms that:

* The **`vcan` kernel module** was loaded successfully.
* The **`vcan0` virtual CAN interface** was created successfully.
* The interface is **UP** and ready for CAN communication.
* Linux recognizes `vcan0` as a **CAN interface**.
* The virtual CAN bus is ready for subsequent ECU simulation and CAN traffic generation.

![vcan0 Virtual CAN Interface Verification](screenshots/step-03-vcan0-verification.png)

**Screenshot 5:** Terminal showing the `vcan0` interface configuration and verification using `ip link show vcan0`.

### Step 3.5: `vcan0` Persistence and Recreation

The `vcan0` virtual CAN interface is created at runtime and is **not persistent by default**. Therefore, the interface will normally disappear when the Kali Linux virtual machine is rebooted. It can also be removed if the interface is manually deleted.

The following command creates the `vcan0` interface:

```bash
sudo ip link add dev vcan0 type vcan
```

This creates the virtual CAN interface only for the current running Linux session. Linux does not automatically recreate the interface after a system reboot.

### Recreate `vcan0` After Reboot

For the CAN-Sentinel development environment, this behavior is not a problem. If the `vcan0` interface is no longer available after restarting the Kali Linux virtual machine, it can be recreated manually using:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

After executing these commands, the `vcan0` interface will be available again for CAN-Sentinel development and testing.

### Optional: Automatic Recreation After Reboot

The `vcan0` interface can also be configured to be **automatically recreated during system startup**. This avoids manually creating the interface after every Kali Linux reboot.

For CAN-Sentinel, this can be implemented using a **systemd service**. The service can load the `vcan` kernel module, create the `vcan0` interface, and bring it up automatically during system boot.

The service can execute the following commands:

```bash
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

Once the corresponding systemd service has been created, it can be enabled to start automatically during boot:

```bash
sudo systemctl enable vcan0.service
```

After the Kali Linux virtual machine is restarted, the systemd service can automatically recreate and activate the `vcan0` interface.

**Note:** Automatic recreation is optional for the CAN-Sentinel development environment. The interface can also be recreated manually whenever required.

### Step 3 Completion

The **`vcan` kernel module** has been loaded successfully, and the **`vcan0` virtual CAN interface** has been created and brought up.

The SocketCAN virtual CAN environment is now ready for the next stage of the CAN-Sentinel Member 1 implementation: **developing the C-based ECU simulator programs and generating CAN traffic through `vcan0`**.

## Step 4: Verify the Virtual CAN Interface Details

After creating and enabling the `vcan0` virtual CAN interface, its detailed configuration was verified to ensure that the interface is correctly recognized and configured by the Linux SocketCAN framework.

Two verification commands were used. The first command displays detailed configuration information for `vcan0`, while the second specifically identifies interfaces using the Virtual CAN (`vcan`) driver.

### Step 4.1: Display Detailed `vcan0` Configuration

First, display the detailed configuration of the `vcan0` interface:

```bash
ip -details link show vcan0
```

This command provides detailed information about the network interface, including its interface state, CAN link type, queue configuration, and Virtual CAN driver parameters.

The command produced the following output:

```text
3: vcan0: <NOARP,UP,LOWER_UP> mtu 2060 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can promiscuity 0 allmulti 0 minmtu 0 maxmtu 0
    vcan addrgenmode eui64 numtxqueues 1 numrxqueues 1 gso_max_size 65536 gso_max_segs 65535 tso_max_size 65535 tso_max_segs 65535 gro_max_size 65536 gso_ipv4_max_size 65536 gro_ipv4_max_size 65536
```

The output shows that the interface is using the **CAN link type** and the **`vcan` driver**. The `UP` state confirms that the interface is enabled and available for CAN communication.

![Detailed vcan0 Interface Configuration](screenshots/step-04-vcan0-details.png)

**Screenshot 6:** Detailed `vcan0` interface configuration displayed using `ip -details link show vcan0`.
### Step 4.2: Verify the Virtual CAN Interface Type

Next, verify all interfaces recognized specifically as Virtual CAN interfaces:

```bash
ip link show type vcan
```

The command produced the following output:

```text
3: vcan0: <NOARP,UP,LOWER_UP> mtu 2060 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/can
```

This confirms that `vcan0` is recognized by Linux as a **Virtual CAN (`vcan`) interface**.

![Virtual CAN Interface Verification](screenshots/step-04-vcan0-type.png)

**Screenshot 7:** Virtual CAN interface verification using `ip link show type vcan`.

### Step 4 Completion

The `vcan0` interface has been successfully verified using both detailed interface information and Virtual CAN type filtering.

The verification confirms that:

* **`vcan0` exists** and is active.
* The interface is in the **UP** state.
* Linux recognizes `vcan0` as a **Virtual CAN (`vcan`) interface**.
* The interface is ready for **CAN frame transmission and reception**.
* The SocketCAN virtual CAN environment is correctly configured for the next stage of CAN-Sentinel development.

## Step 5: Test CAN Communication

After creating and verifying the `vcan0` virtual CAN interface, the next step is to test whether the interface can successfully **transmit and receive CAN frames**.

The CAN communication test uses two Kali Linux terminals. One terminal monitors CAN traffic using `candump`, while the second terminal transmits a test CAN frame using `cansend`.

Successful reception of the transmitted frame confirms that the `vcan0` virtual CAN interface is operational and that CAN communication is functioning correctly.

### Step 5.1: Start CAN Traffic Monitoring

Open a Kali Linux terminal and start monitoring CAN traffic on the `vcan0` interface:

```bash
candump vcan0
```

Leave this command running in the first terminal.

The `candump` utility continuously listens for CAN frames received through the specified interface and displays them in the terminal.

### Step 5.2: Transmit a Test CAN Frame

Open a second Kali Linux terminal and transmit a test CAN frame using:

```bash
cansend vcan0 123#1122334455667788
```

The `cansend` utility transmits the specified CAN frame through the `vcan0` interface.

The test frame uses:

* **CAN ID:** `0x123`
* **Data Length:** 8 bytes
* **Data:** `11 22 33 44 55 66 77 88`

The command completed successfully without displaying an error.

### Step 5.3: Verify the Received CAN Frame

The transmitted frame was successfully received in the first terminal running `candump vcan0`.

The received output was:

```text
vcan0  123   [8]  11 22 33 44 55 66 77 88
```

The output confirms that the CAN frame transmitted from the second terminal was received correctly by the `vcan0` interface.

![CAN Frame Reception](screenshots/step-05-candump-reception.png)

**Screenshot 8:** Terminal 1 showing the received CAN frame using `candump vcan0`.

![CAN Frame Transmission](screenshots/step-05-cansend-transmission.png)

**Screenshot 9:** Terminal 2 showing the `cansend` command used to transmit the test CAN frame.

### Step 5 Completion

The `vcan0` virtual CAN interface successfully transmitted and received a test CAN frame.

The communication test confirms that:

* The **`vcan0` interface is operational**.
* A CAN frame with **CAN ID `0x123`** was transmitted successfully.
* The frame contained **8 data bytes**.
* The transmitted data `11 22 33 44 55 66 77 88` was received correctly.
* CAN communication through the **SocketCAN virtual CAN interface** was successfully verified.

The `vcan0` interface is now ready for the next stage of the CAN-Sentinel Member 1 implementation, where the **C-based ECU simulator programs** will be developed and used to generate CAN traffic.
