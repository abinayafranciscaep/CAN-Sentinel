# CAN-Sentinel: Final Report (Draft)

Intrusion detection for in-vehicle CAN networks

Group 3, Infotact Solutions Cybersecurity Internship
Team: Abinaya Francisca EP (Team Lead), Abdul Haleem P R (Member 1), Chetan (Member 2), Sadhamail (Member 3)

Draft prepared by Abinaya Francisca EP, Nov 10, 2026. Sections marked **[TO FILL]**
are completed from the team's real recordings and final integration test.

---

## 1. Summary

The CAN bus connects a vehicle's control units but has no sender authentication, so
any compromised node can send frames that other ECUs trust. CAN-Sentinel is a
passive intrusion detection system for a simulated vehicle network: six simulated
ECUs send traffic on a Linux virtual CAN bus (vcan0), a C sniffer streams the frames
to a detection engine, and a PyQt dashboard shows live traffic and alerts.

The detection engine combines nine explainable rules, a statistics layer and an
Isolation Forest trained only on normal traffic. On simulated data it detects all
six attack types within one second, with zero false alarms on normal traffic.
**[TO FILL: one sentence with the real-data result.]**

## 2. Problem and scope

- **Problem:** CAN frames carry no sender identity or authentication; a compromised
  infotainment unit can inject fake brake or steering frames (design doc, Section 1.1).
- **Scope:** a single Linux host with vcan0, classic CAN (11-bit IDs, DLC 0-8), six
  simulated ECUs at about 320 frames per second. No real vehicle is involved.
- **Out of scope:** CAN FD, physical bus effects, active blocking of frames.

## 3. System architecture

ECU simulator (C) -> vcan0 -> C sniffer -> Unix socket `/tmp/can_sentinel.sock`
(one JSON object per frame) -> ML engine -> alert JSON lines -> PyQt dashboard.
A CSV logger records traffic for training and evaluation.

| Component | Owner | Branch |
|---|---|---|
| ECU simulator, vcan0 setup, DBC | Abdul Haleem P R | member-1 |
| Attacker script, C sniffer, socket bridge | Chetan | member-2 |
| CSV logger, PyQt dashboard | Sadhamail | member-3 |
| ML engine, threat model, schemas, reports | Abinaya Francisca EP | lead |

ECU baseline (design doc, Section 2): 0x0A0 brake 20 ms, 0x0B0 steering 10 ms,
0x100 RPM 10 ms, 0x200 speed 20 ms, 0x300 temperature 100 ms, 0x600 infotainment
100 ms; 0x7DF diagnostics is event-only. Every frame is 8 bytes with a rolling counter
in byte 7 (0-255, confirmed Oct 30).

## 4. Threat model

STRIDE threat register T1-T8 with MITRE ATT&CK for ICS techniques (design doc,
Section 3), aligned with ISO/SAE 21434 risk assessment and UNECE R155 threat
categories. Six threats map to the six attacks implemented and tested:

| Attack | Threat | ATT&CK for ICS |
|---|---|---|
| flood | T7 Denial of service | T0814, T0813 |
| spoof_brake | T1 Spoofing | T0855, T0831 |
| replay | T3 Tampering | T0855 |
| fuzz | T4 Tampering | T0836 |
| masquerade | T2 Spoofing | T0856, T0832 |
| diag_abuse | T8 Elevation of privilege | T0858, T0816 |

T5 (repudiation) is addressed by suspect-ID attribution in every alert; T6 (passive
sniffing) cannot be detected by a passive IDS. Full mapping:
`docs/threat_detection_coverage.md`.

## 5. Detection method

Traffic is analysed in 1-second windows every 0.5 seconds.

| Layer | What it does |
|---|---|
| Rules R1-R9 | Unknown IDs, DLC mismatch, diagnostic requests, per-ID rate, silent IDs, rolling-counter checks (replay, masquerade, low-rate injection) |
| Statistics | Flags any of 34 window features outside its normal range (50% margin) |
| Isolation Forest | Flags unusual feature combinations; threshold at the 1st percentile of normal scores; needs 2 abnormal windows in a row |

Alerts follow the agreed JSON schema (timestamp, attack type, suspect CAN ID,
confidence, severity, affected system, detection layer, ATT&CK technique). The same
alert is not repeated within 2 seconds. `alert_summary.py` groups alerts into
incidents linked to the incident response playbook.

## 6. Datasets

| Dataset | Source | Use |
|---|---|---|
| Synthetic normal and six-attack files | `generate_test_traffic.py` | Development and unit tests |
| Official normal runs 1-3 (10 min each) | ECU simulator + CSV logger | Runs 1-2 training, run 3 false-alarm test **[TO FILL: dates, frame counts, data-check results from retrain.py]** |
| Labelled attack runs | Attacker script on vcan0 + logger | Per-attack evaluation **[TO FILL]** |

## 7. Results

### 7.1 Simulated data (development check)

`evaluate_alerts.py` on the synthetic six-attack file (120 s, 61,394 frames):

| Attack | Detected | Time to detect | Right attack type | Right CAN ID |
|---|---|---|---|---|
| flood | Yes | 0.50 s | 6/7 | 7/7 |
| spoof_brake | Yes | 0.49 s | 6/6 | 6/6 |
| replay | Yes | 0.49 s | 6/6 | 6/6 |
| fuzz | Yes | 0.50 s | 6/7 | n/a (random IDs) |
| masquerade | Yes | 0.20 s | 6/6 | 6/6 |
| diag_abuse | Yes | 0.50 s | 6/6 | 6/6 |

False alarms on 2 minutes of normal traffic: 0. Precision: 1.0. A low-rate spoofing
test (2 fake frames per second) is also detected (`docs/week4_lowrate_injection.md`).

How the results improved during development:

| Change | Effect |
|---|---|
| Statistics layer added (Week 2) | Flood and fuzz caught reliably |
| Cooldown, grouping, 2-window confirmation | Repeated and noisy alerts removed |
| R7 replay counter rule (Oct 30) | Replay named correctly instead of spoof_brake |
| R8 masquerade counter rule (Oct 31) | Masquerade alerts name the right ECU (6/6, was 1/13) |
| R9 low-rate injection rule (Nov 7) | Low-rate spoofing caught by the rules; spoof and replay detected in 0.49 s (was 0.99 s) |

### 7.2 Real recordings

**[TO FILL: retrain report (data checks, false alarms on run 3) and the
evaluate_alerts.py table for each labelled attack run.]**

### 7.3 Live integration

Live chain ECU simulator -> vcan0 -> sniffer -> dashboard verified on Oct 30 and 31
(`docs/week3_integration_test.md`): live frames, live frame rate and traffic share.
**[TO FILL: live detector connected at the same time; real alerts shown on the dashboard.]**

## 8. Limitations

- All traffic is simulated on a virtual bus; no physical CAN effects.
- An attacker who copies valid rolling-counter values avoids the counter rules (R7-R9).
- The Isolation Forest was trained on short synthetic data so far and raised one false
  alarm on extra synthetic normal traffic; retraining on 20 minutes of real traffic is planned.
- The sniffer-to-engine socket is assumed trusted (trust boundary TB4).
- Workshop diagnostics look the same as diagnostic abuse.

## 9. Future work

- Payload checks to tell replayed copies from forged frames.
- Active response, for example error frames against a confirmed attacker (bonus item).
- Testing on a physical CAN interface.
- Per-ECU message authentication (for example SecOC) as the long-term fix.

## 10. Repository guide

| Folder | Contents |
|---|---|
| `ecu_sim/` | ECU simulator (member-1) |
| `sniffer/`, `attacker/` | Sniffer and attacker script (member-2) |
| `dashboard/` | CSV logger and PyQt dashboard (member-3) |
| `ml_engine/` | Detection engine, tools and tests (lead) |
| `docs/` | Design, threat model, weekly results, playbook, this report |
