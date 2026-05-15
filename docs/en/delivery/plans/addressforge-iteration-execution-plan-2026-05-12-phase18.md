# AddressForge Iteration Execution Plan - 2026-05-12 (Phase 18: Rollout, Gate, And Operations Completion)

## Document Info
- Document type: Execution Plan / Production Readiness Plan
- Effective date: 2026-05-12
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: complete the production rollout loop for the next-generation ML system

## 1. Background And Problem Definition
Even if the models are better, the next-generation ML system is not complete without:
- correct activation
- correct loading
- correct gate logic
- correct rollback

## 2. Main Goal
1. close the model activation chain
2. build Release Gate 2.0
3. build rollback and operational loops
4. finish productionizing the next-generation ML system

## 3. Requirements

### Requirement 18-1: Model activation chain closure
Delivery requirements:
- trained artifacts must be correctly loaded by worker/API
- cleaning/validation runtime must prove that it is using the new model

### Requirement 18-2: Release Gate 2.0
Delivery requirements:
- gate must evaluate:
  - heuristic baseline
  - supervised model delta
  - shadow disagreement
  - rollback risk

### Requirement 18-3: Safe rollout / rollback
Delivery requirements:
- define switching rules for:
  - shadow
  - assist
  - guarded override
  - default on
- provide a fast rollback procedure

### Requirement 18-4: Continuous-learning operational loop
Delivery requirements:
- minority-label seeding
- structured correction
- disagreement review
- feature-schema evolution
must all enter a durable production loop

### Requirement 18-5: Dirty-address diagnostics list
Delivery requirements:
- the console must directly show dirty rows from newly imported data
- filtering must be supported by `source_name` and `batch_id`
- the list must expose:
  - `missing_unit`
  - `gps_conflict`
  - `reference_gap`
  - `parser_disagreement`
  - `manual_review`
- each row must display the system's suggested corrected structured fields for review and training feedback

## 4. Technical Methods
- **Model activation contract**
  - `/reload` must clear registry TTL caches before resolving the active runtime.
- **Gate by layer**
  - `DecisionModel` consistency gate must validate both `model_path` and the `metadata_path` sidecar.
- **Safe rollout stages**
- **Operational feedback loop**
- **Dirty address diagnostics**
  - productize existing diagnostics from `validation_json` / `reference_json` / `parser_json` into a dedicated console list
  - support batch-oriented inspection immediately after API import and cleaning
- **Scoped review backlog reclean**
  - `reclean-reviews` must no longer be workspace-only.
  - It should support targeted review-backlog replay by:
    - `source_name`
    - `batch_id`
  - Goal:
    - let a newly imported batch absorb the latest Decision / Reranker / BuildingType behavior first
    - decide later whether a full historical review replay is necessary
  - It should also provide:
    - `reclean-reviews-preview`
    - to estimate, without mutating the database, how many filtered review rows would now become:
      - `accept`
      - `enrich`
      - `review`
    - `reclean-reviews-evidence`
    - to return the actual current decision distribution after replay for a filtered `source_name / batch_id`:
      - `accept`
      - `enrich`
      - `review`
      - `pending`
    - together with:
      - `review_rate`
      - `recovered_rate`
    - It should also expose the dominant residual review buckets:
      - `remaining_review_reason_counts`
      - `remaining_review_building_type_counts`
    - Goal:
      - let the next Decision / BuildingType / policy iteration target the stubborn residual review buckets directly instead of tuning blindly.
    - It should also provide:
      - `reclean-review-opportunities`
    - Purpose:
      - rank the most review-heavy batches by `source_name / batch_id`
      - help operators choose the highest-value preview / reclean target first
    - It should also provide:
      - `preview-top-review-opportunities`
    - Purpose:
      - aggregate a projected reclean preview for the top N most review-heavy batches
      - also emit a per-batch recovery summary so operators can compare which batch is worth replaying first
      - quantify the expected:
        - `accept`
        - `enrich`
        - `review`
        conversion mix before triggering a bulk replay
      - let operators decide whether the next automated replay wave is worth running
    - It should also provide:
      - `reclean-top-review-opportunities`
    - Purpose:
      - automatically select the top N most review-heavy batches from the leaderboard
      - also return an aggregated preview summary for those batches so operators can judge whether the replay wave is worth running
      - reset them to `pending` and trigger a single cleaning job
      - turn backlog reduction into a prioritized batch operation instead of a manual per-batch click path
    - It should also provide:
      - `review-residual-buckets`
    - Purpose:
      - expose the dominant remaining review buckets for the current filtered batch across:
        - `reason`
        - `building_type`
        - `parser_disagreement_kind`
        - `reference_gap_reason`
      - let the next ML / policy iteration target the real residual buckets directly

## 5. Expected Benefit
- turn the next-generation ML system from an engineering prototype into a production capability
- make model upgrades controlled, reversible, and auditable

## 6. Deliverables
- Release Gate 2.0
- model activation contract
- rollback playbook
- next-gen ML operations guide

## 7. Completion Criteria
1. the supervised model layer can be deployed safely
2. runtime truly consumes the new model
3. gate / rollback / feedback form a complete loop
4. the next-generation ML system reaches production readiness

## 8. Final Condition
When Phase 18 is complete:

**AddressForge’s next-generation ML system can be declared 100% complete.**
