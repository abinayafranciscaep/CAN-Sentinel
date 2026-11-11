#!/usr/bin/env python3
"""
CAN-Sentinel: Real-time SocketCAN to WebSocket Telemetry Bridge & Static Web Server
==================================================================================
Reads CAN 2.0A frames from virtual CAN (vcan0) or physical CAN bus, decodes the 6
automotive ECUs, computes real-time bus load and health metrics, and broadcasts JSON
telemetry to connected EV Sport Dashboard clients over WebSocket (ws://0.0.0.0:8080).
Also serves static web assets (http://0.0.0.0:8080) for Kali Firefox & Windows Chrome.

Zero external dependencies required (uses Python standard library: asyncio, socket, struct).
Supports automatic high-fidelity physics mock mode when run without vcan0 or on Windows.
"""

import argparse
import asyncio
import base64
import hashlib
import json
import math
import mimetypes
import os
import random
import socket
import struct
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# CAN Frame struct format: 4-byte can_id, 1-byte dlc, 3 bytes padding, 8 bytes data
CAN_FRAME_FMT = "=IB3x8s"
CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FMT)

# Nominal CAN bit calculation constants
# Standard CAN 2.0A frame overhead: ~47 bits (SOF, ID, control, CRC, ACK, EOF) + 64 bits data = 111 bits
# With nominal bit stuffing (~15%) and 3-bit interframe space, average frame size is ~128 bits.
BITS_PER_CAN_FRAME = 128

# ECU Definitions & Specifications
ECU_SPECS = {
    0x0A0: {"name": "Brake_ECU", "desc": "Brake Controller", "period_ms": 20, "nominal_hz": 50},
    0x0B0: {"name": "Steering_ECU", "desc": "Steering Gateway", "period_ms": 10, "nominal_hz": 100},
    0x100: {"name": "Engine_ECU", "desc": "Powertrain Engine", "period_ms": 10, "nominal_hz": 100},
    0x200: {"name": "Speed_ECU", "desc": "Speed Sensor", "period_ms": 20, "nominal_hz": 50},
    0x300: {"name": "Temp_ECU", "desc": "Thermal Management", "period_ms": 100, "nominal_hz": 10},
    0x600: {"name": "Infotainment_ECU", "desc": "Infotainment Gateway", "period_ms": 100, "nominal_hz": 10},
}


class VehicleTelemetryState:
    """Thread-safe unified vehicle state and bus performance metrics."""

    def __init__(self, baudrate: int = 500000):
        self.lock = threading.Lock()
        self.baudrate = baudrate

        # Vehicle physical signals
        self.speed_kmh: float = 0.0
        self.rpm: int = 800
        self.brake_pressure: int = 0
        self.brake_switch: int = 0
        self.steering_angle: float = 0.0
        self.coolant_temp_c: int = 90
        self.infotainment_status: int = 1
        self.gear: str = "P"
        self.gear_num: int = 1
        self.drive_mode: str = "SPORT+"

        # Per-ECU telemetry tracking
        self.ecu_stats: Dict[int, dict] = {}
        now = time.time()
        for can_id, spec in ECU_SPECS.items():
            self.ecu_stats[can_id] = {
                "id_hex": f"0x{can_id:03X}",
                "name": spec["name"],
                "desc": spec["desc"],
                "period_ms": spec["period_ms"],
                "nominal_hz": spec["nominal_hz"],
                "counter": 0,
                "counter_errors": 0,
                "last_seen": now,
                "last_seen_ms": 0.0,
                "frame_count": 0,
                "instant_hz": 0.0,
                "health": "WAITING",
                "last_value": "--",
            }

        # Bus-wide performance statistics
        self.total_frames: int = 0
        self.bus_fps: float = 0.0
        self.bus_load_pct: float = 0.0
        self.start_time: float = now
        self.last_stat_time: float = now
        self.frames_in_interval: int = 0
        self.mode_source: str = "INITIALIZING"

    def update_signal(self, can_id: int, data: bytes):
        """Decode incoming CAN payload according to dbc protocol."""
        now = time.time()
        if len(data) < 8:
            return

        with self.lock:
            self.total_frames += 1
            self.frames_in_interval += 1

            if can_id in self.ecu_stats:
                st = self.ecu_stats[can_id]
                prev_counter = st["counter"]
                new_counter = data[7]

                # Check rolling counter continuity
                if st["frame_count"] > 0:
                    expected = (prev_counter + 1) & 0xFF
                    if new_counter != expected:
                        st["counter_errors"] += 1

                st["counter"] = new_counter
                st["last_seen"] = now
                st["frame_count"] += 1
                st["health"] = "OK"

            # 0x0A0: Brake Controller
            if can_id == 0x0A0:
                self.brake_pressure = int(data[0])
                self.brake_switch = int(data[1])
                val_str = f"{self.brake_pressure}% ({'ENGAGED' if self.brake_switch else 'RELEASED'})"
                self.ecu_stats[0x0A0]["last_value"] = val_str

            # 0x0B0: Steering Gateway (-45.0° to +45.0°, 0.1° scale, signed big-endian)
            elif can_id == 0x0B0:
                raw_angle = struct.unpack(">h", data[0:2])[0]
                self.steering_angle = round(raw_angle * 0.1, 1)
                self.ecu_stats[0x0B0]["last_value"] = f"{self.steering_angle:+.1f}°"

            # 0x100: Powertrain Engine (800-4000 RPM, big-endian)
            elif can_id == 0x100:
                self.rpm = int(struct.unpack(">H", data[0:2])[0])
                self.ecu_stats[0x100]["last_value"] = f"{self.rpm} RPM"

            # 0x200: Speed Sensor (0-130 km/h)
            elif can_id == 0x200:
                self.speed_kmh = float(data[0])
                self.ecu_stats[0x200]["last_value"] = f"{int(self.speed_kmh)} km/h"

            # 0x300: Thermal Management (80-105 °C, DBC offset +40)
            elif can_id == 0x300:
                raw_temp = int(data[0])
                # If offset was encoded as temp + 40 (as in ecu_simulator.c and DBC), decode it
                if raw_temp >= 120:
                    self.coolant_temp_c = raw_temp - 40
                else:
                    self.coolant_temp_c = raw_temp
                self.ecu_stats[0x300]["last_value"] = f"{self.coolant_temp_c} °C"

            # 0x600: Infotainment Gateway (0=Off, 1=Active)
            elif can_id == 0x600:
                self.infotainment_status = int(data[0])
                self.ecu_stats[0x600]["last_value"] = "ACTIVE" if self.infotainment_status else "STANDBY"

            # Compute virtual transmission gear
            self._compute_gear()

    def _compute_gear(self):
        """Calculates holographic transmission selector state (P, R, N, D1-D5)."""
        speed = self.speed_kmh
        brake = self.brake_switch

        if speed < 0.5:
            if brake == 1:
                self.gear = "P"
                self.gear_num = 0
            else:
                self.gear = "N"
                self.gear_num = 0
        else:
            if speed < 25.0:
                self.gear = "D1"
                self.gear_num = 1
            elif speed < 50.0:
                self.gear = "D2"
                self.gear_num = 2
            elif speed < 75.0:
                self.gear = "D3"
                self.gear_num = 3
            elif speed < 105.0:
                self.gear = "D4"
                self.gear_num = 4
            else:
                self.gear = "D5"
                self.gear_num = 5

    def update_periodic_metrics(self):
        """Compute rolling bus rate, physical bus load, and ECU freshness every 250ms."""
        now = time.time()
        with self.lock:
            dt = now - self.last_stat_time
            if dt >= 0.25:
                self.bus_fps = self.frames_in_interval / dt
                self.frames_in_interval = 0
                self.last_stat_time = now

                # Physical Bus Load Calculation
                # Load % = (Frames/sec * Bits/frame / Bus_Baudrate) * 100%
                # At 320 frames/sec on 500 kbps: (320 * 128 / 500000) * 100% = 8.192%
                raw_load = (self.bus_fps * BITS_PER_CAN_FRAME / self.baudrate) * 100.0
                self.bus_load_pct = round(min(raw_load, 100.0), 2)

                # Check if simulator has stopped transmitting (no frames in > 0.5s)
                latest_seen = max((st["last_seen"] for st in self.ecu_stats.values()), default=0)
                is_bus_active = (now - latest_seen) < 0.5

                if not is_bus_active:
                    # Simulator has stopped! Drop all vehicle dynamics to zero
                    self.speed_kmh = 0.0
                    self.rpm = 0
                    self.brake_pressure = 0
                    self.brake_switch = 0
                    self.steering_angle = 0.0
                    self.gear = "P"
                    self.gear_num = 0
                    self.bus_fps = 0.0
                    self.bus_load_pct = 0.0

                # Update per-ECU freshness and status
                for can_id, st in self.ecu_stats.items():
                    elapsed_ms = (now - st["last_seen"]) * 1000.0
                    st["last_seen_ms"] = round(elapsed_ms, 1)

                    if not is_bus_active or elapsed_ms > 400.0:
                        st["health"] = "TIMEOUT"
                    elif elapsed_ms > (st["period_ms"] * 2.5):
                        st["health"] = "LAG"
                    else:
                        st["health"] = "OK"

    def get_snapshot(self) -> dict:
        """Returns a JSON-serializable snapshot of vehicle telemetry."""
        now = time.time()
        with self.lock:
            latest_seen = max((st["last_seen"] for st in self.ecu_stats.values()), default=0)
            is_bus_active = (now - latest_seen) < 0.5 and (self.bus_fps > 0 or self.total_frames > 0)

            # If bus inactive, enforce zero state
            out_speed = round(self.speed_kmh, 1) if is_bus_active else 0.0
            out_rpm = self.rpm if is_bus_active else 0
            out_gear = self.gear if is_bus_active else "P"
            out_fps = round(self.bus_fps, 1) if is_bus_active else 0.0
            out_load = self.bus_load_pct if is_bus_active else 0.0

            return {
                "type": "telemetry",
                "timestamp": round(now, 3),
                "is_active": is_bus_active,
                "speed": out_speed,
                "rpm": out_rpm,
                "gear": out_gear,
                "gear_num": self.gear_num if is_bus_active else 0,
                "drive_mode": self.drive_mode,
                "brake_pressure": self.brake_pressure if is_bus_active else 0,
                "brake_switch": self.brake_switch if is_bus_active else 0,
                "steering_angle": self.steering_angle if is_bus_active else 0.0,
                "coolant_temp": self.coolant_temp_c,
                "infotainment": self.infotainment_status if is_bus_active else 0,
                "bus_stats": {
                    "total_frames": self.total_frames,
                    "fps": out_fps,
                    "bus_load_pct": out_load,
                    "baudrate": self.baudrate,
                    "status": "HEALTHY" if (is_bus_active and self.bus_fps > 50) else "OFFLINE",
                    "mode": self.mode_source,
                },
                "ecus": {
                    f"0x{can_id:03X}": {
                        "name": st["name"],
                        "desc": st["desc"],
                        "nominal_hz": st["nominal_hz"],
                        "counter": st["counter"],
                        "counter_errors": st["counter_errors"],
                        "last_seen_ms": st["last_seen_ms"],
                        "health": st["health"] if is_bus_active else "TIMEOUT",
                        "value": st["last_value"] if is_bus_active else "--",
                    }
                    for can_id, st in self.ecu_stats.items()
                },
            }


# ==============================================================================
# CAN BUS INTERFACE WORKERS
# ==============================================================================


class SocketCANReceiver(threading.Thread):
    """Reads real CAN frames from Linux SocketCAN interface (vcan0)."""

    def __init__(self, interface: str, state: VehicleTelemetryState):
        super().__init__(daemon=True, name="SocketCANReceiver")
        self.interface = interface
        self.state = state
        self.running = True
        self.connected = False

    def run(self):
        # Check if AF_CAN exists on this OS
        if not hasattr(socket, "AF_CAN"):
            print(f"[WARN] socket.AF_CAN is not supported on this OS ({sys.platform}).")
            return

        try:
            can_socket = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
            can_socket.bind((self.interface,))
            self.connected = True
            self.state.mode_source = f"SOCKETCAN ({self.interface})"
            print(f"[SUCCESS] Bound to Linux SocketCAN interface '{self.interface}'. Awaiting ECU frames...")

            while self.running:
                cf = can_socket.recv(CAN_FRAME_SIZE)
                if len(cf) < CAN_FRAME_SIZE:
                    continue
                can_id, can_dlc, data = struct.unpack(CAN_FRAME_FMT, cf)
                can_id &= 0x7FF  # Mask to standard 11-bit CAN ID
                self.state.update_signal(can_id, data)

        except Exception as exc:
            print(f"[INFO] SocketCAN interface '{self.interface}' connection notice: {exc}")
            self.connected = False


class HighFidelityMockECUSimulator(threading.Thread):
    """
    Fallback high-fidelity physics simulator producing exact 320 frames/sec on 6 ECUs.
    Used seamlessly when running on Windows, or when vcan0 is not yet active.
    """

    def __init__(self, state: VehicleTelemetryState):
        super().__init__(daemon=True, name="MockECUSimulator")
        self.state = state
        self.running = True

    def run(self):
        print("[INFO] Starting High-Fidelity ECU Physics Engine (320 frames/sec baseline)...")
        self.state.mode_source = "HIGH-FIDELITY SIMULATOR (320 FPS)"

        counters = {0x0A0: 0, 0x0B0: 0, 0x100: 0, 0x200: 0, 0x300: 0, 0x600: 0}
        last_tx = {can_id: time.time() for can_id in counters}

        # Dynamic physics state variables
        speed = 55.0
        target_speed = 75.0
        steering_t = 0.0
        brake_active = 0
        brake_press = 0
        coolant = 90.0
        info_status = 1
        speed_cycle_t = 0.0

        clock_interval = 0.002  # 2 ms precision loop

        while self.running:
            now = time.time()
            speed_cycle_t += clock_interval
            steering_t += clock_interval

            # Dynamic realistic driving cycle (cruising, cornering, braking, accelerating)
            # Smooth speed wave between 35 and 115 km/h
            target_speed = 68.0 + 38.0 * math.sin(speed_cycle_t * 0.15) + 10.0 * math.cos(speed_cycle_t * 0.05)
            target_speed = max(0.0, min(128.0, target_speed))

            # Simulate braking when decelerating sharply
            if target_speed < speed - 0.5:
                brake_active = 1
                brake_press = min(100, brake_press + 4)
            else:
                brake_active = 0
                brake_press = max(0, brake_press - 3)

            # Smooth speed progression
            speed += (target_speed - speed) * 0.03
            speed = max(0.0, min(130.0, speed))

            # Steering angle wave (-35° to +35°) with realistic steering wheel motion
            steer_angle = 32.0 * math.sin(steering_t * 0.4) * math.cos(steering_t * 0.12)
            steer_angle = max(-45.0, min(45.0, steer_angle))

            # Engine RPM tied to vehicle speed + gear ratio dynamics
            calculated_rpm = int(800 + speed * 26.0 + 40.0 * math.sin(speed_cycle_t * 2.0))
            calculated_rpm = max(800, min(4000, calculated_rpm))

            # Coolant temp thermal equilibrium around 90-95°C
            coolant = 89.0 + (speed / 130.0) * 8.0 + 1.5 * math.sin(speed_cycle_t * 0.08)
            coolant = max(80.0, min(105.0, coolant))

            # 1. 0x0B0 Steering Gateway (10 ms / 100 Hz)
            if now - last_tx[0x0B0] >= 0.010:
                raw_angle = int(round(steer_angle * 10.0))
                data = bytearray(8)
                struct.pack_into(">h", data, 0, raw_angle)
                data[7] = counters[0x0B0] & 0xFF
                counters[0x0B0] = (counters[0x0B0] + 1) & 0xFF
                self.state.update_signal(0x0B0, bytes(data))
                last_tx[0x0B0] = now

            # 2. 0x100 Powertrain Engine (10 ms / 100 Hz)
            if now - last_tx[0x100] >= 0.010:
                data = bytearray(8)
                struct.pack_into(">H", data, 0, calculated_rpm)
                data[7] = counters[0x100] & 0xFF
                counters[0x100] = (counters[0x100] + 1) & 0xFF
                self.state.update_signal(0x100, bytes(data))
                last_tx[0x100] = now

            # 3. 0x0A0 Brake Controller (20 ms / 50 Hz)
            if now - last_tx[0x0A0] >= 0.020:
                data = bytearray(8)
                data[0] = brake_press & 0xFF
                data[1] = brake_active & 0xFF
                data[7] = counters[0x0A0] & 0xFF
                counters[0x0A0] = (counters[0x0A0] + 1) & 0xFF
                self.state.update_signal(0x0A0, bytes(data))
                last_tx[0x0A0] = now

            # 4. 0x200 Speed Sensor (20 ms / 50 Hz)
            if now - last_tx[0x200] >= 0.020:
                data = bytearray(8)
                data[0] = int(speed) & 0xFF
                data[7] = counters[0x200] & 0xFF
                counters[0x200] = (counters[0x200] + 1) & 0xFF
                self.state.update_signal(0x200, bytes(data))
                last_tx[0x200] = now

            # 5. 0x300 Thermal Management (100 ms / 10 Hz)
            if now - last_tx[0x300] >= 0.100:
                data = bytearray(8)
                # Offset +40 as specified by DBC & ecu_simulator.c
                data[0] = (int(coolant) + 40) & 0xFF
                data[7] = counters[0x300] & 0xFF
                counters[0x300] = (counters[0x300] + 1) & 0xFF
                self.state.update_signal(0x300, bytes(data))
                last_tx[0x300] = now

            # 6. 0x600 Infotainment Gateway (100 ms / 10 Hz)
            if now - last_tx[0x600] >= 0.100:
                data = bytearray(8)
                data[0] = info_status & 0xFF
                data[7] = counters[0x600] & 0xFF
                counters[0x600] = (counters[0x600] + 1) & 0xFF
                self.state.update_signal(0x600, bytes(data))
                last_tx[0x600] = now

            time.sleep(clock_interval)


# ==============================================================================
# ZERO-DEPENDENCY ASYNCIO HTTP & WEBSOCKET RFC 6455 SERVER
# ==============================================================================

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class AsyncUnifiedDashboardServer:
    """
    Combined HTTP Static File Server & RFC 6455 WebSocket Server.
    Requires no external pip packages; executes directly on Python 3.8+ asyncio.
    """

    def __init__(self, host: str, port: int, web_dir: Path, state: VehicleTelemetryState):
        self.host = host
        self.port = port
        self.web_dir = web_dir
        self.state = state
        self.clients: Set[asyncio.StreamWriter] = set()
        self.clients_lock = asyncio.Lock()

    def build_ws_frame(self, message: str) -> bytes:
        """Encode UTF-8 payload into unmasked server WebSocket frame (RFC 6455)."""
        payload = message.encode("utf-8")
        length = len(payload)
        frame = bytearray([0x81])  # FIN bit set, Opcode 1 (Text)

        if length <= 125:
            frame.append(length)
        elif length <= 65535:
            frame.append(126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(127)
            frame.extend(struct.pack("!Q", length))

        frame.extend(payload)
        return bytes(frame)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Dispatches connection to either WebSocket handshake or HTTP response."""
        try:
            # Read initial HTTP request header
            header_bytes = await reader.readuntil(b"\r\n\r\n")
            header_text = header_bytes.decode("latin1")
            lines = header_text.split("\r\n")
            if not lines:
                writer.close()
                await writer.wait_closed()
                return

            req_line = lines[0].split(" ")
            if len(req_line) < 2:
                writer.close()
                return

            method, path = req_line[0], req_line[1]

            # Parse headers into dictionary
            headers = {}
            for line in lines[1:]:
                if ": " in line:
                    k, v = line.split(": ", 1)
                    headers[k.lower()] = v.strip()

            # Check if this is a WebSocket Upgrade request
            if headers.get("upgrade", "").lower() == "websocket":
                await self._handle_websocket(headers, reader, writer)
            else:
                await self._handle_http(method, path, writer)

        except asyncio.IncompleteReadError:
            pass
        except Exception as exc:
            pass
        finally:
            async with self.clients_lock:
                self.clients.discard(writer)

    async def _handle_websocket(self, headers: dict, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """RFC 6455 WebSocket Handshake & Client Read Loop."""
        sec_key = headers.get("sec-websocket-key")
        if not sec_key:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            writer.close()
            return

        accept_val = base64.b64encode(hashlib.sha1((sec_key + WS_GUID).encode("utf-8")).digest()).decode("latin1")

        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_val}\r\n\r\n"
        )
        writer.write(response.encode("latin1"))
        await writer.drain()

        async with self.clients_lock:
            self.clients.add(writer)
            print(f"[WS] Client connected. Total active dashboard displays: {len(self.clients)}")

        # Send immediate initial telemetry snapshot
        snap = self.state.get_snapshot()
        writer.write(self.build_ws_frame(json.dumps(snap)))
        await writer.drain()

        # Keep reading incoming frames (client pings/pongs/closes)
        try:
            while True:
                head = await reader.read(2)
                if len(head) < 2:
                    break
                b1, b2 = head[0], head[1]
                opcode = b1 & 0x0F
                masked = (b2 & 0x80) != 0
                payload_len = b2 & 0x7F

                if payload_len == 126:
                    ext = await reader.read(2)
                    payload_len = struct.unpack("!H", ext)[0]
                elif payload_len == 127:
                    ext = await reader.read(8)
                    payload_len = struct.unpack("!Q", ext)[0]

                mask_key = b""
                if masked:
                    mask_key = await reader.read(4)

                payload = await reader.read(payload_len)

                # Close frame
                if opcode == 0x08:
                    break
                # Ping frame
                elif opcode == 0x09:
                    # Echo back as Pong
                    pong_frame = bytearray([0x8A, len(payload)]) + payload
                    writer.write(pong_frame)
                    await writer.drain()

        except Exception:
            pass
        finally:
            async with self.clients_lock:
                self.clients.discard(writer)
                print(f"[WS] Client disconnected. Remaining: {len(self.clients)}")
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_http(self, method: str, path: str, writer: asyncio.StreamWriter):
        """Serves static files (index.html, styles, scripts) and REST health API."""
        clean_path = path.split("?")[0].lstrip("/")
        if clean_path == "" or clean_path == "/":
            clean_path = "index.html"

        # REST API health check endpoint
        if clean_path == "api/status":
            data = json.dumps(self.state.get_snapshot()).encode("utf-8")
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" + data
            )
            writer.write(resp)
            await writer.drain()
            writer.close()
            return

        file_path = (self.web_dir / clean_path).resolve()

        # Prevent directory traversal
        if not str(file_path).startswith(str(self.web_dir.resolve())):
            writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            await writer.drain()
            writer.close()
            return

        if not file_path.is_file():
            # Fallback to index.html if file doesn't exist
            file_path = self.web_dir / "index.html"

        if file_path.is_file():
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "text/plain"
            content = file_path.read_bytes()
            resp = (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Type: {mime_type}\r\n"
                f"Content-Length: {len(content)}\r\n"
                f"Cache-Control: no-cache\r\n"
                f"Access-Control-Allow-Origin: *\r\n\r\n"
            ).encode("latin1") + content
            writer.write(resp)
            await writer.drain()
        else:
            not_found = b"HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nFile Not Found"
            writer.write(not_found)
            await writer.drain()

        writer.close()
        await writer.wait_closed()

    async def broadcast_loop(self):
        """Broadcasts vehicle telemetry state to all connected WebSocket clients at ~60 FPS."""
        # 60 FPS broadcast interval = ~16.6 ms
        broadcast_interval = 1.0 / 60.0
        while True:
            self.state.update_periodic_metrics()
            async with self.clients_lock:
                active_clients = list(self.clients)

            if active_clients:
                snapshot_json = json.dumps(self.state.get_snapshot())
                frame_data = self.build_ws_frame(snapshot_json)
                stale_clients = []

                for client in active_clients:
                    try:
                        client.write(frame_data)
                        await client.drain()
                    except Exception:
                        stale_clients.append(client)

                if stale_clients:
                    async with self.clients_lock:
                        for sc in stale_clients:
                            self.clients.discard(sc)

            await asyncio.sleep(broadcast_interval)

    async def run(self):
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        print(f"[SERVER] CAN-Sentinel EV Dashboard Server running on {addrs}")
        print(f"[SERVER] Dashboard URL: http://localhost:{self.port}")
        print(f"[SERVER] WebSocket URL: ws://localhost:{self.port}/ws")
        print(f"[SERVER] Static Root   : {self.web_dir}")

        async with server:
            await asyncio.gather(server.serve_forever(), self.broadcast_loop())


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================


def main():
    parser = argparse.ArgumentParser(description="CAN-Sentinel: SocketCAN to WebSocket Dashboard Bridge")
    parser.add_argument("--interface", "-i", default="vcan0", help="CAN interface name (default: vcan0)")
    parser.add_argument("--port", "-p", type=int, default=8080, help="HTTP/WebSocket port (default: 8080)")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host IP (default: 0.0.0.0)")
    parser.add_argument("--baudrate", "-b", type=int, default=500000, help="Bus baudrate for load calc (default: 500000)")
    parser.add_argument("--mock", "-m", action="store_true", help="Force high-fidelity mock simulator mode")
    parser.add_argument("--web-dir", "-w", default=None, help="Path to static web assets directory")
    args = parser.parse_args()

    # Determine web directory containing index.html
    current_dir = Path(__file__).resolve().parent
    if args.web_dir:
        web_path = Path(args.web_dir).resolve()
    else:
        # Check current dir, then 'dashboard' subdir
        if (current_dir / "index.html").exists():
            web_path = current_dir
        elif (current_dir / "dashboard" / "index.html").exists():
            web_path = current_dir / "dashboard"
        else:
            web_path = current_dir

    print("=" * 74)
    print("  CAN-SENTINEL: REAL-TIME EV SPORT DASHBOARD BRIDGE & WEB SERVER")
    print("=" * 74)

    state = VehicleTelemetryState(baudrate=args.baudrate)

    # Initialize CAN layer
    use_mock = args.mock
    socketcan_worker = None

    if not use_mock and hasattr(socket, "AF_CAN") and sys.platform.startswith("linux"):
        socketcan_worker = SocketCANReceiver(interface=args.interface, state=state)
        socketcan_worker.start()
        # Give worker a brief moment to check if socket bind succeeds
        time.sleep(0.15)
        if not socketcan_worker.connected:
            print(f"[NOTICE] Interface '{args.interface}' not responding on SocketCAN. Switching to High-Fidelity Physics Mock.")
            use_mock = True
    else:
        if not args.mock:
            print(f"[NOTICE] Host OS ({sys.platform}) does not have active Linux SocketCAN. Activating High-Fidelity Physics Mock.")
        use_mock = True

    if use_mock:
        mock_worker = HighFidelityMockECUSimulator(state=state)
        mock_worker.start()

    # Start Unified HTTP and WebSocket Server
    server = AsyncUnifiedDashboardServer(host=args.host, port=args.port, web_dir=web_path, state=state)

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down CAN-Sentinel Dashboard Bridge.")


if __name__ == "__main__":
    main()
