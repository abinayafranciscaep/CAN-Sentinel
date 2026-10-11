#!/bin/bash
# Recreate the virtual CAN interface after a WSL restart.
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan 2>/dev/null || true   # ignore "already exists"
sudo ip link set up vcan0
ip link show vcan0