# AddressForge 20w Data Processing and Training Execution Summary 2026-05-16 Week 3

## Document Info
- Project: AddressForge
- Scope: 20w data processing and training loop
- Phase: Week 3
- Date: 2026-05-16

## Context
The prior analysis established that:
- human gold does not show obvious large-scale mislabeling, but coverage is narrow
- the observed `ml_gold` `raw_id_cross_split` effect is mostly due to multi-task reuse, not same-task leakage
- the next step should strengthen rare and boundary classes instead of expanding the already large review class indiscriminately

## What Was Executed
### 1. Live residual / review hotspot verification
We rechecked the current heaviest review batches and dominant reasons via live MySQL:
- `historical_db_backfill / NULL`
- `third_party / HASUB-202605112209`
- `third_party / HASUB-202605072129`
- `third_party / HASUB-202605092211`

The dominant review reasons remain:
- `Parser confidence is moderate; review is safer.`
- `Address is incomplete and needs manual confirmation.`

### 2. Scoped residual reseeding
Executed a scoped residual reseed:
- `workspace = default`
- `source_name = third_party`
- `batch_id = HASUB-202605112209`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

Execution result:
- active learning queue insertions: `150`
- `run_id = 4513`
- current `active_learning_queue` total: `2120`

### 3. Second residual bucket reseed
Executed a second scoped residual reseed for the next-highest priority batch:
- `workspace = default`
- `source_name = third_party`
- `batch_id = HASUB-202605072129`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

Execution result:
- active learning queue insertions: `150`
- `run_id = 4516`
- current queued total: `957`

### 4. Training target narrowing
Week 3 execution has been narrowed to:
- prioritize rare and boundary classes
- focus supplementation on:
  - `decision`
  - `commercial`
  - `hard_correction`
  - `gps_conflict`
  - `reference_review`
  - `calibration_accept`
  - `unit_boost_accept`
- avoid indiscriminately expanding the already large `review` class

### 5. Decision calibration / minority supplementation
We also advanced the supplementation flow into narrower supervision boundaries:
- `decision calibration` reseed: `inserted = 40`
- `decision minority` reseed: `inserted = 80`
- total new active-learning samples: `120`
- corresponding runs:
  - `run_id = 4514`
  - `run_id = 4515`

### 6. Third high-priority residual batch reseed
We continued with scoped residual reseeding on the next high-value batch:
- `workspace = default`
- `source_name = third_party`
- `batch_id = HASUB-202605092211`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

Execution result:
- active learning queue insertions: `150`
- `run_id = 4520`

### 7. Historical backfill source reseed
We also continued source-scoped residual reseeding for the historical backfill source:
- `workspace = default`
- `source_name = historical_db_backfill`
- `batch_id = NULL`
- `target_buckets = history_mismatch, asset_gap, location_drift, building_type_gap, parser_disagreement`

Execution result:
- active learning queue insertions: `150`
- `run_id = 4517`

### 8. Decision minority reseed follow-up
We then extended the decision minority supplementation:
- `decision calibration` reseed: `inserted = 0`
- `decision minority` reseed: `inserted = 120`
- corresponding runs:
  - `run_id = 4518`
  - `run_id = 4519`

### 9. Review queue prescreen
We ran a batch prescreen over the currently queued review samples:
- `workspace = default`
- `limit = 200`
- `overwrite = false`

Execution result:
- processed samples: `200`
- cache hits: `0`
- skipped: `0`
- total `review_prescreen_cache` rows: `673`

## Evidence
- residual reseed completed successfully with `inserted = 150`
- second residual reseed completed successfully with `inserted = 150`
- third residual reseed completed successfully with `inserted = 150`
- historical backfill source-scoped residual reseed completed successfully with `inserted = 150`
- decision calibration completed with `inserted = 40`
- decision minority completed with `inserted = 80`
- decision calibration follow-up reseed returned `inserted = 0`
- decision minority follow-up reseed returned `inserted = 120`
- active learning queue total increased to `2810`
- `residual_bucket/building_type` queued total: `714`
- `decision_minority_label/review` queued total: `204`
- `decision_calibration/review` queued total: `40`
- batch prescreen successfully processed `200` queued review samples and wrote them to `review_prescreen_cache`
- the queued backlog is still growing, which confirms that the Week 3 supplementation loop is actively feeding forward
- `residual_bucket/building_type` remains the largest unconsumed supplementation bucket
- the plan document now explicitly records the training discipline:
  - `train/eval/test` must remain mutually exclusive within each `sample_type`
  - `raw_id_cross_split` metrics must first distinguish normal multi-task reuse from true same-task leakage

## Residual Risk
- The supplementation still leans heavily on residual/review boundary cases; rare classes such as `decision` and `commercial` still need dedicated follow-up sampling
- Calibration / minority supplementation is underway, but `commercial` / `gps_conflict` / `hard_correction` still need dedicated follow-up sampling
- We still need to observe whether the residual routing actually yields a meaningful gold increment before moving into gold / calibration reconstruction

## Next Step
- Continue Week 3 residual bucket reseeding
- Keep supplementing rare and boundary classes based on residual summaries
- Continue supplementing `decision calibration` and `decision minority` boundary buckets
- Before entering Week 4 gold / calibration reconstruction, confirm that supplementation is producing a meaningful increment
