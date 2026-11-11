"""
CAN-Sentinel: synthetic test traffic generator.

Creates labelled CAN CSV files in the agreed five-column format
(timestamp, can_id, dlc, data_hex, label) so the ML engine can be developed
and tested before the team's real datasets are ready. Normal traffic follows
the ECU baseline in docs/week1_design.md (about 320 frames per second), with
small timing jitter and changing signal values.

This is SIMULATED data for development and unit testing only. Results reported
in the final evaluation must come from the team's recorded datasets.

Usage (from the repository root):
    python ml_engine/generate_test_traffic.py normal data/synthetic_normal.csv --seconds 120
    python ml_engine/generate_test_traffic.py flood data/synthetic_flood.csv
    python ml_engine/generate_test_traffic.py all data/synthetic_all_attacks.csv
    python ml_engine/generate_test_traffic.py lowrate_spoof data/synthetic_lowrate_spoof.csv

Author: Abinaya Francisca EP (Team Lead)
"""

import argparse
import csv
import random

# Baseline from docs/week1_design.md, Section 2: CAN ID -> period in seconds
BASELINE = {
    "0x0A0": 0.020,  # brake
    "0x0B0": 0.010,  # steering
    "0x100": 0.010,  # engine RPM
    "0x200": 0.020,  # vehicle speed
    "0x300": 0.100,  # engine temperature
    "0x600": 0.100,  # infotainment heartbeat
}
JITTER = 0.001        # +/- 1 ms timing jitter
START = 1791300000.0  # fixed start time so files are reproducible
ATTACKS = ["flood", "spoof_brake", "replay", "fuzz", "masquerade", "diag_abuse"]
# Extra test cases, not part of "all" (so the six-attack file stays the same)
EXTRA_ATTACKS = ["lowrate_spoof"]
LOWRATE_FPS = 2  # fake brake frames per second in lowrate_spoof


def normal_payload(can_id, t, counter):
    """8-byte payload with a slowly changing signal and a rolling counter in byte 7."""
    if can_id == "0x0A0":
        signal = [int(20 + 15 * ((t // 5) % 2)), 1 if (t // 5) % 2 else 0]
    elif can_id == "0x0B0":
        angle = int(1000 + 300 * ((t % 8) - 4) / 4) & 0xFFFF
        signal = [angle >> 8, angle & 0xFF]
    elif can_id == "0x100":
        rpm = int(2000 + 500 * ((t % 10) / 10))
        signal = [rpm >> 8, rpm & 0xFF]
    elif can_id == "0x200":
        signal = [int(40 + (t % 20))]
    elif can_id == "0x300":
        signal = [90 + 40]  # 90 C coolant with -40 offset
    else:
        signal = [1]  # infotainment status OK
    data = signal + [0] * (7 - len(signal)) + [counter % 256]
    return "".join(f"{b:02X}" for b in data)


def normal_frames(seconds, rng, skip=None):
    """Baseline traffic. `skip` = (can_id, start, end) silences one ID (masquerade)."""
    rows = []
    for can_id, period in BASELINE.items():
        t, counter = 0.0, 0
        while t < seconds:
            if not (skip and skip[0] == can_id and skip[1] <= t < skip[2]):
                ts = START + t + rng.uniform(-JITTER, JITTER)
                rows.append([ts, can_id, 8, normal_payload(can_id, t, counter), "normal"])
                counter += 1
            t += period
    return rows


def attack_frames(kind, start, end, rng, recorded=None):
    rows = []
    t = start
    if kind == "flood":
        while t < end:
            rows.append([START + t, "0x000", 8, "0000000000000000", kind])
            t += 0.0005  # 2000 frames per second
    elif kind == "spoof_brake":
        while t < end:
            rows.append([START + t + 0.007, "0x0A0", 8, "64010000000000FF", kind])
            t += 0.020
    elif kind == "replay":
        # Re-send earlier brake frames (valid payloads, old counters) at the same rate
        old = [r for r in (recorded or []) if r[1] == "0x0A0"][: int((end - start) / 0.02)]
        for i, r in enumerate(old):
            rows.append([START + start + i * 0.020 + 0.009, r[1], r[2], r[3], kind])
    elif kind == "fuzz":
        while t < end:
            can_id = f"0x{rng.randint(0, 0x7FF):03X}"
            payload = "".join(f"{rng.randint(0, 255):02X}" for _ in range(8))
            rows.append([START + t, can_id, 8, payload, kind])
            t += 0.005
    elif kind == "masquerade":
        # Real steering ECU is silenced (see normal_frames skip); attacker takes over
        t = start + 0.3
        while t < end:
            rows.append([START + t, "0x0B0", 8, "0000000000000000", kind])
            t += 0.010
    elif kind == "lowrate_spoof":
        # A careful attacker: only a few fake brake frames per second, each with a
        # random counter, so the 0x0A0 rate rises by just 4% (labelled spoof_brake)
        while t < end:
            counter = rng.randint(0, 255)
            rows.append([START + t + rng.uniform(0.003, 0.017), "0x0A0", 8,
                         f"64010000000000{counter:02X}", "spoof_brake"])
            t += 1.0 / LOWRATE_FPS
    elif kind == "diag_abuse":
        while t < end:
            rows.append([START + t, "0x7DF", 8, "0211010000000000", kind])  # ECU reset request
            t += 0.5
    return rows


def build(kind, seconds, seed):
    rng = random.Random(seed)
    if kind == "normal":
        return normal_frames(seconds, rng)
    kinds = ATTACKS if kind == "all" else [kind]
    total = max(seconds, 30 + 15 * len(kinds))
    plan, t = [], 30.0  # 30 s of normal traffic before the first attack
    for k in kinds:
        plan.append((k, t, t + 10))
        t += 15
    skip = next(((("0x0B0", a, a + 0.3)) for k, a, b in plan if k == "masquerade"), None)
    rows = normal_frames(total, rng, skip)
    for k, a, b in plan:
        if k == "masquerade":  # steering stays silent while the attacker sends
            rows = [r for r in rows if not (r[1] == "0x0B0" and START + a <= r[0] < START + b)]
        rows += attack_frames(k, a, b, rng, recorded=rows)
    return rows


def main():
    p = argparse.ArgumentParser(description="CAN-Sentinel synthetic traffic generator")
    p.add_argument("kind", choices=["normal", "all"] + ATTACKS + EXTRA_ATTACKS)
    p.add_argument("output_csv")
    p.add_argument("--seconds", type=float, default=60, help="length of the recording")
    p.add_argument("--seed", type=int, default=1, help="random seed for reproducible files")
    a = p.parse_args()

    rows = sorted(build(a.kind, a.seconds, a.seed), key=lambda r: r[0])
    with open(a.output_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "can_id", "dlc", "data_hex", "label"])
        for r in rows:
            w.writerow([f"{r[0]:.6f}", r[1], r[2], r[3], r[4]])
    attacks = sum(1 for r in rows if r[4] != "normal")
    print(f"Wrote {len(rows)} frames ({attacks} attack frames) to {a.output_csv}")


if __name__ == "__main__":
    main()
