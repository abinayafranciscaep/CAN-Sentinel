# CAN-Sentinel dataset log (Member 3)

Evidence trail for every recording. Numbers below were copied from the terminal
output of `bash dashboard/record_normal.sh <run> 600`. CSV files are **not** in
Git; they are on Google Drive.

Schema: `timestamp,can_id,dlc,data_hex,label`

## Normal-traffic recordings

| File | Date | Source | Frames | validate_csv.py | check_baseline.py | Timestamp span | Drive link |
|---|---|---|---|---|---|---|---|
| standin_normal_run1_1010.csv | Oct 10 | **stand-in sender** (not final simulator) | 192,001 | 0 problems | PASS | not measured | on Drive; sharing with team lead unconfirmed |
| normal_run1_1016.csv | Oct 16 | `ecu_sim/ecu_simulator` | 184,716 | 0 problems | PASS | 552.49 s (19 backward steps) | TBD after upload |
| normal_run2_1016.csv | Oct 16 | `ecu_sim/ecu_simulator` | 185,993 | 0 problems | PASS | 554.87 s (18 backward steps) | TBD after upload |
| normal_run3_1016.csv | Oct 16 | `ecu_sim/ecu_simulator` | 185,104 | 0 problems | PASS | 555.00 s (18 backward steps) | TBD after upload |

Total for the three simulator runs: 555,813 frames.

## Mean period per ID (ms), from check_baseline.py

| CAN ID | System | Expected | Run 1 | Run 2 | Run 3 |
|---|---|---|---|---|---|
| 0x0A0 | brake | 20 | 18.89 | 18.87 | 18.93 |
| 0x0B0 | steering | 10 | 9.67 | 9.63 | 9.69 |
| 0x100 | engine RPM | 10 | 9.67 | 9.63 | 9.69 |
| 0x200 | vehicle speed | 20 | 18.88 | 18.87 | 18.94 |
| 0x300 | temperature | 100 | 92.62 | 92.89 | 92.94 |
| 0x600 | infotainment | 100 | 92.62 | 92.89 | 92.95 |

Rolling-counter breaks: 0 for every ID in every run.

## Timing findings (from dashboard/dataset_summary.py, Oct 17)

Measured, from the terminal output:

- The logger was asked for 600 s but the first-to-last timestamp span is only
  552.49 s (run 1), 554.87 s (run 2) and 555.00 s (run 3).
- Timestamps go backwards 19, 18 and 18 times in runs 1, 2 and 3.
- For every ID, frame count x median period is about 599 s, so the traffic
  really lasted about 600 s. Example (run 1, 0x0A0): 29,250 x 20.48 ms = 599 s.
- The median period is slightly LONGER than nominal (20.4-20.5 ms for 20 ms IDs,
  10.4-10.5 ms for 10 ms IDs, 100.3-100.5 ms for 100 ms IDs).
- The mean period used by check_baseline.py is (last - first) / (n - 1), so it
  is shortened by the lost time. Mean / median is about 0.92 for every ID in
  every run, which matches 552.5 / 600.

What this suggests (not yet proven):

- The "periods 3-7% shorter than nominal" result is probably a timestamp
  artifact (the clock stepping backwards), not a simulator that runs fast.
- The simulator itself seems to run slightly slow: each message looks about
  0.45-0.5 ms late (20.48 - 20, 10.47 - 10, 100.45 - 100), and the files hold
  about 308 frames/s instead of 320. A fixed delay per message fits a relative
  sleep in the simulator loop, but the simulator source has not been read.
- The cause of the backward steps is not established. A clock correction in
  WSL2 is a candidate. Step sizes are in the dataset_summary.py output.

Consequences:

- check_baseline.py PASS on timing is misleading for these files.
- Inter-arrival and rate features computed from these timestamps will contain
  the backward steps unless they are handled or the data is re-recorded.

## Limits of these checks

- `validate_csv.py` checks file structure only.
- `check_baseline.py` PASS means the checks implemented there passed. It does
  not prove the traffic is free of anomalies.
- The terminal output shows the simulator path used; it does not by itself
  prove this was the final shared simulator version.

## How to reproduce the numbers

```bash
python3 dashboard/validate_csv.py data/normal_run1_1016.csv
python3 dashboard/check_baseline.py data/normal_run1_1016.csv
python3 dashboard/dataset_summary.py data/normal_run*_1016.csv --duration 600
```