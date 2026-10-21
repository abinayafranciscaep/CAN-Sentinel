# CAN-Sentinel: Incident Response Playbook

Author: Abinaya Francisca EP (Team Lead, Security Lead)
Status: Draft v1, for team review

This playbook says what an analyst does when CAN-Sentinel raises an alert. It
follows the usual incident response cycle (detect, triage, contain, recover,
learn), adapted to an in-vehicle network where the safest response is often to
degrade a feature rather than stop the vehicle.

Scope: our lab environment only (virtual bus vcan0). In a real vehicle the
containment steps would be carried out by the vehicle's gateway or safety
controller, not by a person.

## 1. Severity and response time

| Severity | Affected system | Target response | Example |
|---|---|---|---|
| Critical | Brake, steering | Immediate, automatic containment | Spoofed brake frames on 0x0A0 |
| High | Engine, speed, diagnostics, whole bus | Within seconds | Flood of ID 0x000, diagnostic abuse |
| Medium | Temperature | Within minutes | Spoofed coolant temperature |
| Low | Infotainment | Review at next check | Infotainment heartbeat anomaly |

## 2. Common first steps (every alert)

1. Read the alert: attack_type, suspect_id, severity, detection_layer, technique.
2. Check whether it repeats. One isolated `unknown_anomaly` from the Isolation Forest is weaker evidence than repeated alerts from the rules layer.
3. Save evidence: keep the alerts file and the CSV recording around the alert time (at least 30 seconds before and after).
4. Note the time, the alert and the action taken in the incident log (Section 5).

## 3. Playbook per attack

### 3.1 flood (Denial of Service, T0814)

| Step | Action |
|---|---|
| Recognise | Bus rate far above the normal ~320 frames/s; dominant unknown ID such as 0x000 |
| Triage | Confirm with candump: one ID dominating traffic |
| Contain | Isolate the sending node (in a vehicle: gateway blocks the source segment). Lab: stop the attacker process |
| Recover | Confirm the bus returns to ~320 frames/s and all six periodic IDs resume |
| Learn | Record peak rate and time-to-detect |

### 3.2 spoof_brake (Spoofing, T0855)

| Step | Action |
|---|---|
| Recognise | 0x0A0 at about 2x its normal rate; conflicting brake values |
| Triage | Compare payloads: two different brake pressure values alternating means two senders |
| Contain | Critical: treat brake commands as untrusted, fall back to the driver's direct input; isolate the infotainment segment (most likely source per threat T1) |
| Recover | Rate of 0x0A0 back to 50 frames/s with one consistent value stream |
| Learn | Which ECU was compromised and how it was reached (entry point TB1) |

### 3.3 replay (Tampering, T0855)

| Step | Action |
|---|---|
| Recognise | Valid IDs and payloads at a higher rate; repeated rolling counter values if counters are used |
| Triage | Look for identical payload sequences seen earlier in the recording |
| Contain | Same as spoofing for the affected ID |
| Recover | Counter sequence and rate back to normal |
| Learn | Replay is a known blind spot without counters or message authentication; note as a limitation |

### 3.4 fuzz (Tampering, T0836)

| Step | Action |
|---|---|
| Recognise | Many unknown IDs, high payload entropy, DLC mismatches |
| Triage | Check whether any ECU stopped sending (crash caused by malformed input) |
| Contain | Isolate the source; restart any ECU that stopped responding |
| Recover | All six periodic IDs present at normal rates; no unknown IDs |
| Learn | Which IDs or payloads caused ECU faults |

### 3.5 masquerade (Spoofing, T0856)

| Step | Action |
|---|---|
| Recognise | A gap in a periodic ID, then traffic resumes, possibly at a changed timing phase or rate |
| Triage | Check whether the real ECU is still alive (heartbeat, other IDs it sends) |
| Contain | Treat that ID's values as untrusted; use redundant sensors where available |
| Recover | Original ECU confirmed sending; timing back to baseline |
| Learn | Masquerade after takeover is the hardest attack to see; record what gave it away |

### 3.6 diag_abuse (Elevation of privilege, T0858)

| Step | Action |
|---|---|
| Recognise | Diagnostic requests on 0x7DF while the vehicle is operating |
| Triage | Was a workshop tool connected? If not, treat as malicious |
| Contain | Block diagnostic sessions while driving (gateway rule) |
| Recover | No further 0x7DF traffic; ECUs back in normal session |
| Learn | Review diagnostic access policy |

### 3.7 unknown_anomaly (Isolation Forest or statistics only)

| Step | Action |
|---|---|
| Recognise | Model flags unusual traffic but no rule names the attack |
| Triage | Check the suspect ID's rate and gaps; look for a matching attack signature |
| Contain | Only if confirmed; otherwise monitor |
| Learn | If it was a false alarm, record it for threshold tuning |

## 4. Escalation

| Situation | Escalate to |
|---|---|
| Critical alert confirmed | Team lead immediately |
| Repeated false alarms | ML engine owner for threshold tuning |
| Detector or sniffer stopped | Member owning that module |

## 5. Incident log template

| Time | Alert (type, ID, severity) | Layer | Confirmed? | Action taken | Result |
|---|---|---|---|---|---|
| | | | | | |
