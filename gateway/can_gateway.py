"""
CAN-Sentinel: security gateway.
Forwards frames from vcan0 to vcan1 only.
Lab use only, on virtual CAN interfaces.
"""

import argparse
import json
import math
import os
import select
import socket
import struct
import time

CONTROL_SOCKET = "/tmp/can_sentinel_gw.sock"
EVENT_FILE = "gateway_events.jsonl"

ALLOWED = {
    0x0A0: 0.020,
    0x0B0: 0.010,
    0x100: 0.010,
    0x200: 0.020,
    0x300: 0.100,
    0x600: 0.100,
    0x7DF: None,
}

MAX_COUNTER_STEP = 3
RESYNC_PERIODS = 5
DEFAULT_DURATION = 30.0
CAN_FRAME = struct.Struct("=IB3x8s")


def id_text(can_id):
    return f"0x{can_id:03X}"


def parse_id(value):
    if not isinstance(value, str):
        raise ValueError("can_id must be a hexadecimal string")

    can_id = int(value, 16)

    if not 0 <= can_id <= 0x7FF:
        raise ValueError("CAN ID must be between 0x000 and 0x7FF")

    return can_id


class GatewayCore:
    """Forwarding decisions, independent of CAN sockets."""

    def __init__(self, allowed=None):
        self.allowed = dict(ALLOWED if allowed is None else allowed)
        self.quarantine = {}
        self.last_counter = {}
        self.last_time = {}
        self.forwarded = 0
        self.dropped = {}

    def handle_command(self, cmd, now):
        if not isinstance(cmd, dict):
            return {"type": "ack", "ok": False,
                    "error": "command must be a JSON object"}, None

        kind = cmd.get("type")

        if kind == "quarantine":
            try:
                can_id = parse_id(cmd["can_id"])
                mode = cmd.get("mode", "counter")
                duration = float(cmd.get("duration_s", DEFAULT_DURATION))
            except (KeyError, TypeError, ValueError) as exc:
                return {"type": "ack", "ok": False,
                        "error": str(exc)}, None

            if can_id not in self.allowed:
                return {"type": "ack", "ok": False,
                        "error": "CAN ID is not allowed"}, None

            if mode not in ("counter", "drop"):
                return {"type": "ack", "ok": False,
                        "error": f"unknown mode {mode}"}, None

            if not math.isfinite(duration) or duration <= 0:
                return {"type": "ack", "ok": False,
                        "error": "duration_s must be positive and finite"}, None

            reason = str(cmd.get("reason", ""))
            renewed = can_id in self.quarantine

            self.quarantine[can_id] = {
                "mode": mode,
                "until": now + duration,
                "reason": reason,
            }

            event = None if renewed else {
                "timestamp": round(now, 6),
                "event": "quarantine_start",
                "can_id": id_text(can_id),
                "mode": mode,
                "duration_s": duration,
                "reason": reason,
            }

            return {
                "type": "ack",
                "ok": True,
                "can_id": id_text(can_id),
                "mode": mode,
                "until": round(now + duration, 3),
                "renewed": renewed,
            }, event

        if kind == "release":
            try:
                can_id = parse_id(cmd["can_id"])
            except (KeyError, TypeError, ValueError) as exc:
                return {"type": "ack", "ok": False,
                        "error": str(exc)}, None

            existed = self.quarantine.pop(can_id, None) is not None

            event = {
                "timestamp": round(now, 6),
                "event": "quarantine_end",
                "can_id": id_text(can_id),
                "why": "released",
            } if existed else None

            return {
                "type": "ack",
                "ok": True,
                "can_id": id_text(can_id),
                "released": existed,
            }, event

        if kind == "status":
            return self.status(now), None

        return {
            "type": "ack",
            "ok": False,
            "error": f"unknown type {kind}",
        }, None

    def status(self, now):
        return {
            "type": "status",
            "forwarded": self.forwarded,
            "dropped": dict(self.dropped),
            "quarantined": [
                {
                    "can_id": id_text(can_id),
                    "mode": item["mode"],
                    "seconds_left": round(item["until"] - now, 1),
                }
                for can_id, item in sorted(self.quarantine.items())
            ],
        }

    def expire(self, now):
        events = []

        expired = [
            can_id for can_id, item in self.quarantine.items()
            if item["until"] <= now
        ]

        for can_id in expired:
            del self.quarantine[can_id]
            events.append({
                "timestamp": round(now, 6),
                "event": "quarantine_end",
                "can_id": id_text(can_id),
                "why": "expired",
            })

        return events

    def _drop(self, reason):
        self.dropped[reason] = self.dropped.get(reason, 0) + 1
        return False

    @staticmethod
    def _valid_step(diff, elapsed, period):
        step = diff % 256

        if not 1 <= step <= MAX_COUNTER_STEP:
            return False

        if period is None:
            return step == 1

        return elapsed >= (step - 0.5) * period

    def decide(self, can_id, data, now):
        if can_id not in self.allowed:
            return self._drop("not_allowed")

        quarantine = self.quarantine.get(can_id)

        if quarantine is not None and quarantine["mode"] == "drop":
            return self._drop("quarantine_drop")

        counter = data[7] if len(data) >= 8 else None

        if counter is not None:
            last = self.last_counter.get(can_id)
            period = self.allowed.get(can_id)

            elapsed = now - self.last_time.get(
                can_id, float("-inf")
            )

            stale = (
                period is not None
                and elapsed > RESYNC_PERIODS * period
            )

            valid = (
                last is None
                or stale
                or self._valid_step(
                    counter - last, elapsed, period
                )
            )

            if valid:
                self.last_counter[can_id] = counter
                self.last_time[can_id] = now
            elif (
                quarantine is not None
                and quarantine["mode"] == "counter"
            ):
                return self._drop("quarantine_counter")

        self.forwarded += 1
        return True


def open_can(iface):
    can_socket = socket.socket(
        socket.PF_CAN,
        socket.SOCK_RAW,
        socket.CAN_RAW,
    )
    can_socket.bind((iface,))
    return can_socket


def open_control(path):
    if os.path.lexists(path):
        raise FileExistsError(
            f"Control socket path already exists: {path}. "
            "Check and remove a stale socket manually if appropriate."
        )

    control = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    try:
        control.bind(path)
        os.chmod(path, 0o666)
        control.listen(5)
        control.setblocking(False)
        return control
    except Exception:
        control.close()
        raise


def log_event(event, path):
    print(json.dumps(event), flush=True)

    with open(path, "a", encoding="utf-8") as file:
        file.write(
            json.dumps(event, separators=(",", ":")) + "\n"
        )


def run(src, dst, control_path, event_path):
    if src != "vcan0" or dst != "vcan1":
        raise ValueError("Gateway supports only vcan0 -> vcan1")

    core = GatewayCore()
    rx = open_can(src)

    try:
        tx = open_can(dst)
    except Exception:
        rx.close()
        raise

    try:
        control = open_control(control_path)
    except Exception:
        rx.close()
        tx.close()
        raise

    clients = []
    buffers = {}

    print(
        f"Gateway {src} -> {dst}; control socket {control_path}",
        flush=True,
    )

    last_report = time.time()

    try:
        while True:
            ready, _, _ = select.select(
                [rx, control] + clients, [], [], 0.5
            )

            now = time.time()

            for event in core.expire(now):
                log_event(event, event_path)

            for current in ready:

                if current is rx:
                    raw = rx.recv(CAN_FRAME.size)

                    if len(raw) != CAN_FRAME.size:
                        continue

                    can_id, dlc, data = CAN_FRAME.unpack(raw)

                    if dlc > 8:
                        continue

                    if can_id & 0xE0000000:
                        continue

                    if core.decide(
                        can_id & 0x7FF,
                        data[:dlc],
                        now,
                    ):
                        tx.send(raw)

                elif current is control:
                    conn, _ = control.accept()
                    conn.setblocking(False)
                    clients.append(conn)
                    buffers[conn] = ""

                else:
                    try:
                        chunk = current.recv(4096).decode(
                            "utf-8", errors="replace"
                        )
                    except OSError:
                        chunk = ""

                    if not chunk:
                        clients.remove(current)
                        buffers.pop(current, None)
                        current.close()
                        continue

                    buffers[current] += chunk

                    if len(buffers[current]) > 65536:
                        current.close()
                        clients.remove(current)
                        buffers.pop(current, None)
                        continue

                    lines = buffers[current].split("\n")
                    buffers[current] = lines.pop()

                    for line in lines:
                        if not line.strip():
                            continue

                        try:
                            command = json.loads(line)
                            reply, event = core.handle_command(
                                command, now
                            )
                        except (
                            ValueError,
                            KeyError,
                            TypeError,
                            json.JSONDecodeError,
                        ) as exc:
                            reply = {
                                "type": "ack",
                                "ok": False,
                                "error": str(exc),
                            }
                            event = None

                        current.sendall(
                            (json.dumps(reply) + "\n").encode()
                        )

                        if event:
                            log_event(event, event_path)

            if now - last_report >= 10:
                print(
                    json.dumps(core.status(now)),
                    flush=True,
                )
                last_report = now

    except KeyboardInterrupt:
        print("Gateway stopped.")

    finally:
        for client in clients:
            client.close()

        control.close()
        rx.close()
        tx.close()

        if os.path.exists(control_path):
            os.unlink(control_path)


def main():
    parser = argparse.ArgumentParser(
        description="CAN-Sentinel security gateway (vcan only)"
    )

    parser.add_argument("--src", default="vcan0")
    parser.add_argument("--dst", default="vcan1")
    parser.add_argument("--control", default=CONTROL_SOCKET)
    parser.add_argument("--events", default=EVENT_FILE)

    args = parser.parse_args()

    run(
        args.src,
        args.dst,
        args.control,
        args.events,
    )


if __name__ == "__main__":
    main()
