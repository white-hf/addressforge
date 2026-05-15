# AddressForge Iteration Execution Plan - 2026-05-15 (Phase 19-24: Next-Gen ML Completion)

## Document Info
- Document Type: Execution Plan / Delivery Plan
- Effective Date: 2026-05-15
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: Move the next-gen ML system from "working" to "operational, learnable, and production-safe"

## 1. Current State
The system already has:
- `DecisionModel` shadow-assist
- versioned runtime bundles
- `BuildingTypeModel` guarded override
- scoped review-backlog reclean / preview / evidence / opportunity leaderboard
- baseline release gate / reload / rollback

What is still missing before the next-gen ML system can be considered complete:
1. backlog operations need to be stable and feed gold/training directly
2. residual buckets need to drive the next calibration and sampling loop
3. runtime / gate / rollback / observability need production-grade consistency

## 2. Overall Goal
1. Turn review backlog into a measurable operational loop
2. Turn residual buckets into formal inputs for gold, training, and calibration
3. Make runtime bundles, gates, reload, rollback, shadow, and assist consistent
4. Reach a long-term maintainable and auditable next-gen ML operating mode

## 3. Phase Breakdown

### Phase 19: Batch Recovery Summary Closure
Goal:
- Upgrade `preview-top-review-opportunities` from a single aggregate estimate to a stable batch-level recovery summary
- Let operators compare the recovery value of candidate batches directly

Code touchpoints:
- `src/addressforge/api/routes/cleaning.py`
- `templates/reports.html`
- `tests/test_cleaning_route.py`

Technical approach:
- Emit per-batch recovery summaries for leaderboard top batches
- Preserve the following fields:
  - `sampled_rows`
  - `accept / enrich / review`
  - `projected_recovery_rate`
  - `projected_remaining_review_rate`
  - `reason_counts`
  - `batch_summaries`
- Allow the UI to compare top batches by projected recovery

Completion criteria:
- Operators can compare multiple batch recovery estimates in the console
- Preview logic and reclean logic stay aligned
- Tests cover batch-level and aggregate summary consistency

### Phase 20: Residual Bucket -> Gold Re-seeding
Goal:
- Feed residual review buckets back into gold / calibration / training
- Make stubborn buckets a supervised data source, not just a display item

Code touchpoints:
- `src/addressforge/learning/gold.py`
- `src/addressforge/learning/trainer.py`
- `tests/test_gold_sampling.py`

Technical approach:
- Generate targeted re-seed samples from residual buckets
- Support sampling by:
  - `reason`
  - `building_type`
  - `parser_disagreement_kind`
  - `reference_gap_reason`
- Deduplicate by `raw_address_text` globally to avoid duplicate gold rows
- Feed residual reviews back into:
  - `decision minority`
  - `decision calibration`
  - `building_type edge cases`

Completion criteria:
- Residual buckets can create new supervised samples
- New samples do not duplicate or pollute existing gold
- Training/evaluation show measurable benefit from residual sampling

### Phase 21: DecisionModel Assist Threshold Recalibration
Goal:
- Recalibrate DecisionModel assist boundaries using real backlog outcomes and shadow-assist evidence
- Move `assist_trial` closer to controlled production

Code touchpoints:
- `src/addressforge/learning/evaluator.py`
- `src/addressforge/learning/trainer.py`
- `src/addressforge/api/server.py`

Technical approach:
- Retune the following thresholds against the remaining buckets:
  - `assist_accept_score_threshold`
  - `assist_accept_parse_score_threshold`
  - `assist_review_score_threshold`
  - `assist_review_parse_score_threshold`
  - `assist_review_reference_score_threshold`
- Separate the transitions:
  - `review -> accept`
  - `review -> enrich`
  - `accept -> review`
- Keep reporting:
  - `decision_shadow_assist`
  - `decision_assist_rollout_readiness`
  - `decision_threshold_tuning_hints`
  - `assist_trial_advantage`

Completion criteria:
- Assist threshold adjustments are proposal-driven
- Training consumes the previous round's proposal
- The next evaluation round shows measurable movement

### Phase 22: Reranker / BuildingType Version Binding Closure
Goal:
- Ensure replay / shadow / evaluator / API / worker all use the same runtime bundle for a given model version
- Prevent active / candidate version mixing

Code touchpoints:
- `src/addressforge/services/replay_service.py`
- `src/addressforge/services/model_service.py`
- `src/addressforge/services/reranker_service.py`
- `src/addressforge/api/server.py`

Technical approach:
- Complete manifest binding for reranker / building_type
- Return full runtime identity from runtime bundles
- Emit runtime identity in replay/shadow/evaluator outputs
- Keep the `BuildingTypeModel` safety guard:
  - `building_type_assist_enabled`
  - `building_type_assist_min_confidence`
  - `building_type_assist_allowed_transitions`

Completion criteria:
- Any evaluation can be traced back to the physical model file and manifest
- Candidate / active / replay / shadow never mix model versions

### Phase 23: Release Gate / Reload / Rollback Final Consistency
Goal:
- Make promote / reload / rollback reliable in production

Code touchpoints:
- `src/addressforge/models/registry.py`
- `src/addressforge/api/server.py`
- `tests/test_registry_release_gate.py`
- `tests/test_reload_sync.py`

Technical approach:
- `promote_model()` should only accept:
  - `status == "ready_for_assist_trial"`
  - all `checks` are true
- The consistency gate must inspect the complete sidecar set:
  - `decision_model_artifact.model_path`
  - `decision_model_artifact.metadata_path`
  - `reranker_model_artifact.model_path`
  - `building_type_model_artifact.model_path`
- Clear registry caches before `/reload` reads the latest manifest
- Keep `/rollback` consistent with in-memory reload

Completion criteria:
- Operators can understand why promotion is blocked
- Reload effects are verifiable
- Rollback is safe and auditable

### Phase 24: Production Observability and Regression
Goal:
- Turn the system from "can run" into "can operate long-term"

Code touchpoints:
- `src/addressforge/services/business_service.py`
- `src/addressforge/api/routes/business.py`
- `templates/reports.html`
- `tests/test_business_dirty_addresses.py`

Technical approach:
- Consolidate the following into the console and reporting:
  - `dirty address diagnostics`
  - `review opportunity leaderboard`
  - `batch recovery summary`
  - `residual bucket summary`
  - `release readiness`
- Add regression coverage for:
  - batch preview
  - batch reclean
  - evidence
  - residual buckets
  - promote gate
  - reload / rollback

Completion criteria:
- The console can explain why review is high, whether a batch is worth replaying, and what remains afterward
- Production regressions can reproduce the critical operational flows

## 4. Recommended Order
1. Phase 19
2. Phase 20
3. Phase 21
4. Phase 22
5. Phase 23
6. Phase 24

## 5. Success Definition
The next-gen ML system is only 100% complete when all of the following are true:
- automatic handling is materially better
- review backlog can be consumed continuously
- residual buckets feed training
- runtime bundles are traceable
- release gate / reload / rollback are closed loops
- the console and reports can explain production issues

