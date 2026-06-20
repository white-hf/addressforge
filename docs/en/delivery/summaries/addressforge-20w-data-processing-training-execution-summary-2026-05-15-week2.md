# AddressForge 20w Data Processing and Training Execution Summary - 2026-05-15 Week 2

## Document Info
- Document Type: Execution Summary / Backlog Digestion Result
- Related Plan: [addressforge-20w-data-processing-training-execution-plan-2026-05-15.md](../plans/addressforge-20w-data-processing-training-execution-plan-2026-05-15.md)
- Status: In Progress
- Scope: Week 2 - review backlog digestion and top-batch preview / reclean

## 1. Overall Conclusion
Week 2 has moved into live backlog digestion.

This week has already completed:
1. a top-batch recovery preview for the heaviest review batch
2. a scoped reclean for that batch
3. two cleaning passes to push pending rows back through the pipeline
4. a residual-bucket breakdown for the same batch
5. a scoped residual reseed for the next highest-review batch
6. a scoped preview for `third_party / HASUB-202604240249`, confirming it is a smaller but still high-yield batch
7. a scoped reclean submitted for `HASUB-202604240249`, now awaiting further cleaning passes
8. a refreshed preview for `third_party / HASUB-202605072129`, confirming it is still a high-yield batch in the current runtime
9. a new scoped reclean submitted for `HASUB-202605072129`
10. a source-scoped preview for `historical_db_backfill`, confirming it still has very high recovery potential
11. a source-scoped reclean submitted for `historical_db_backfill`

## 2. Completed Work
### 2.1 Top-Batch Recovery Preview
The highest-review batch, `third_party / HASUB-202605112209`, was previewed first.

The 120-sample preview for that batch showed:
- `accept = 1`
- `review = 119`
- `projected_recovery_rate = 0.0083`

This indicates the batch is still strongly review-heavy and has low short-term auto-recovery yield.

### 2.2 Scoped Reclean
The same batch was then recleaned, followed by two `run_cleaning_once` passes.

Actual processing:
- cleaning pass 1: 1000 rows
- cleaning pass 2: 1000 rows
- total processed: 2000 rows

Current SQL distribution for the batch:
- `accept = 6027`
- `pending = 2364`
- `enrich = 4`
- `review = 2`

### 2.3 Residual Bucket Breakdown
The batch's residual buckets were split into the following dominant reasons:
- `Parser confidence is moderate; review is safer.`
- `Address is incomplete and needs manual confirmation.`
- `LOCALITY_MISMATCH`
- `LOW_SCORE_MATCH`

This shows the batch is not structurally broken; it is mostly held back by:
- conservative moderate-confidence review policy
- locality/reference mismatch
- a small number of incomplete addresses

### 2.4 Scoped Residual Reseed
A scoped residual reseed was executed for `third_party / HASUB-202605072129`.

Reseed result:
- `inserted = 120`
- `active_learning_queue` total rose to `1,970`
- `residual_bucket` rows in queue: `120`

Target buckets:
- `history_mismatch`
- `asset_gap`
- `building_type_gap`

### 2.5 Next High-Yield Batch Preview
Scoped preview was executed for `third_party / HASUB-202604240249`.

The 40 sampled rows were projected to recover as:
- `accept = 25`
- `review = 15`
- `projected_recovery_rate = 0.625`

This indicates the batch still has meaningful recovery potential and is worth further backlog digestion.

### 2.6 Next High-Yield Batch Reclean
Scoped reclean was submitted for `third_party / HASUB-202604240249`.

Current visible state:
- `affected_records = 50`
- `job_id = 3079`
- the batch's review rows have been reset to pending and are waiting for the next cleaning pass

### 2.7 Next Low-Yield Batch Preview
Scoped preview was executed for `third_party / HASUB-202605010445`.

The 40 sampled rows were projected to recover as:
- `accept = 3`
- `review = 37`
- `projected_recovery_rate = 0.075`

This indicates the batch has low short-term auto-recovery value and should remain a residual / calibration candidate rather than a high-priority reclean target.

### 2.8 High-Yield Batch Reclean (Updated)
A refreshed preview was executed for `third_party / HASUB-202605072129`.

The 120 sampled rows were projected to recover as:
- `accept = 95`
- `review = 25`
- `projected_recovery_rate = 0.7917`

This confirms the batch is still a high-yield recovery target and was resubmitted for scoped reclean.

Latest scoped reclean result:
- `affected_records = 1644`
- `rolled_back_to = 7170`
- `job_id = 3086`
- the batch's review rows have been reset to pending and are waiting for the next cleaning pass

### 2.9 Historical Source Scoped Reclean
A source-scoped preview was executed for `historical_db_backfill`.

The 120 sampled rows were projected to recover as:
- `accept = 114`
- `review = 6`
- `projected_recovery_rate = 0.95`

This confirms the historical backfill source still has very high auto-recovery potential in the current runtime.

Latest source-scoped reclean result:
- `affected_records = 3384`
- `rolled_back_to = 13831`
- `job_id = 3093`
- the source's review rows have been reset to pending and are waiting for the next cleaning pass

## 3. Validation Results
### 3.1 Preview vs. Actual Digestion
The preview confirmed that:
- this batch is not a high-yield auto-recovery target
- but it is still a valid backlog target because it carries heavy review pressure

### 3.2 Training Relevance
The remaining residuals are now concentrated in:
- moderate-confidence decisions
- locality mismatch

The preview result for `HASUB-202604240249` also shows:
- the batch still has meaningful recoverable content
- this smaller batch is a better Week 2 digestion target than immediately moving it into residual-only handling

That makes them suitable for later feedback into:
- calibration
- decision minority
- residual bucket reseeding

## 4. Remaining Work
The other high-review batches still need processing:
- `third_party / HASUB-202605092211`

Current global cleaning state:
- `accept = 212950`
- `review = 6980`
- `pending = 1931`
- `enrich = 12`

Current `third_party` distribution:
- `review = 5474`
- `pending = 53`
- `accept = 25316`

Current `historical_db_backfill` distribution:
- `review = 1506`
- `pending = 1878`
- `accept = 187634`

Current running cleaning job:
- `job_id = 3094`
- `status = succeeded`
- `current_raw_id = 421326`

Queued follow-up cleaning jobs:
none

The next decision is whether to:
- continue batch-by-batch recleaning
- or shift more effort into gold / calibration reseeding

## 5. Phase Conclusion
Week 2 has started and has already produced real data evidence.

The direction remains aligned with the 20w governance plan:
- digest backlog through the existing operational loop
- convert stubborn residuals into new supervision
- then return to retrain / shadow / gate
