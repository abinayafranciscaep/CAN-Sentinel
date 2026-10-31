# CAN-Sentinel: Week 3 Live Integration Test

Author: Abinaya Francisca EP (Team Lead)
Date: Nov 1, 2026 (test run by Member 3 on Oct 30, 2026; reviewed by the team lead)

## Purpose

Check that the live chain works end to end on vcan0:
ECU simulator (Member 1) -> C sniffer over `/tmp/can_sentinel.sock` (Member 2) ->
PyQt dashboard (Member 3), with the ML live detector (team lead) as the next consumer.

## Setup

| Item | Value |
|---|---|
| Environment | Ubuntu 24.04 on WSL2 (Member 3's laptop) |
| Bus | vcan0 |
| Socket | `/tmp/can_sentinel.sock` (Unix domain socket, NDJSON, design Section 5.2) |
| Evidence | Screen recording, 26 s, Oct 30, 2026 |

## Results

| Check | Result | Evidence |
|---|---|---|
| Simulator sends the baseline | Pass | Telemetry: 319.9 frames/s steady over 6 minutes |
| Sniffer reads vcan0 | Pass | Sniffer output shows 0x0A0, 0x0B0, 0x100, 0x200, 0x300, 0x600, DLC 8 |
| Dashboard receives live frames over the socket | Pass | Timestamps 1793382184 to 1793382209, increasing in real time; rows marked RECEIVED |
| Timestamps in order | Pass | Every row newer than the one below; no backward steps seen |
| Rolling counter range | Pass: 0-255 | Counters such as 0xDD, 0xE0, 0xBF in the sniffer output; confirmed by Member 1 (simulator `uint8_t`, DBC `[0|255]`, `test_payloads.c`) |
| Labels honest while live | Fail | Dashboard still shows "LAST 5 ROWS OF normal_run2_1025.csv", "NOT LIVE", "NOT CONNECTED TO LIVE CAN" and "(mock-up)" while live frames arrive |
| Socket permissions | Workaround | Socket created by root; `sudo chmod 666` was needed by hand |
| Injected frame shown (0x7DF) | Not yet tested | |
| Simulator stopped is shown | Not yet tested | |
| Detector and dashboard connected at the same time | Not yet tested | Needs the sniffer to accept two clients |

## Update (Oct 31, 2026): dashboard re-test by Member 3

Evidence: second screen recording (about 40 s, Oct 31, 2026), reviewed by the team lead.

| Check | Result | Evidence |
|---|---|---|
| Frames/s card from live frames | Pass | Changes between 309 and 327 during the recording |
| Frames/s graph from live frames | Pass | "Live capture", current and average values update |
| Traffic tables show live frames only | Pass | Overview and CAN Traffic tabs: timestamps 1793463285 to 1793463323, increasing; counters step by 1 |
| CAN ID traffic share from live frames | Pass | 0x100 and 0x0B0 about 31% each, 0x0A0 and 0x200 about 16%, 0x300 and 0x600 about 3%; matches the 100/100/50/50/10/10 frames/s baseline |
| UI refresh time updates | Pass | 16:14:45 to 16:15:23 |
| Frames/s drops to 0 when traffic stops | Reported by Member 3; not shown in the recording | |
| Labels honest while live | Fail (partly fixed) | Still shown while live: window title "(mock-up)", footer "NOT CONNECTED TO LIVE CAN", "Recorded file: normal_run2_1025.csv ... NOT LIVE", and on the CAN Traffic tab "Recorded CSV rows only - this view does not connect to a live CAN bus" |

Still open: live labels, socket permissions (manual `chmod 666`), two clients on the socket.

## Decisions

- Rolling counter: 0-255, wrapping 255 to 0, for all six ECUs (Oct 30). The ML
  engine's counter rules (R7, R8) and `counter_check.py` use this range.

## Open items

| Item | Owner |
|---|---|
| Update the remaining labels and window title in live mode (cards and graph now use live data) | Member 3 |
| Sniffer sets socket permissions itself; accepts two clients (detector + dashboard) | Member 2 |
| Re-record the official normal dataset (three 10-minute runs) | Member 1 + Member 3 |
| Labelled real attack recordings | Member 2 + Member 3 |
| Run the remaining checks with the live detector connected | Team lead with Member 2 + Member 3 |
| Dashboard reads `alerts.jsonl` from the live detector instead of the sample alert | Member 3 |
