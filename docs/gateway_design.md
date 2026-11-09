# CAN-Sentinel: Security Gateway Design (Detect -> Block)

Author: Abinaya Francisca EP (Team Lead)
Date: Nov 9, 2026 | Status: agreed design, implementation in progress

## 1. Goal

Go one step beyond detection: when CAN-Sentinel confirms an attack, a security
gateway stops the attack frames from reaching the safety-critical part of the
vehicle, while real ECU traffic keeps flowing where possible. This follows the
central-gateway architecture of modern vehicles and the "contain" step of
`docs/incident_response_playbook.md`. Lab use only, on virtual CAN interfaces.

## 2. Topology

```
 ECU simulator  attacker   sniffer --socket--> ML live detector
       \           |          /                     |
        +------- vcan0 ------+                      | control socket
          (vehicle bus)                             | /tmp/can_sentinel_gw.sock
                 |                                  |
          [ security gateway ] <--------------------+
                 |  forwards vcan0 -> vcan1 only
               vcan1  (protected safety domain)
                 |
          brake / steering receiver (candump vcan1, or receiver program)
```

- **vcan0, vehicle bus:** unchanged from today. The simulator, the attacker and the
  sniffer all stay here, and the detector monitors it.
- **vcan1, protected bus:** only frames the gateway allows reach it.
- One direction only (vcan0 -> vcan1), so no frame loops.

## 3. Gateway filtering

| Step | Rule | Stops |
|---|---|---|
| 1. Allowlist (always on) | Forward only 0x0A0, 0x0B0, 0x100, 0x200, 0x300, 0x600, 0x7DF | flood (0x000), fuzzing (random IDs) |
| 2. Quarantine "counter" mode (on alert) | Forward a frame of the ID only if its byte-7 counter continues the real sequence at the real timing (step +1 after at least half a period; +2 or +3 only if that many periods passed) | spoof_brake, replay: fake frames dropped, real brake frames still pass |
| 3. Quarantine "drop" mode (on alert) | Drop every frame of the ID | masquerade (real ECU is gone), diag_abuse (0x7DF) |

The gateway tracks each ID's real counter sequence all the time, so when a
quarantine starts it already knows which frames are real, even if fake frames got
through before the alert. After 5 periods with no valid frame it resynchronises on
the next frame. A quarantine lasts 30 s and is renewed by every new alert.

## 4. Message formats

All messages are one JSON object per line (NDJSON), UTF-8, over the Unix domain
socket `/tmp/can_sentinel_gw.sock`. The **gateway is the server**; the detector and
the analyst tool are clients. The gateway creates the socket with permissions 0666,
so no `sudo chmod` is needed.

### 4.1 Detector -> gateway: quarantine

```json
{"type":"quarantine","can_id":"0x0A0","mode":"counter","duration_s":30,"reason":"spoof_brake on 0x0A0 (rules, confidence 0.90, T0855)","alert":{"timestamp":1794230100.799,"attack_type":"spoof_brake","suspect_id":"0x0A0","confidence":0.9,"severity":"critical","affected_system":"brake","detection_layer":"rules","technique":"T0855"}}
```

| Field | Type | Values |
|---|---|---|
| `type` | string | `quarantine` |
| `can_id` | string | CAN ID as `0x` + 3 hex digits |
| `mode` | string | `counter` or `drop` |
| `duration_s` | number | seconds; default 30 |
| `reason` | string | human-readable cause, shown in logs and on the dashboard |
| `alert` | object | the alert that caused it (alert schema, design doc Section 5.3) |

### 4.2 Analyst -> gateway: release and status

```json
{"type":"release","can_id":"0x0B0"}
{"type":"status"}
```

### 4.3 Gateway -> client: replies (one per command)

```json
{"type":"ack","ok":true,"can_id":"0x0A0","mode":"counter","until":1794230130.8,"renewed":false}
{"type":"ack","ok":true,"can_id":"0x0B0","released":true}
{"type":"ack","ok":false,"error":"unknown mode block"}
{"type":"status","forwarded":51234,"dropped":{"not_allowed":20000,"quarantine_counter":475},"quarantined":[{"can_id":"0x0A0","mode":"counter","seconds_left":21.4}]}
```

### 4.4 Gateway event log (for the dashboard)

The gateway appends events to `gateway_events.jsonl` (one JSON object per line),
which the dashboard can read the same way as `alerts.jsonl`:

```json
{"timestamp":1794230100.799,"event":"quarantine_start","can_id":"0x0A0","mode":"counter","duration_s":30,"reason":"spoof_brake on 0x0A0 (rules, confidence 0.90, T0855)"}
{"timestamp":1794230130.801,"event":"quarantine_end","can_id":"0x0A0","why":"expired"}
```

`why` is `expired` or `released`.

## 5. Blocking policy (detector side, `ml_engine/gateway_client.py`)

Only confident, explainable alerts trigger blocking: detection layer `rules`,
confidence at least 0.7, severity high or critical. A model-only anomaly never
blocks a real ECU.

| Alert | Gateway action |
|---|---|
| spoof_brake, replay | quarantine the suspect ID, `counter` mode |
| masquerade | quarantine the suspect ID, `drop` mode |
| diag_abuse | quarantine 0x7DF, `drop` mode |
| flood, fuzz on an unknown ID | none (the allowlist already drops it) |
| flood, fuzz on a baseline ID | quarantine that ID, `drop` mode |
| unknown_anomaly, or low severity (for example infotainment) | none; logged for a person to review |

## 6. Setup and run (Kali or Ubuntu)

```
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan && sudo ip link set up vcan0
sudo ip link add dev vcan1 type vcan && sudo ip link set up vcan1
```

| Terminal | Command |
|---|---|
| 1 Simulator | `./ecu_sim/ecu_simulator` (on vcan0, unchanged) |
| 2 Sniffer | sniffer on vcan0 (unchanged) |
| 3 Gateway | `python3 gateway/can_gateway.py --src vcan0 --dst vcan1` |
| 4 Detector | `python3 ml_engine/live_detector.py --alerts alerts.jsonl --gateway` |
| 5 Protected bus | `candump vcan1` (or the brake receiver program) |
| 6 Attack | attacker script on vcan0 |

Analyst control: `python3 ml_engine/gateway_client.py status` and
`python3 ml_engine/gateway_client.py release 0x0B0`.

## 7. Demo moment

Run `candump vcan0` and `candump vcan1 | grep " 0A0 "` side by side. Start brake
spoofing: fake 0x0A0 frames appear on vcan0; the detector raises the alert and prints
`GATEWAY: quarantined 0x0A0 (counter mode, 30 s)`; from then on vcan1 shows only the
real brake frames with a continuous counter.

## 8. Offline check of the gateway logic (simulated data)

The gateway's decision code was run over the synthetic six-attack file, starting each
quarantine when the detector first alerted:

| Attack | Mode | Attack frames dropped | Real frames of that ID passed |
|---|---|---|---|
| spoof_brake | counter | 475 / 475 | 500 / 500 |
| replay | counter | 475 / 475 | 500 / 500 |
| masquerade | drop | 970 / 970 | n/a (real steering ECU silenced by the attack; 19 real frames just after the attack also dropped) |
| diag_abuse | drop | 19 / 19 | n/a |
| flood, fuzz | allowlist | all (unknown IDs) | n/a |
| low-rate spoof (2 frames/s) | counter | 17 / 18 | 999 / 1000 |

This is a logic check on simulated data, not yet a live test on vcan0/vcan1.

## 9. Limitations

- Drop mode also stops the real ECU's frames for that ID; the receiver must fall back
  to a safe state (for example, a brake receiver treating missing 0x0A0 frames as a
  fault). Release is manual or after 30 s without new alerts.
- An attacker who sends the correct next counter at exactly the right time can still
  pass in counter mode (very rarely by chance: 1 of 18 frames in the low-rate test).
- Frames that pass before the first alert (up to about 0.5 s) are not blocked.
- The control socket is local and unauthenticated (same trust assumption as TB4).

## 10. Ownership

| Part | Owner | Branch |
|---|---|---|
| Gateway program (`gateway/`) and vcan1 setup; reference implementation provided | Chetan (Member 2) | member-2 |
| Brake receiver on vcan1 with safe-state fallback (optional) | Haleem (Member 1) | member-1 |
| Gateway status and quarantine events on the dashboard | Sadhamail (Member 3) | member-3 |
| Blocking policy, detector -> gateway link, this design | Abinaya (Team Lead) | lead |
