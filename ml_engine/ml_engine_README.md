# ML Engine

Owner: Abinaya Francisca EP (Team Lead)

The ML engine turns raw CAN traffic into features, learns what normal traffic
looks like, and flags windows that look like an attack.

## Detection layers

| Layer | What it checks | Good at |
|---|---|---|
| Statistics | Any feature far outside its normal range (with a 50% margin) | Flood, fuzz, obvious rate changes |
| Isolation Forest | Unusual combinations of features | Spoofing and subtler timing changes |
| Rules (Week 3) | Unknown IDs, DLC mismatch, diagnostic ID while driving | Fast, explainable alerts |

## Files

| File | Purpose |
|---|---|
| features.py | CAN CSV -> one feature row per sliding time window |
| train_model.py | Train on normal windows; evaluate per attack |
| requirements.txt | Python packages needed |

## Setup

```
pip install -r ml_engine/requirements.txt
```

Run all commands from the repository root (the CAN-Sentinel folder).

## How to run

1. Turn raw traffic into features (default: 1 second windows, 0.5 second step):

```
python ml_engine/features.py data/normal_run1.csv data/features_normal_run1.csv
python ml_engine/features.py data/flood_run1.csv data/features_flood_run1.csv
```

2. Train on normal traffic only:

```
python ml_engine/train_model.py train data/features_normal_run1.csv data/features_normal_run2.csv
```

This saves `ml_engine/isolation_forest.joblib`.

3. Evaluate on labelled attack traffic:

```
python ml_engine/train_model.py evaluate data/features_flood_run1.csv
```

The output shows precision, false positive rate, recall per attack, and how
many windows each layer caught.

## Input format

The CSV from the logger (agreed in docs/week1_design.md, Section 5.1):

```
timestamp,can_id,dlc,data_hex,label
1791300000.123456,0x0A0,8,3201000000000017,normal
```

## Features per window

| Feature | Why it matters |
|---|---|
| bus_rate_fps, frame_count | Flood raises total traffic |
| unknown_id_count, unique_ids | Fuzz and flood use IDs outside the baseline |
| id_entropy | Distribution of IDs shifts during floods |
| payload_entropy_mean / max | Random fuzz payloads have high entropy |
| dlc_mismatch_count | Malformed frames |
| diag_frame_count | Diagnostic abuse on 0x7DF |
| id_XXX_rate_ratio | 1.0 is normal; about 2.0 means an ID is being spoofed |
| id_XXX_iat_mean / iat_std | Timing irregularity from injected frames |
| id_XXX_max_gap_ratio | Gaps in a periodic ID (masquerade) |

## Status

| Item | Status |
|---|---|
| Feature extraction | Done, tested on simulated traffic |
| Isolation Forest + statistics layer | Done, tested on simulated traffic |
| Evaluation on real team data | Waiting for first logger CSV |
| Rules layer and live alerts | Week 3 |
