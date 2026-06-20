# AddressForge 20w Data Processing and Training Execution Summary - 2026-05-15 Week 1

## Document Info
- Document Type: Execution Summary / Baseline Result
- Related Plan: [addressforge-20w-data-processing-training-execution-plan-2026-05-15.md](../plans/addressforge-20w-data-processing-training-execution-plan-2026-05-15.md)
- Status: Completed
- Scope: Week 1 - dataset audit and baseline freeze

## 1. Overall Conclusion
Week 1 is complete.

This week delivered two core actions:
1. a live baseline audit of the existing 200k dataset
2. a new frozen snapshot for the current human gold set, establishing a stable holdout baseline

## 2. Completed Work
### 2.1 Live Dataset Baseline Audit
Live MySQL queries show the current `default` workspace state as:
- `raw_address_record`: `221,873`
- `address_cleaning_result`: `221,873`
- human-accepted `gold_label`: `1,406`
- `active_learning_queue` total: `1,850`
- `active_learning_queue` queued: `417`

Cleaning distribution:
- `accept = 212,950`
- `review = 8,911`
- `enrich = 12`

Main review reasons:
- `Parser confidence is moderate; review is safer.`: `7,591`
- `Address is incomplete and needs manual confirmation.`: `1,286`
- `Commercial-looking address parsed well, but unit details may need confirmation.`: `22`
- `Reference matched a commercial address; suite or unit details may be missing.`: `12`

### 2.2 Top Batch Audit
The highest review pressure currently comes from the `third_party` source. The top three batches are:
- `HASUB-202605112209`
- `HASUB-202605072129`
- `HASUB-202605092211`

These batches have review rates in the rough `28% ~ 31%` range and are strong candidates for Week 2 backlog digestion.

### 2.3 Holdout Freeze
A new gold freeze has been executed:
- `gold_set_version = gold_v20260515`
- `split_version = v20260515`
- `snapshot_id = 26`
- `sample_count = 1,406`
- `train_count = 1,145`
- `eval_count = 129`
- `test_count = 132`

This snapshot is now the fixed baseline for the next stage of 20k/200k data training work and should not drift with backlog processing.

## 3. Validation Results
### 3.1 Data Validation
The baseline matches the current operational pattern:
- the dominant review bucket is moderate-confidence residential traffic
- backlog concentration is localized to a few batches
- the gold set is large enough to support a new holdout freeze

### 3.2 Training Validation
`freeze_gold_set()` completed successfully and the new snapshot is persisted for downstream training.

## 4. Remaining Work
Week 2 starts review backlog digestion:
- `Preview Top Batches`
- `Reclean Top Batches`
- `Load Evidence`
- `Load Residual Buckets`

Residual buckets will then be fed back into gold / calibration before retraining, shadow, and gate validation.

## 5. Phase Conclusion
Week 1 is complete.

The next steps should follow the execution plan strictly: no new features, only dataset digestion and model reliability work on the existing 200k dataset.

