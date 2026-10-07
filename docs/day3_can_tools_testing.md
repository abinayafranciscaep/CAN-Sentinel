# Day 3 - CAN Tools and Virtual CAN Testing

## Objective

The objective of Day 3 was to install the SocketCAN userspace tools and verify basic CAN frame communication using the virtual CAN interface `vcan0`.

The testing was performed entirely on the local Linux virtual CAN environment.

## Tools Used

- Linux
- SocketCAN
- `can-utils`
- `candump`
- `cansend`
- Virtual CAN interface: `vcan0`

## 1. Install can-utils

The CAN userspace tools were installed using:

```bash
sudo apt update
sudo apt install can-utils -y
```

## 2. Verify CAN Tools

The installed tools were verified using:

```bash
which cansend
which candump
```

The tools were found at:

```text
/usr/bin/cansend
/usr/bin/candump
```

## 3. Create Virtual CAN Interface

The required kernel modules were loaded:

```bash
sudo modprobe can
sudo modprobe vcan
```

The virtual CAN interface was created using:

```bash
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

The interface was verified with:

```bash
ip link show vcan0
```

The interface was successfully detected as a CAN interface and was in the UP state.

## 4. CAN Frame Testing

`candump` was used to monitor CAN traffic on `vcan0`:

```bash
candump vcan0
```

A test CAN frame was transmitted using:

```bash
cansend vcan0 123#11223344
```

The received frame was observed as:

```text
vcan0  123   [4]  11 22 33 44
```

## 5. Frame Breakdown

| Field | Value | Meaning |
|---|---|---|
| Interface | `vcan0` | Virtual CAN interface |
| CAN ID | `123` | CAN identifier used for this test |
| DLC | `4` | Four data bytes |
| Data | `11 22 33 44` | CAN payload |

## Result

The test successfully verified that:

1. `can-utils` was installed successfully.
2. `cansend` and `candump` were available.
3. The `vcan0` interface was successfully created and brought UP.
4. A CAN frame could be transmitted on `vcan0`.
5. The transmitted frame could be captured using `candump`.

This confirms that the Linux virtual CAN environment is ready for further CAN-Sentinel development and testing.

## Safety Scope

All CAN traffic generated during this test was sent only through the local virtual interface `vcan0`. No real vehicle or physical CAN bus was involved.
