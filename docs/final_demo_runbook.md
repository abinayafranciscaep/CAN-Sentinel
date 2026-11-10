# CAN-Sentinel: Final Review Demo Runbook

Author: Abinaya Francisca EP (Team Lead)
Date: Nov 11, 2026 (draft; rehearse and update before the review)

Step-by-step plan for the live demo at the final review. Everything runs on one
Linux machine (Kali VM or Ubuntu) with vcan0. Commands run from the repository root
unless a folder is named. Items marked **[CONFIRM]** need the owner's exact command.

## 1. Before the call (30 minutes earlier)

| Step | Command / action | Who |
|---|---|---|
| Pull the latest code of every branch into the demo machine | `git fetch origin`, then update each worktree (see the Kali test guide) | Demo machine owner |
| Bring up vcan0 | `sudo modprobe vcan`; `sudo ip link add dev vcan0 type vcan`; `sudo ip link set up vcan0` | Demo machine owner |
| Check the ML engine | `python -m pytest ml_engine -q` (all tests pass) | Abinaya |
| Train on the official normal runs | `python ml_engine/retrain.py --train <run1> <run2> --test <run3> --report docs/retrain_report.md` | Abinaya |
| Delete the old alerts file | `rm -f alerts.jsonl` | Abinaya |
| Open the terminals below, large font (Ctrl + Shift + +) | | All |
| Keep backup screenshots and the demo video ready | | All |

## 2. Terminals (start in this order)

| # | Purpose | Command | Owner |
|---|---|---|---|
| 1 | ECU simulator | `./ecu_sim/ecu_simulator` | Haleem |
| 2 | Sniffer (socket server) | **[CONFIRM]** Chetan's run command | Chetan |
| 3 | ML live detector | `python ml_engine/live_detector.py --alerts alerts.jsonl` | Abinaya |
| 4 | Dashboard | **[CONFIRM]** Sadhamail's run command (reads `alerts.jsonl`) | Sadhamail |
| 5 | Attacks | Chetan's attacker script, or the `cansend` lines below | Chetan |

The live detector waits for the sniffer if it starts first, and reconnects if the
sniffer restarts.

## 3. Demo script (about 8 minutes)

| Time | Show | Say (short) | Who |
|---|---|---|---|
| 0:00 | Dashboard, normal traffic | Six ECUs at about 320 frames per second; no alerts | Abinaya |
| 0:45 | Terminal 1 and `candump vcan0` | How the simulator builds frames; byte 7 rolling counter | Haleem |
| 1:45 | Terminal 2 | Sniffer reads vcan0 and streams JSON over the Unix socket | Chetan |
| 2:30 | Attack 1: diagnostic abuse | Run the lines below; alert appears in terminal 3 and on the dashboard | Chetan, Abinaya |
| 3:30 | Attack 2: brake spoofing | Attacker script, spoof mode **[CONFIRM]**; critical brake alert | Chetan, Abinaya |
| 4:30 | Attack 3: flood | Attacker script, flood mode **[CONFIRM]**; high alert, bus rate jumps | Chetan, Abinaya |
| 5:30 | Dashboard alerts tab | Severity, suspect ID, ATT&CK technique, threat level | Sadhamail |
| 6:30 | Incident log | `python ml_engine/alert_summary.py alerts.jsonl` | Abinaya |
| 7:15 | Results table | `docs/final_report_draft.md` Section 7 | Abinaya |

Diagnostic abuse without the attacker script (safe, virtual bus only):

```
for i in 1 2 3 4 5; do cansend vcan0 7DF#0211010000000000; sleep 0.3; done
```

## 4. If something fails

| Problem | Fix during the demo |
|---|---|
| vcan0 missing | Run the three vcan0 lines again |
| Detector says "Sniffer not ready" | Start the sniffer; the detector connects by itself |
| Dashboard cannot open the socket | `sudo chmod 666 /tmp/can_sentinel.sock` (until the sniffer sets permissions itself) |
| Live attack does not run | Show the same attack from a recording: `python ml_engine/live_detector.py --replay data/<attack run>.csv --alerts alerts.jsonl` |
| Anything else | Switch to the recorded demo video and screenshots, and say so |

## 5. Honesty points to state

- Everything runs on a virtual CAN bus; no real vehicle.
- Name which results come from simulated data and which from the team's recordings.
- Known limits: an attacker who copies valid counters; workshop diagnostics look like
  diagnostic abuse; the socket between sniffer and engine is assumed trusted.

## 6. Rehearsal checklist

- [ ] Full run-through on the demo machine, timed
- [ ] Each owner has confirmed their command in Section 2
- [ ] Alerts from the live detector appear on the dashboard (not the sample file)
- [ ] Backup video and screenshots saved
- [ ] Each member ready for viva questions on their own module
