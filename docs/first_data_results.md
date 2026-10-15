# CAN-Sentinel: First Results on Team Data

Author: Abinaya Francisca EP (Team Lead)
Date: Oct 15, 2026
Dataset: standin_normal_run1_1010.csv (Member 3, 10 minutes, stand-in sender, 192,001 frames)

## Purpose

First run of the ML engine on traffic recorded by our own logger, to check that
the feature pipeline works on real logged data and to see the baseline
false-alarm level before the final ECU simulator datasets arrive.

## Commands run (from the repository root)

```
python ml_engine/features.py data/standin_normal_run1_1010.csv data/features_standin_run1.csv
python ml_engine/train_model.py train data/features_standin_run1.csv
python -c "import pandas as pd; print(pd.read_csv('data/standin_normal_run1_1010.csv')['can_id'].value_counts())"
python -c "import pandas as pd; d=pd.read_csv('data/features_standin_run1.csv'); print(len(d), round(d['bus_rate_fps'].mean(),1), round(d['id_0A0_rate_ratio'].mean(),2))"
```

## Results

| Check | Result |
|---|---|
| Frames read | FILL |
| Feature windows created (1 s window, 0.5 s step) | FILL |
| Bus rate per window (expected about 320 fps) | FILL |
| CAN IDs seen (expected 6) | FILL |
| Brake (0x0A0) rate ratio (expected about 1.0) | FILL |
| Model trained without errors | Yes / No |
| Anomaly threshold printed by train_model.py | FILL |

## Observations

- FILL: anything unexpected (missing IDs, uneven rates, errors)

## Limitations

- The data comes from a stand-in sender, not the final ECU simulators, so the
  traffic is more regular than real ECU traffic. The model will be retrained on
  the three 10-minute runs recorded with Member 1's simulator.
- No attack data yet, so detection rates cannot be measured from this run.

## Next steps

- Retrain on normal_run1 and normal_run2 from the final simulator; keep run3 for false-alarm testing.
- Evaluate per attack once Member 2's labeled attack runs are available (see docs/evaluation_plan.md).
