# CAN-Sentinel: Rolling-Counter Rule (R7), Replay vs Spoofing

Author: Abinaya Francisca EP (Team Lead)
Date: Oct 30, 2026

## Problem (from the Week 2 integration test)

Replay and brake spoofing both double the 0x0A0 frame rate, so the rate rule (R5)
labelled replay as `spoof_brake`. The rolling counter in byte 7 is what tells them apart.

## How R7 works

R7 runs only when R5 has already found an ID sending faster than normal.

1. Read the rolling counter (byte 7) of every frame of that ID in the window.
2. Split the counters into continuous sequences: a frame joins the sequence it
   continues (previous value + 1, wrapping 255 to 0); otherwise it starts a new one.
3. Decide:
   - **Replay**: two or more continuous sequences of at least 5 frames, covering at
     least 80% of the frames. The genuine ECU is one sequence; old frames re-sent with
     their old counters form the second.
   - **Spoof**: anything else. An attacker who does not follow the counter creates
     many short or one-frame sequences.

The counter range is inferred per window (0-15 or 0-255), so the rule works with
either range until the team confirms the final one.

## Results (synthetic six-attack file, same commands as Week 2)

| Check | Week 2 | Now |
|---|---|---|
| Unit tests | 15 passed | 18 passed (3 new counter tests) |
| Alerts on 2 min of normal traffic | 0 | 0 |
| Alerts on the six-attack file (`detect.py`) | 44 | 44 |
| Replay phase (60-70 s) labelled as | spoof_brake | **replay** (5 alerts, T0855) |
| Spoof phase (45-55 s) labelled as | spoof_brake | spoof_brake (unchanged) |
| Time to detect, all six attacks | 0.20-0.99 s | 0.20-0.99 s (unchanged) |

Simulated data; to be repeated on the team's real attack recordings.

## Limitations

- An attacker who forges a correct, continuous counter of their own would look like a
  replay. Separating that case needs a payload check (are the frames copies of
  earlier traffic?), planned after real recordings are available.
- The rule assumes every ECU frame carries the counter in byte 7, as in the design
  document (Section 2).
