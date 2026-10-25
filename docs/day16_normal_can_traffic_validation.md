# Day 16 — Normal CAN Traffic and Validation

## Objective
Validate normal synthetic CAN traffic on the local virtual CAN interface and record the baseline traffic observations for CAN-Sentinel testing.

## Test Environment
- Interface: `vcan0`
- Traffic source: Temporary synthetic ECU simulator
- Capture tool: `candump`
- Scope: Local virtual CAN interface only

## Observed CAN IDs
The traffic capture showed frames from these six expected CAN IDs:

- `0x0A0`
- `0x0B0`
- `0x100`
- `0x200`
- `0x300`
- `0x600`

## Traffic Rate Measurement
Capture command:

`timeout 3s sh -c 'candump -L vcan0 > /tmp/can-rate-test.log'`

Frame count:

`959`

Approximate observed rate:

`959 / 3 ≈ 320 frames/second`

This is a short-duration measurement; timing jitter and capture overhead may affect the observed rate.

## Validation Notes
- Synthetic CAN frames were observed on `vcan0`.
- The six expected CAN IDs appeared in the capture.
- The observed short-term frame rate was approximately 320 frames/second.
- Live ML detector alert behavior still requires validation with the detector running and connected to the sniffer.

## Safety
All tests were performed on the local virtual CAN interface `vcan0`. No physical vehicle or hardware CAN bus was involved.

## Next Steps
- Confirm the C sniffer remains connected to the ML detector.
- Run the detector while normal synthetic traffic is active.
- Compare alert counts before and after a timed test.
- Investigate any false-positive alerts before treating the baseline as validated.

## Conclusion
A short capture confirmed synthetic CAN traffic across six expected CAN IDs at approximately 320 frames/second. End-to-end ML detection validation remains pending.
