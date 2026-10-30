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
COUNTER_MIN_STREAM = 5      # frames needed before a counter sequence counts as continuous
REPLAY_STREAM_SHARE = 0.8   # share of an ID's frames that must sit in continuous sequences


def counter_values(data_hex_series):
    """Rolling counter (byte 7) of each 8-byte payload; frames without one are skipped."""
    values = []
    for data_hex in data_hex_series:
        if isinstance(data_hex, str) and len(data_hex) >= 16:
            try:
                values.append(int(data_hex[14:16], 16))
            except ValueError:
                pass
    return values


def counter_streams(counters):
    """Split one ID's counters (in time order) into continuous sequences.

    Each frame joins the sequence it continues (previous value + 1, with
    wrap-around); otherwise it starts a new sequence. Genuine traffic is one
    sequence. A replay attack adds a second sequence (old frames re-sent with
    their old, still-continuous counters). A spoofing attacker that does not
    follow the counter produces many short or one-frame sequences.
    """
    if not counters:
        return []
    modulus = 16 if max(counters) < 16 else 256  # design: 0-255; also accepts 0-15
    streams = []
    for value in counters:
        for stream in streams:
            if (value - stream[-1]) % modulus == 1:
                stream.append(value)
                break
        else:
            streams.append([value])
    return [len(s) for s in streams]


def classify_injection(id_frames):
    """For an ID sending too fast: 'replay' if the extra frames keep a valid
    counter sequence of their own, otherwise 'spoof'."""
    lengths = counter_streams(counter_values(id_frames["data_hex"]))
    long_streams = [n for n in lengths if n >= COUNTER_MIN_STREAM]
    total = sum(lengths)
    if total and len(long_streams) >= 2 and sum(long_streams) / total >= REPLAY_STREAM_SHARE:
        return "replay", len(long_streams)
    return "spoof", len(lengths)


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
    # R7: for an ID sending too fast, the rolling counter tells replay from spoofing
    for can_id, period in BASELINE_PERIODS.items():
        expected = window_len / period
        ratio = counts.get(can_id, 0) / expected
        if ratio > RATE_RATIO_LIMIT:
            kind, streams = classify_injection(frames[frames["can_id"] == can_id])
            if kind == "replay":
                attack, rule = "replay", "R7_counter_replay"
                detail = f"{can_id} at {ratio:.1f}x normal rate, {streams} valid counter sequences"
            else:
                attack = "spoof_brake" if can_id == "0x0A0" else "unknown_anomaly"
                rule = "R5_rate_exceeded"
                detail = f"{can_id} at {ratio:.1f}x normal rate, {streams} counter sequences"
            results.append(finding(rule, attack, can_id,
                                   min(1.0, 0.4 + (ratio - 1) / 2), detail))
        times = frames.loc[frames["can_id"] == can_id, "timestamp"]
        if len(times) >= 2:
            max_gap = times.diff().max()
            if max_gap > GAP_PERIODS_LIMIT * period:
                results.append(finding("R6_periodic_gap", "masquerade", can_id, 0.7,
                                       f"{can_id} silent for {max_gap * 1000:.0f} ms"))

    return results
