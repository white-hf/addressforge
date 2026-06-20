# AddressForge 20w Data Processing and Training Execution Summary 2026-05-17 Week 4

## Document Info
- Project: AddressForge
- Scope: 20w data processing and training loop
- Phase: Week 4
- Date: 2026-05-17

## Execution Started
### 1. Frozen new human gold baseline
A new gold snapshot has been frozen as the Week 4 gold / calibration reconstruction baseline:
- `gold_set_version = gold_v20260517`
- `split_version = v20260517`
- `snapshot_id = 27`
- `sample_count = 1406`
- `train/eval/test = 1126 / 154 / 126`

### 2. Queued review batch prescreen
We ran another batch prescreen over the currently queued review samples:
- `workspace = default`
- `limit = 200`
- `processed = 79`
- `cached = 121`
- `skipped = 0`

Current `review_prescreen_cache` total:
- `673`

### 3. Building-type edge case supplementation
We supplemented Week 4 building-type edge cases using existing edge-case seeders:
- `semantic_disambiguation`: `inserted = 3`
  - `run_id = 4524`
- `label_consistency`: `inserted = 8`
  - `run_id = 4525`

Current `review_prescreen_cache` total:
- `752`

### 4. Decision minority follow-up supplementation
We continued strengthening the `decision minority` boundary bucket:
- `inserted = 120`
- `run_id = 4526`

### 5. Additional decision minority supplementation
We expanded the `decision minority` queue further:
- `inserted = 154`
- `run_id = 4529`

Current `decision_minority_label / review` queued total:
- `598`

### 6. Additional queued review prescreening
We continued batch prescreening for queued review samples:
- `processed = 55`
- `cached = 145`
- `skipped = 0`

Current `review_prescreen_cache` total:
- `938`

### 7. DecisionModel runtime contract hardening
We fixed a DecisionModel sidecar inference contract issue exposed during the Week 4 baseline evaluation:
- The decision inference frame now force-coerces categorical columns to strings so CatBoost cannot misread a categorical slot as a floating-point value
- worker hot-reload now follows the current active manifest explicitly instead of falling back to legacy compatibility mode

### 8. City fallback recovery closure
We fixed the Canadian address parsing issue where missing city values were being defaulted to `Halifax`:
- `_finalize_parsed()` no longer forces a missing city into the profile default city
- the parser now performs locality recovery from raw text so real cities such as `New Glasgow` and `Dartmouth` are preserved
- the historical sample `Granville Street 285, New Glasgow, NS, B2H4Y8, CA` now stays as `New Glasgow` instead of falling back to `Halifax`

### 9. Live baseline conclusion
We completed a live baseline evaluation for the Week 4 candidate:
- `decision_f1 = 0.2991`
- compared with the current active `canada_default_v1` `decision_f1 = 0.7214`
- `release_comparison.promote_recommended = false`
- main error bucket: `OVER_SENSITIVE_REVIEW`

Conclusion:
- **Week 4 candidate does not move to promote**
- **The current active version remains in place**

## Why This Matters
This step consolidates the Week 3 residual / calibration / minority supplementation into a new trainable baseline, after which we can continue with:
- `decision minority` reconstruction
- `decision calibration` reconstruction
- `building_type edge cases` review
- duplicate text and conflicting label review

## Next Step
- Rebuild `decision minority` on `gold_v20260517`
- Rebuild `decision calibration` on `gold_v20260517`
- Recheck `building_type edge cases`
- Review duplicate address texts and conflicting labels
- Continue verifying that DecisionModel sidecar/runtime identity remains strictly aligned with the training artifact during live evaluation
- Continue cleaning historical rows where the default city was incorrectly written as `Halifax`
