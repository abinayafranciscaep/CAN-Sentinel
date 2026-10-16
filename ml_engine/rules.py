"""
CAN-Sentinel: rules layer.

Fast, explainable checks on the raw frames inside one time window. Each rule
that fires returns a finding with the suspected attack, the suspect CAN ID and
a confidence. Rules complement the statistics layer and the Isolation Forest:
they name the attack and the ECU directly instead of only saying "anomaly".

Author: Abinaya Francisca EP (Team Lead)
"""

from features import BASELINE_PERIODS, DIAGNOSTIC_ID, KNOWN_IDS

NORMAL_BUS_FPS = sum(1 / p for p in BASELINE_PERIODS.values())  # about 320
RATE_RATIO_LIMIT = 1.5      # a periodic ID sending 50% more than normal
GAP_PERIODS_LIMIT = 5       # a periodic ID silent for 5 of its periods
FLOOD_BUS_RATIO = 2.0       # total bus traffic at twice the normal rate
FUZZ_UNKNOWN_IDS = 5        # many different unknown IDs in one window


def finding(rule, attack_type, suspect_id, confidence, detail):
    return {"rule": rule, "attack_type": attack_type, "suspect_id": suspect_id,
            "confidence": round(float(confidence), 2), "detail": detail}


def check_window(frames, window_len):
    """Run every rule on one window of frames (DataFrame from features.load_frames)."""
    results = []
    if frames.empty:
        return results

    counts = frames["can_id"].value_counts()
    bus_fps = len(frames) / window_len

    # R1 + R2: IDs outside the baseline -> flood (one dominant ID) or fuzz (many IDs)
    unknown = counts[~counts.index.isin(KNOWN_IDS)]
    if len(unknown) >= FUZZ_UNKNOWN_IDS:
        results.append(finding("R2_many_unknown_ids", "fuzz", unknown.index[0],
                               min(1.0, len(unknown) / 20 + 0.5),
                               f"{len(unknown)} unknown IDs in window"))
    elif len(unknown) > 0 and bus_fps > FLOOD_BUS_RATIO * NORMAL_BUS_FPS:
        top = unknown.index[0]
        results.append(finding("R1_unknown_id_flood", "flood", top,
                               min(1.0, bus_fps / (4 * NORMAL_BUS_FPS) + 0.5),
                               f"bus at {bus_fps:.0f} fps, dominant unknown ID {top}"))
    elif len(unknown) > 0:
        results.append(finding("R1_unknown_id", "unknown_anomaly", unknown.index[0],
                               0.6, f"unknown ID {unknown.index[0]} seen"))

    # R3: malformed frames (payload length does not match DLC)
    bad = frames[frames["dlc_mismatch"] == 1]
    if len(bad):
        results.append(finding("R3_dlc_mismatch", "fuzz", bad["can_id"].iloc[0], 0.8,
                               f"{len(bad)} frames with DLC/payload mismatch"))

    # R4: diagnostic requests while the vehicle is operating
    diag = int(counts.get(DIAGNOSTIC_ID, 0))
    if diag:
        results.append(finding("R4_diagnostic_request", "diag_abuse", DIAGNOSTIC_ID,
                               min(1.0, 0.6 + diag / 20), f"{diag} diagnostic frames"))

    # R5 + R6: per-ID rate too high (spoofing / replay) or long silence (masquerade)
    for can_id, period in BASELINE_PERIODS.items():
        expected = window_len / period
        ratio = counts.get(can_id, 0) / expected
        if ratio > RATE_RATIO_LIMIT:
            attack = "spoof_brake" if can_id == "0x0A0" else "unknown_anomaly"
            results.append(finding("R5_rate_exceeded", attack, can_id,
                                   min(1.0, 0.4 + (ratio - 1) / 2),
                                   f"{can_id} at {ratio:.1f}x normal rate"))
        times = frames.loc[frames["can_id"] == can_id, "timestamp"]
        if len(times) >= 2:
            max_gap = times.diff().max()
            if max_gap > GAP_PERIODS_LIMIT * period:
                results.append(finding("R6_periodic_gap", "masquerade", can_id, 0.7,
                                       f"{can_id} silent for {max_gap * 1000:.0f} ms"))

    return results
