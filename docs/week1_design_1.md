# CAN-Sentinel: Week 1 Design Document

**Project:** CAN-Sentinel, Automotive ECU Intrusion Detection System
**Program:** Infotact Solutions, Advanced Cybersecurity Engineering (Vol. II), Project 1
**Week:** 1 (Oct 5 - Oct 11, 2026)
**Author:** Abinaya Francisca EP (Team Lead, Security Lead)
**Status:** Draft v1.0, for team review

---

## Contents

1. Architecture and trust boundaries
2. ECU baseline table
3. Threat model (STRIDE + MITRE ATT&CK for ICS)
4. Attack catalogue and dataset plan
5. Data schemas (CSV, socket JSON, alert JSON)
6. Week 1 checklist and open items

---

## 1. Architecture and trust boundaries

### 1.1 Problem

The CAN bus has no encryption and no sender authentication. Any node on the bus can
transmit any CAN ID, and every node trusts what it receives. A compromised node (for
example, the infotainment unit reached over Bluetooth or Wi-Fi) can therefore inject
frames that safety-critical ECUs accept as genuine, such as a fake brake command.

CAN-Sentinel detects such frames on a virtual SocketCAN bus, raises an alert on a
dashboard, and identifies the suspected CAN ID / ECU.

### 1.2 Data flow

```
 +-------------------+       +--------+       +-------------+    Unix domain    +-------------+   alert JSON   +----------------+
 | ECU simulators (C)| ----> | vcan0  | ----> | C sniffer   | ----------------> | ML engine   | -------------> | PyQt dashboard |
 | brake, steering,  |       | (bus)  |       | raw socket  |   socket (JSON    | rules +     |                | traffic, gauge,|
 | RPM, speed, temp, |       +--------+       +-------------+   line per frame) | stats + IF  |                | car diagram    |
 | infotainment      |           ^                  |                           +-------------+                +----------------+
 +-------------------+           |                  +--> CSV logger (training data)
                                 |
                       +-------------------+
                       | Attacker script   |
                       | (lab only, vcan0) |
                       +-------------------+
```

### 1.3 Components and owners

| Component | Language | Owner | Folder |
|---|---|---|---|
| vcan0 setup + ECU simulators | C / shell | Haleem (Member 1) | ecu_sim/ |
| Attacker script | Python or C | Chetan (Member 2) | attacker/ |
| C sniffer + Unix socket bridge | C | Chetan (Member 2) | sniffer/ |
| CSV logger | Python | Sadhamail (Member 3) | dashboard/ |
| ML engine (features, detection, alerts) | Python, scikit-learn | Abinaya (Lead) | ml_engine/ |
| PyQt dashboard | Python, PyQt | Sadhamail (Member 3) | dashboard/ |
| Threat model, schemas, reports | Markdown | Abinaya (Lead) | docs/ |

### 1.4 Trust boundaries

| ID | Boundary | Why it matters |
|---|---|---|
| TB1 | External world -> infotainment ECU (Bluetooth, Wi-Fi, USB) | Main entry point for the attacker. We assume this ECU can be compromised. |
| TB2 | Infotainment ECU -> CAN bus | No gateway or filtering in our model. A compromised infotainment ECU can send any ID. This is the boundary CAN-Sentinel monitors. |
| TB3 | Diagnostic port (OBD-II, ID 0x7DF) -> CAN bus | Physical / tool access that can issue diagnostic requests. |
| TB4 | Sniffer -> ML engine (Unix socket) | Local IPC on the same host. Assumed trusted for this project; noted as a limitation. |
| TB5 | ML engine -> dashboard (alert JSON) | Display only. Dashboard must never send frames back onto the bus. |

### 1.5 Assumptions and scope

- Everything runs on a single Linux host using the virtual interface vcan0. No real vehicle is involved.
- Classic CAN (11-bit IDs, DLC 0-8). CAN FD is out of scope.
- The IDS is passive (detect and alert). Active response is limited to the Week 4 bonus error-frame countermeasure.
- All attack code is used only on our own vcan0 lab setup.

---

## 2. ECU baseline table

Normal ("golden") traffic the ECU simulators must produce. Detection is built on deviations from this table.

| CAN ID | ECU / signal | Period | DLC | Proposed payload layout | Safety criticality |
|---|---|---|---|---|---|
| 0x0A0 | Brake | 20 ms | 8 | B0 = brake pressure (0-100), B1 = brake switch (0/1), B7 = rolling counter (0-255) | Critical |
| 0x0B0 | Steering | 10 ms | 8 | B0-B1 = steering angle (signed, 0.1 deg), B7 = rolling counter | Critical |
| 0x100 | Engine RPM | 10 ms | 8 | B0-B1 = RPM (0-8000), B7 = rolling counter | High |
| 0x200 | Vehicle speed | 20 ms | 8 | B0 = speed km/h (0-250), B7 = rolling counter | High |
| 0x300 | Engine temperature | 100 ms | 8 | B0 = coolant temp (offset -40 C) | Medium |
| 0x600 | Infotainment heartbeat | 100 ms | 8 | B0 = status, B7 = rolling counter | Low |
| 0x7DF | Diagnostic request (OBD-II broadcast) | Event only (not periodic) | 8 | Standard OBD-II / UDS request format | High (when abused) |

Notes:
- Payload layouts are a proposal. Haleem to confirm final IDs, periods and byte layouts (open item O1).
- Normal traffic should include realistic variation: small timing jitter (about +/- 1 ms) and changing signal values (for example, speed ramping up and down), otherwise the model learns an unrealistically clean baseline.
- The rolling counter is optional but recommended. It gives the rules layer a way to catch replay and some masquerade attacks.
- Expected normal bus load: 50 (brake) + 100 (steering) + 100 (RPM) + 50 (speed) + 10 (temp) + 10 (infotainment) = **~320 frames/second**.

---

## 3. Threat model

### 3.1 Method

- **STRIDE** to enumerate threats per component and boundary.
- **Risk score** = Likelihood (1-5) x Impact (1-5). 15-25 = High, 8-14 = Medium, 1-7 = Low.
- **MITRE ATT&CK for ICS** for technique mapping. IDs below are best-effort and must be verified at attack.mitre.org/matrices/ics before the mid review (open item O4).
- Aligned with the risk-assessment approach of **ISO/SAE 21434** (TARA) and the threat categories listed in **UNECE R155** Annex 5 (for example, spoofing of messages, denial of service, unauthorized diagnostic access).

### 3.2 Threat register

| ID | STRIDE | Threat | Entry point | L | I | Risk | ATT&CK for ICS (verify) | Attack in catalogue |
|---|---|---|---|---|---|---|---|---|
| T1 | Spoofing | Compromised infotainment injects fake brake frames on 0x0A0 | TB2 | 4 | 5 | 20 High | T0855 Unauthorized Command Message; T0831 Manipulation of Control | spoof_brake |
| T2 | Spoofing | Masquerade: real ECU silenced, attacker impersonates it with plausible frames | TB2 | 2 | 5 | 10 Medium | T0856 Spoof Reporting Message; T0832 Manipulation of View | masquerade |
| T3 | Tampering | Replay of previously captured legitimate frames at the wrong time | TB2 | 3 | 4 | 12 Medium | T0855 Unauthorized Command Message | replay |
| T4 | Tampering | Fuzzing with random IDs / payloads causing ECU faults or unexpected behaviour | TB2 | 3 | 3 | 9 Medium | T0836 Modify Parameter | fuzz |
| T5 | Repudiation | CAN frames carry no sender identity, so malicious frames cannot be attributed to a node | Whole bus | 5 | 2 | 10 Medium | n/a (design weakness) | Mitigated by IDS logging and suspect-ID attribution |
| T6 | Information disclosure | Passive sniffing of plaintext traffic to reverse-engineer IDs and signals (attack reconnaissance) | TB2, TB3 | 5 | 2 | 10 Medium | T0842 Network Sniffing | Precursor to all attacks (not detectable passively) |
| T7 | Denial of service | High-priority flood (for example, ID 0x000) starves legitimate ECUs of bus access | TB2 | 4 | 5 | 20 High | T0814 Denial of Service; T0813 Denial of Control | flood |
| T8 | Elevation of privilege | Diagnostic abuse via 0x7DF (for example, session control, ECU reset) to gain privileged functions | TB3, TB2 | 2 | 4 | 8 Medium | T0858 Change Operating Mode; T0816 Device Restart/Shutdown | diag_abuse |

### 3.3 Out of scope (documented, not implemented)

- Compromise of the infotainment ECU itself (we assume it is already compromised).
- Attacks on the IDS host or the Unix socket (TB4).
- Physical-layer attacks and bus-off attacks via error frames (bus-off is studied only for the Week 4 bonus).

---

## 4. Attack catalogue and dataset plan

### 4.1 Attack catalogue

All attacks run only on our own vcan0. Chetan implements them; each attack script must log the exact timestamps and frames it injects (used for labeling).

| Attack | Threat | What the attacker does | Bus signature | Best detection layer | Blind spot |
|---|---|---|---|---|---|
| flood | T7 | Sends ID 0x000 (highest priority) as fast as possible | Bus load jumps far above ~320 fps; new dominant ID | Rules (rate threshold, unknown ID) | None significant |
| spoof_brake | T1 | Injects 0x0A0 frames with brake pressure set by attacker, alongside the real brake ECU | 0x0A0 rate roughly doubles; inter-arrival times become irregular; payload values conflict with real ones | Statistics (per-ID rate, inter-arrival variance) + Isolation Forest | Low-rate injection (one frame now and then) is hard to see |
| replay | T3 | Re-sends a captured recording of legitimate frames | Valid IDs and valid payloads; only timing and context are wrong (for example, duplicate rolling counters) | Statistics (rate per ID) + rules (counter check, if implemented) | Hardest: without a counter or timestamp in the payload, replayed frames look normal |
| fuzz | T4 | Sends random IDs and/or random payloads | Unknown IDs; high payload entropy; DLC mismatches | Rules (unknown ID, DLC check) + Isolation Forest (entropy) | Fuzzing restricted to valid IDs with plausible payloads |
| masquerade | T2 | Silences the real ECU, then transmits its ID at the normal period with plausible payloads | Brief gap in the ID's traffic, then normal-looking traffic resumes | Statistics (gap / timing phase shift) + Isolation Forest | Hardest: after takeover, rate and timing match the baseline |
| diag_abuse | T8 | Sends diagnostic requests on 0x7DF (for example, session change, ECU reset) while driving | Diagnostic ID appears during normal operation; burst of requests | Rules (0x7DF outside an allowed state, request rate) | Legitimate workshop diagnostics look the same |

### 4.2 Detection approach (layered)

| Layer | What it checks | Strength |
|---|---|---|
| L1 Rules | Unknown IDs, DLC mismatch, per-ID rate above threshold, diagnostic ID while driving, rolling-counter errors | Fast, explainable, near-zero false positives for obvious attacks |
| L2 Statistics | Per-ID inter-arrival time mean and variance vs. baseline, gaps in periodic IDs | Catches timing anomalies (spoofing, masquerade gap) |
| L3 Isolation Forest | Window features: per-ID message rate, inter-arrival variance, payload entropy, ID distribution | Catches combined or subtle anomalies the first two layers miss |

Each alert records which layer fired, so the team can show which layer catches which attack.

### 4.3 Evaluation metrics (per attack)

| Metric | Meaning | Target |
|---|---|---|
| Precision | Of all alerts, how many were real attacks | >= 0.90 |
| Recall | Of all attack windows, how many were detected | >= 0.90 for flood, spoof_brake, fuzz; report honestly for replay and masquerade |
| Time-to-detect | Time from first malicious frame to first alert | < 1 second |
| False positive rate on normal runs | Alerts during attack-free traffic | As close to 0 as possible |

### 4.4 Dataset plan

| Dataset | Runs | Duration per run | Total | Purpose |
|---|---|---|---|---|
| Normal traffic | 3 | 10 min | 30 min | Training baseline (Isolation Forest trains on normal only) |
| flood | 3 | 2 min | 6 min | Testing |
| spoof_brake | 3 | 2 min | 6 min | Testing |
| replay | 3 | 2 min | 6 min | Testing |
| fuzz | 3 | 2 min | 6 min | Testing |
| masquerade | 3 | 2 min | 6 min | Testing |
| diag_abuse | 3 | 2 min | 6 min | Testing (if in scope, open item O2) |

Rules:
- Each attack run starts with about 30 seconds of normal traffic before the attack begins, so time-to-detect can be measured.
- File naming: `data/<label>_run<N>_<MMDD>.csv`, for example `normal_run1_1010.csv`, `flood_run2_1013.csv`.
- Labeling: frames are labeled `normal` by default; frames that match the attacker's injection log (timestamp + ID + payload) are labeled with the attack name.
- Large CSV files are not committed to GitHub. Only small samples go in `data/`; full datasets are shared separately.

---

## 5. Data schemas

These are interface contracts between team members. Changes must be agreed by the whole team.

### 5.1 CSV (training and test data) - CSV logger -> ML engine

| Column | Type | Format | Example |
|---|---|---|---|
| timestamp | float | Unix time in seconds, microsecond precision | 1791300000.123456 |
| can_id | string | Hex with 0x prefix, uppercase, 3 digits | 0x0A0 |
| dlc | int | 0-8 | 8 |
| data_hex | string | Hex bytes, uppercase, no spaces (2 x DLC characters) | 3201000000000017 |
| label | string | normal, flood, spoof_brake, replay, fuzz, masquerade, diag_abuse | normal |

Example:

```
timestamp,can_id,dlc,data_hex,label
1791300000.123456,0x0A0,8,3201000000000017,normal
1791300000.133502,0x0B0,8,00FA000000000042,normal
1791300000.140011,0x000,8,0000000000000000,flood
```

### 5.2 Socket message (live) - C sniffer -> ML engine

One JSON object per frame, one per line (newline-delimited JSON) over a Unix domain socket.

- Socket path: `/tmp/can_sentinel.sock` (to confirm with Chetan)
- Same fields as the CSV, without `label`

```json
{"timestamp": 1791300000.123456, "can_id": "0x0A0", "dlc": 8, "data_hex": "3201000000000017"}
```

### 5.3 Alert JSON - ML engine -> dashboard

| Field | Type | Values / example | Meaning |
|---|---|---|---|
| timestamp | float | 1791300042.501223 | Time the alert was raised |
| attack_type | string | flood, spoof_brake, replay, fuzz, masquerade, diag_abuse, unknown_anomaly | Best guess of the attack |
| suspect_id | string | "0x0A0" | CAN ID most associated with the anomaly |
| confidence | float | 0.0 - 1.0 | Detection confidence |
| severity | string | low, medium, high, critical | From the threat register and affected system |
| affected_system | string | brake, steering, engine, speed, temperature, infotainment, diagnostics, bus | Used by the car diagram on the dashboard |
| detection_layer | string | rules, statistics, isolation_forest | Which layer fired |
| technique | string | "T0855" | MITRE ATT&CK for ICS ID (verified list) |

Example:

```json
{"timestamp": 1791300042.501223, "attack_type": "spoof_brake", "suspect_id": "0x0A0", "confidence": 0.94, "severity": "critical", "affected_system": "brake", "detection_layer": "statistics", "technique": "T0855"}
```

Severity guide: brake or steering = critical; RPM, speed, diagnostics or bus-wide DoS = high; temperature = medium; infotainment = low.

---

## 6. Week 1 checklist and open items

### 6.1 Week 1 checklist

| # | Task | Owner | Status |
|---|---|---|---|
| 1 | GitHub repo, folder structure, README, branches | Abinaya | Done |
| 2 | Invite collaborators and confirm everyone has cloned the repo | Abinaya / all | In progress |
| 3 | Week 1 design document (this file) | Abinaya | Draft done, team review pending |
| 4 | Linux environment with vcan0 working on each laptop | All (Haleem leads) | To do |
| 5 | ECU simulators producing the baseline traffic in Section 2 | Haleem | To do |
| 6 | CSV logger writing the schema in Section 5.1 | Sadhamail | To do |
| 7 | First normal-traffic CSV committed as a small sample | Sadhamail + Haleem | To do |
| 8 | Attacker script skeleton (at least flood) | Chetan | To do |
| 9 | Kickoff call: walk through this document and agree on schemas | All | To do |

### 6.2 Open items

| ID | Question | Owner | Decide by |
|---|---|---|---|
| O1 | Confirm final ECU IDs, periods and payload layouts (Section 2), including the rolling counter | Haleem + Abinaya | Kickoff call |
| O2 | Is diag_abuse in scope, or kept as stretch goal? | Team | Kickoff call |
| O3 | Who hosts vcan0, and how: WSL2 (check `sudo modprobe vcan` works) or an Ubuntu VM in VirtualBox | Haleem | Kickoff call |
| O4 | Verify all MITRE ATT&CK for ICS technique IDs at attack.mitre.org | Abinaya | Before mid review |
| O5 | Confirm Unix socket path and message format (Section 5.2) | Chetan + Abinaya | End of Week 2 |
| O6 | Where to share full datasets that are too large for GitHub (for example, Google Drive) | Sadhamail | End of Week 1 |

---

## Revision history

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | Oct 6, 2026 | Abinaya Francisca EP | First draft |
