"""
stand_in_sender.py - temporary baseline traffic generator for vcan0.

Sends the six periodic CAN IDs from the baseline table
(docs/week1_design.md, Section 2) at their nominal periods, so the CSV logger
can record realistic "normal" traffic until the real ECU simulators are ready.
The diagnostic ID 0x7DF is event-only and is intentionally not sent.

Usage (vcan0 must already be up):
    python3 dashboard/stand_in_sender.py            # run until Ctrl+C
    python3 dashboard/stand_in_sender.py 600        # run for 600 seconds

Assumption: multi-byte values are big-endian, because the design doc does not
specify byte order. Confirm against the final ECU layouts (open item O1).
"""
import math
import random
import struct
import sys
import time

import can

# CAN ID -> sending period in seconds (baseline table).
PERIODS = {
    0x0A0: 0.020,   # brake
    0x0B0: 0.010,   # steering
    0x100: 0.010,   # engine RPM
    0x200: 0.020,   # vehicle speed
    0x300: 0.100,   # engine temperature
    0x600: 0.100,   # infotainment heartbeat
}

# Real ECUs do not send at perfect intervals. +/- 1 ms of jitter avoids teaching
# the model an unrealistically clean timing baseline.
JITTER = 0.001


def make_payload(can_id, t, counter):
    """Build the 8-byte payload for one frame.

    t       -- seconds since start, used to make signal values change smoothly
    counter -- rolling counter (0-255), stored in byte 7 where the layout has one
    """
    data = bytearray(8)

    if can_id == 0x0A0:                          # brake: B0 pressure, B1 switch
        pressure = int(50 + 50 * math.sin(t / 4))            # 0-100
        data[0] = pressure
        data[1] = 1 if pressure > 60 else 0                  # switch on at high pressure
    elif can_id == 0x0B0:                        # steering: B0-B1 signed angle, 0.1 deg
        angle = int(300 * math.sin(t / 7))                   # about +/- 30 degrees
        data[0:2] = struct.pack(">h", angle)                 # signed 16-bit, big-endian
    elif can_id == 0x100:                        # RPM: B0-B1 unsigned
        rpm = int(3000 + 2000 * math.sin(t / 6)) + random.randint(-20, 20)
        data[0:2] = struct.pack(">H", rpm)                   # unsigned 16-bit, big-endian
    elif can_id == 0x200:                        # speed: B0 in km/h
        data[0] = int(60 + 40 * math.sin(t / 8))             # 20-100 km/h
    elif can_id == 0x300:                        # temperature: B0 = coolant temp + 40
        data[0] = int(125 + 5 * math.sin(t / 30))            # 80-90 C after the -40 offset
    elif can_id == 0x600:                        # infotainment heartbeat: B0 status
        data[0] = 1

    if can_id != 0x300:                          # temperature layout has no counter
        data[7] = counter
    return bytes(data)


def main():
    # Optional run time in seconds; None means run until Ctrl+C.
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else None

    bus = can.Bus(channel="vcan0", interface="socketcan")
    start = time.monotonic()                     # monotonic clock never jumps backwards
    nominal = {cid: start for cid in PERIODS}    # ideal send time of the next frame per ID
    due = dict(nominal)                          # actual send time = nominal + jitter
    counters = {cid: 0 for cid in PERIODS}
    sent = 0

    try:
        while duration is None or time.monotonic() - start < duration:
            now = time.monotonic()
            for can_id, period in PERIODS.items():
                if now >= due[can_id]:
                    msg = can.Message(
                        arbitration_id=can_id,
                        data=make_payload(can_id, now - start, counters[can_id]),
                        is_extended_id=False,    # classic 11-bit IDs only
                    )
                    bus.send(msg)
                    sent += 1
                    counters[can_id] = (counters[can_id] + 1) % 256   # wraps 255 -> 0
                    # Advance the ideal schedule by one period (not "now + period"),
                    # so small delays do not accumulate into rate drift.
                    nominal[can_id] += period
                    due[can_id] = nominal[can_id] + random.uniform(-JITTER, JITTER)
            time.sleep(0.0005)                   # short sleep so the loop does not use 100% CPU
    except KeyboardInterrupt:
        pass                                     # Ctrl+C is the normal way to stop
    finally:
        bus.shutdown()
        print(f"Sent {sent} frames")


if __name__ == "__main__":
    main()