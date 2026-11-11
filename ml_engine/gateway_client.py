"""
CAN-Sentinel: detector -> gateway link (detect, then block).

Decides which alerts should make the security gateway quarantine a CAN ID, and
sends the quarantine command over the gateway's control socket
(/tmp/can_sentinel_gw.sock, one JSON object per line; docs/gateway_design.md).

Only confident, explainable alerts trigger blocking, so a model-only anomaly
can never cut off a real ECU by mistake:

| Alert              | Gateway action                                      |
|--------------------|-----------------------------------------------------|
| spoof_brake, replay| quarantine the ID in "counter" mode (fakes dropped, |
|                    | real frames with the right counter still pass)      |
| masquerade         | quarantine the ID in "drop" mode (real ECU is gone; |
|                    | the receiver falls back to its safe state)          |
| diag_abuse         | quarantine 0x7DF in "drop" mode                     |
| flood, fuzz        | none if the ID is unknown (the gateway's allowlist  |
|                    | already drops it); "drop" if a baseline ID is abused|
| unknown_anomaly    | none (logged for a person to review)                |

Used by live_detector.py --gateway. Manual control for the analyst:
    python ml_engine/gateway_client.py status
    python ml_engine/gateway_client.py release 0x0B0

Author: Abinaya Francisca EP (Team Lead)
"""

import json
import socket

GATEWAY_SOCKET = "/tmp/can_sentinel_gw.sock"
QUARANTINE_SECONDS = 30.0
MIN_CONFIDENCE = 0.7
BLOCK_SEVERITIES = ("high", "critical")
BASELINE_IDS = ("0x0A0", "0x0B0", "0x100", "0x200", "0x300", "0x600")
MODE_BY_ATTACK = {"spoof_brake": "counter", "replay": "counter",
                  "masquerade": "drop", "diag_abuse": "drop"}


def decide_action(alert):
    """Return the quarantine command for an alert, or None if no blocking is needed."""
    attack, suspect = alert["attack_type"], alert["suspect_id"]
    if alert.get("detection_layer") != "rules":
        return None
    if alert.get("confidence", 0) < MIN_CONFIDENCE or alert.get("severity") not in BLOCK_SEVERITIES:
        return None
    if attack in MODE_BY_ATTACK:
        mode = MODE_BY_ATTACK[attack]
        can_id = "0x7DF" if attack == "diag_abuse" else suspect
    elif attack in ("flood", "fuzz") and suspect in BASELINE_IDS:
        mode, can_id = "drop", suspect
    else:
        return None
    reason = (f"{attack} on {suspect} ({alert['detection_layer']}, confidence "
              f"{alert['confidence']:.2f}, {alert.get('technique') or 'no technique'})")
    return {"type": "quarantine", "can_id": can_id, "mode": mode,
            "duration_s": QUARANTINE_SECONDS, "reason": reason, "alert": alert}


class GatewayClient:
    """Keeps one connection to the gateway; never stops the detector if the gateway is down."""

    def __init__(self, path=GATEWAY_SOCKET, timeout=0.5):
        self.path, self.timeout, self.sock, self.buffer = path, timeout, None, ""

    def _connect(self):
        if self.sock is None:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect(self.path)
            self.sock = s

    def send(self, command):
        """Send one command and return the gateway's reply, or None if it is unreachable."""
        try:
            self._connect()
            self.sock.sendall((json.dumps(command, separators=(",", ":")) + "\n").encode())
            while "\n" not in self.buffer:
                chunk = self.sock.recv(4096).decode("utf-8", errors="replace")
                if not chunk:
                    raise OSError("gateway closed the connection")
                self.buffer += chunk
            line, self.buffer = self.buffer.split("\n", 1)
            return json.loads(line)
        except (OSError, ValueError, AttributeError) as e:  # AttributeError: no AF_UNIX (Windows)
            print(f"Gateway not reachable ({e}); command not delivered", flush=True)
            self.close()
            return None

    def close(self):
        if self.sock is not None:
            self.sock.close()
        self.sock, self.buffer = None, ""


def main():
    """Manual control for the analyst: show the gateway status or release an ID."""
    import argparse
    p = argparse.ArgumentParser(description="CAN-Sentinel gateway control")
    p.add_argument("action", choices=["status", "release"])
    p.add_argument("can_id", nargs="?", help="CAN ID to release, for example 0x0B0")
    p.add_argument("--socket", default=GATEWAY_SOCKET)
    a = p.parse_args()
    if a.action == "release" and not a.can_id:
        p.error("release needs a CAN ID, for example: release 0x0B0")
    command = {"type": "status"} if a.action == "status" else {"type": "release", "can_id": a.can_id}
    reply = GatewayClient(a.socket, timeout=2).send(command)
    if reply is not None:
        print(json.dumps(reply, indent=2))


if __name__ == "__main__":
    main()
