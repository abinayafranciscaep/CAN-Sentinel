# ============================================================================
# CAN-Sentinel Virtual ECU Simulator & Test Suite Build System
# Member 1: CAN Systems & ECU Simulation
# ============================================================================

CC      := gcc
CFLAGS  := -Wall -Wextra -Wpedantic -std=c11 -O2 -pthread
LDLIBS  := -lpthread -lrt
TARGETS := ecu_simulator test_payloads brake_receiver

# Configurable Runtime Variables (can be overridden from CLI, e.g. make run IFACE=vcan1 SEED=42)
IFACE    ?= vcan0
SEED     ?=
DURATION ?=
LOG      ?=
TIMEOUT  ?= 100
ARGS     ?=

.PHONY: all clean test setup-vcan run run-mt run-receiver dashboard help

# Default target: compile simulator, automated test runner, and brake receiver
all: $(TARGETS)

ecu_simulator: ecu_simulator.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

test_payloads: test_payloads.c
	$(CC) $(CFLAGS) -o $@ $<

brake_receiver: brake_receiver.c
	$(CC) $(CFLAGS) -o $@ $<

# Run the 7/7 automated unit test suite
test: test_payloads
	@echo "===================================================="
	@echo "Running CAN-Sentinel automated payload unit tests..."
	@echo "===================================================="
	./test_payloads

# Run the single-threaded baseline ECU simulator
run: ecu_simulator
	@cmd="./ecu_simulator -i $(IFACE)"; \
	if [ -n "$(DURATION)" ]; then \
		cmd="$$cmd -d $(DURATION)"; \
	fi; \
	if [ -n "$(LOG)" ]; then \
		cmd="$$cmd -l $(LOG)"; \
	fi; \
	if [ -n "$(ARGS)" ]; then \
		cmd="$$cmd $(ARGS)"; \
	fi; \
	if [ -n "$(SEED)" ]; then \
		cmd="$$cmd $(SEED)"; \
	fi; \
	echo "Launching Single-Threaded Simulator on $(IFACE)..."; \
	exec $$cmd

# Run the multi-threaded distributed ECU simulator (6 pthreads + atomics)
run-mt: ecu_simulator
	@cmd="./ecu_simulator -i $(IFACE) --threads"; \
	if [ -n "$(DURATION)" ]; then \
		cmd="$$cmd -d $(DURATION)"; \
	fi; \
	if [ -n "$(LOG)" ]; then \
		cmd="$$cmd -l $(LOG)"; \
	fi; \
	if [ -n "$(ARGS)" ]; then \
		cmd="$$cmd $(ARGS)"; \
	fi; \
	if [ -n "$(SEED)" ]; then \
		cmd="$$cmd $(SEED)"; \
	fi; \
	echo "Launching Multi-Threaded Distributed Simulator on $(IFACE)..."; \
	exec $$cmd

# Run the Fail-Safe Brake Actuator Receiver (defaults to vcan0)
run-receiver: brake_receiver
	@cmd="./brake_receiver -i $(IFACE) -t $(TIMEOUT)"; \
	if [ -n "$(ARGS)" ]; then \
		cmd="$$cmd $(ARGS)"; \
	fi; \
	echo "Launching Fail-Safe Brake Receiver on $(IFACE) (Timeout: $(TIMEOUT) ms)..."; \
	exec $$cmd

# Setup and bring up the virtual CAN interfaces (vcan0 and vcan1 for gateway)
setup-vcan:
	@echo "Verifying virtual CAN interfaces (vcan0, vcan1)..."
	@sudo modprobe vcan
	@if ip link show vcan0 > /dev/null 2>&1; then \
		echo "vcan0 is already configured and active."; \
	else \
		echo "Configuring vcan0..."; \
		(sudo ip link add dev vcan0 type vcan 2>/dev/null || true) && \
		sudo ip link set up vcan0 && \
		echo "vcan0 successfully brought up."; \
	fi
	@if ip link show vcan1 > /dev/null 2>&1; then \
		echo "vcan1 is already configured and active."; \
	else \
		echo "Configuring vcan1..."; \
		(sudo ip link add dev vcan1 type vcan 2>/dev/null || true) && \
		sudo ip link set up vcan1 && \
		echo "vcan1 successfully brought up."; \
	fi

# Launch the real-time Web-Based EV Sport Dashboard bridge
dashboard:
	@if [ -f "dashboard/bridge.py" ]; then \
		echo "Starting CAN-Sentinel Web Dashboard Bridge on http://localhost:8080 (interface $(IFACE))..."; \
		python3 dashboard/bridge.py --interface $(IFACE) --port 8080; \
	elif [ -f "bridge.py" ]; then \
		echo "Starting CAN-Sentinel Web Dashboard Bridge on http://localhost:8080 (interface $(IFACE))..."; \
		python3 bridge.py --interface $(IFACE) --port 8080; \
	elif [ -f "../docs/member-1/dashboard/bridge.py" ]; then \
		echo "Starting CAN-Sentinel Web Dashboard Bridge on http://localhost:8080 (interface $(IFACE))..."; \
		python3 ../docs/member-1/dashboard/bridge.py --interface $(IFACE) --port 8080; \
	elif [ -f "docs/member-1/dashboard/bridge.py" ]; then \
		echo "Starting CAN-Sentinel Web Dashboard Bridge on http://localhost:8080 (interface $(IFACE))..."; \
		python3 docs/member-1/dashboard/bridge.py --interface $(IFACE) --port 8080; \
	else \
		echo "Error: bridge.py not found in dashboard/ or current directory."; \
		exit 1; \
	fi

# Clean compiled binaries
clean:
	rm -f $(TARGETS)
	@echo "Cleaned build artifacts: $(TARGETS)"

# Display help menu
help:
	@echo "CAN-Sentinel Build System Targets:"
	@echo "  make                 - Build ecu_simulator, test_payloads, and brake_receiver"
	@echo "  make test            - Build and run the automated unit test suite (7/7)"
	@echo "  make setup-vcan      - Configure and activate virtual CAN interfaces (vcan0 & vcan1)"
	@echo "  make run             - Run single-threaded simulator (IFACE=vcan0/vcan1, SEED=N, DURATION=S)"
	@echo "  make run-mt          - Run multi-threaded distributed simulator (--threads)"
	@echo "  make run-receiver    - Run fail-safe brake actuator receiver on IFACE (default: vcan0)"
	@echo "  make dashboard       - Launch the real-time Web EV Sport Dashboard (http://localhost:8080)"
	@echo "  make clean           - Remove compiled executable binaries"
	@echo "  make help            - Display this help message"
