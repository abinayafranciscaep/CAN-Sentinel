# CAN-Sentinel: Threat-to-Detection Coverage

Author: Abinaya Francisca EP (Team Lead)
Date: Nov 5, 2026

Links every threat in the threat register (`docs/week1_design.md`, Section 3.2) to
the detection that covers it, the alert it produces and the evidence so far. This
is the traceability table for the final report.

## Detection rules and layers

| ID | Layer | What it checks | Alert raised |
|---|---|---|---|
| R1 | Rules | Unknown CAN ID; with bus rate above 2x normal, a flood | flood / unknown_anomaly |
| R2 | Rules | 5 or more different unknown IDs in one window | fuzz |
| R3 | Rules | Payload length does not match DLC | fuzz |
| R4 | Rules | Diagnostic request on 0x7DF while driving | diag_abuse |
| R5 | Rules | A baseline ID sending above 1.5x its normal rate | spoof_brake (0x0A0) / unknown_anomaly |
| R6 | Rules | A baseline ID silent for 5 of its periods | masquerade |
| R7 | Rules | Rate too high and the extra frames carry their own valid counter sequence | replay |
| R8 | Rules | Normal rate but the counter is broken and the real ECU's sequence is gone | masquerade |
| S | Statistics | Any of 34 window features outside its normal range (50% margin) | unknown_anomaly |
| IF | Isolation Forest | Unusual combination of window features (2 windows in a row) | unknown_anomaly |

## Coverage of the threat register

| Threat | Attack | ATT&CK for ICS | Detected by | Evidence (simulated data) | Known gap |
|---|---|---|---|---|---|
| T1 Spoofing (fake brake frames) | spoof_brake | T0855, T0831 | R5, then S / IF | Detected in 0.99 s; 5/5 alerts name 0x0A0 | Low-rate injection (a frame now and then) stays under R5 |
| T2 Spoofing (masquerade) | masquerade | T0856, T0832 | R6 at takeover, R8 after | Detected in 0.20 s; 6/6 alerts name 0x0B0 | Attacker copying a valid counter avoids R8 |
| T3 Tampering (replay) | replay | T0855 | R5 + R7 | Detected in 0.99 s; named replay since Oct 30 | Replay of an ID with no counter would look like spoofing |
| T4 Tampering (fuzzing) | fuzz | T0836 | R2, R3, S, IF | Detected in 0.50 s | Fuzzing only valid IDs with plausible payloads |
| T5 Repudiation | (design weakness) | n/a | Logging and suspect-ID attribution in every alert | Every alert names a suspect ID or "bus" | CAN has no sender identity; attribution is by ID, not by node |
| T6 Information disclosure | reconnaissance | T0842 | Not detectable (passive) | n/a | Sniffing sends nothing on the bus |
| T7 Denial of service | flood | T0814, T0813 | R1, S | Detected in 0.50 s; alerts name 0x000 | A flood on a baseline ID would be reported by R5 as a rate attack |
| T8 Elevation of privilege | diag_abuse | T0858, T0816 | R4 | Detected in 0.50 s; alerts name 0x7DF | Real workshop diagnostics look the same |

Current numbers (`ml_engine/evaluate_alerts.py` on the synthetic six-attack file):
6/6 attacks detected, all within 1 second, 0 false alarms on normal traffic, precision 1.0.
These are simulated-data results; the final table is filled in from the team's real
labelled recordings.

## Severity in alerts

| Affected system | Severity |
|---|---|
| Brake, steering | critical |
| Engine, speed, diagnostics, whole bus | high |
| Temperature | medium |
| Infotainment | low |
