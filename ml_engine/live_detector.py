"""
CAN-Sentinel: live detector (Week 3 integration).

Reads frames from the C sniffer over a Unix domain socket (one JSON object per
line, as agreed in docs/week1_design.md Section 5.2), keeps a sliding window,
runs the same three detection layers as detect.py, and writes alert JSON lines
for the dashboard.

Until the sniffer bridge is ready, --replay feeds a recorded CSV through the
same code path, so the integration can be tested now.

Usage (from the repository root):
    python ml_engine/live_detector.py                       # live, from the sniffer socket
    python ml_engine/live_detector.py --replay data/flood_run1_1013.csv

With --gateway, confirmed attacks are also sent to the security gateway, which
quarantines the CAN ID (docs/gateway_design.md):
    python ml_engine/live_detector.py --alerts alerts.jsonl --gateway

In live mode the detector waits for the sniffer if it is not running yet,
reconnects if the sniffer restarts, and skips malformed lines instead of
stopping.

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import json
import socket
import time
from collections import deque

import pandas as pd

from alerts import to_json_line
from detect import Detector
from features import normalise_id, payload_entropy
from gateway_client import GATEWAY_SOCKET, GatewayClient, decide_action
from train_model import MODEL_PATH

SOCKET_PATH = "/tmp/can_sentinel.sock"
ALERT_FILE = "alerts.jsonl"


REQUIRED_FIELDS = ("timestamp", "can_id", "dlc", "data_hex")


def parse_line(line):
    """One NDJSON line from the sniffer -> frame dict, or None if it is not a valid frame.

    A bad line (cut off, not JSON, missing a field) is skipped instead of
    stopping the detector.
    """
    line = line.strip()
    if not line:
        return None
    try:
        frame = json.loads(line)
        if not all(k in frame for k in REQUIRED_FIELDS):
            return None
        frame["timestamp"] = float(frame["timestamp"])
        frame["dlc"] = int(frame["dlc"])
        frame["data_hex"] = str(frame["data_hex"] or "")
        return frame
    except (ValueError, TypeError, AttributeError):
        return None


def split_lines(buffer, chunk):
    """Add a received chunk to the buffer; return (complete lines, leftover)."""
    buffer += chunk
    *lines, rest = buffer.split("\n")
    return lines, rest


def connect(path, retries, wait):
    """Connect to the sniffer, retrying while it is not running yet."""
    for attempt in range(1, retries + 1):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
            print(f"Connected to sniffer at {path}", flush=True)
            return s
        except OSError as e:
            s.close()
            print(f"Sniffer not ready ({e.strerror}); retry {attempt}/{retries} in {wait:.0f} s",
                  flush=True)
            time.sleep(wait)
    raise SystemExit(f"Could not connect to {path}. Is the sniffer running?")


def frames_from_socket(path, retries=30, wait=2.0, reconnect=True):
    """Yield frame dicts from the sniffer's Unix domain socket.

    If the sniffer is not running yet, keep retrying; if it stops, reconnect
    (unless reconnect is False). Bad lines are counted and skipped.
    """
    skipped = 0
    while True:
        with connect(path, retries, wait) as s:
            buffer = ""
            while True:
                chunk = s.recv(4096).decode("utf-8", errors="replace")
                if not chunk:
                    break
                lines, buffer = split_lines(buffer, chunk)
                for line in lines:
                    frame = parse_line(line)
                    if frame is None:
                        if line.strip():
                            skipped += 1
                            if skipped in (1, 10, 100) or skipped % 1000 == 0:
                                print(f"Skipped {skipped} malformed line(s) from the sniffer",
                                      flush=True)
                        continue
                    yield frame
        print("Sniffer closed the connection.", flush=True)
        if not reconnect:
            return


def frames_from_csv(path, realtime=False):
    """Yield frame dicts from a recorded CSV (replay mode)."""
    df = pd.read_csv(path).sort_values("timestamp")
    previous = None
    for row in df.itertuples(index=False):
        if realtime and previous is not None:
            time.sleep(max(0.0, row.timestamp - previous))
        previous = row.timestamp
        yield {"timestamp": row.timestamp, "can_id": row.can_id, "dlc": row.dlc,
               "data_hex": "" if pd.isna(row.data_hex) else str(row.data_hex)}


def to_frame_table(window):
    df = pd.DataFrame(list(window))
    df["can_id"] = df["can_id"].map(normalise_id)
    df["data_hex"] = df["data_hex"].fillna("").astype(str)
    df["payload_entropy"] = df["data_hex"].map(payload_entropy)
    df["dlc_mismatch"] = (df["data_hex"].str.len() != df["dlc"] * 2).astype(int)
    df["is_unknown_id"] = 0
    df["label"] = "unknown"
    return df


def run(source, window_len=1.0, step=0.5, model_path=MODEL_PATH, alert_file=ALERT_FILE,
        gateway=None):
    """Detect on a stream of frames; with a GatewayClient, also block confirmed attacks."""
    detector = Detector(model_path, window_len)
    window = deque()
    next_check = None
    total = 0
    with open(alert_file, "a") as out:
        for frame in source:
            window.append(frame)
            now = frame["timestamp"]
            while window and window[0]["timestamp"] < now - window_len:
                window.popleft()
            if next_check is None:
                next_check = now + window_len
            if now >= next_check:
                for alert in detector.detect_window(to_frame_table(window), now):
                    line = to_json_line(alert)
                    print(line, flush=True)
                    out.write(line + "\n")
                    out.flush()
                    total += 1
                    command = decide_action(alert) if gateway else None
                    if command:
                        reply = gateway.send(command)
                        if reply and reply.get("ok") and not reply.get("renewed"):
                            print(f"GATEWAY: quarantined {command['can_id']} "
                                  f"({command['mode']} mode, {command['duration_s']:.0f} s)",
                                  flush=True)
                next_check = now + step
    print(f"Stream ended; {total} alerts written to {alert_file}")


def main():
    p = argparse.ArgumentParser(description="CAN-Sentinel live detector")
    p.add_argument("--socket", default=SOCKET_PATH)
    p.add_argument("--replay", help="CSV to replay instead of the live socket")
    p.add_argument("--realtime", action="store_true", help="replay at recorded speed")
    p.add_argument("--model", default=MODEL_PATH)
    p.add_argument("--alerts", default=ALERT_FILE)
    p.add_argument("--retries", type=int, default=30, help="connection attempts before giving up")
    p.add_argument("--no-reconnect", action="store_true", help="stop when the sniffer stops")
    p.add_argument("--gateway", action="store_true",
                   help="send quarantine commands to the security gateway (detect -> block)")
    p.add_argument("--gateway-socket", default=GATEWAY_SOCKET)
    a = p.parse_args()
    if a.replay:
        source = frames_from_csv(a.replay, a.realtime)
    else:
        source = frames_from_socket(a.socket, a.retries, reconnect=not a.no_reconnect)
    gateway = GatewayClient(a.gateway_socket) if a.gateway else None
    run(source, model_path=a.model, alert_file=a.alerts, gateway=gateway)


if __name__ == "__main__":
    main()
