# AddressForge Iteration Execution Plan - 2026-05-12 (Phase 15: DecisionModel Runtimeization)

## Document Info
- Document type: Execution Plan / ML Runtime Delivery Plan
- Effective date: 2026-05-12
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: move `DecisionModel` from offline baseline to controlled online capability

## 1. Background And Problem Definition
`DecisionModel` already proves itself offline, but still mainly lives in:
- baseline training
- compare artifacts
- shadow-level validation

It has not yet become part of the actual runtime assist/override flow.

## 2. Main Goal
1. connect `DecisionModel` to shadow-assist serving
2. build a disagreement loop for model vs heuristic
3. tighten `review/reject` minority-class boundaries

## 3. Requirements

### Requirement 15-1: DecisionModel shadow-assist serving
Delivery requirements:
- runtime must emit:
  - heuristic decision
  - model decision
  - disagreement reason
- all requests must enter shadow logging

### Requirement 15-2: Decision boundary calibration
Delivery requirements:
- continue improving:
  - false review
  - false reject
  - over-sensitive review

### Requirement 15-3: Decision rollout policy
Delivery requirements:
- define the rules for:
  - shadow
  - assist
  - guarded override

## 4. Technical Methods
- **Shadow-assist policy layer**
- **Disagreement bucket logging**
- **Minority-label reinforcement**
- **Threshold tuning with safety guards**

Current priority slice:
- **Gold-backed DecisionModel shadow-assist compare**
  - runtime must return:
    - heuristic decision
    - ml shadow decision
    - disagreement reason
  - evaluator must compute directly against latest human gold:
    - heuristic decision metrics
    - ml shadow decision metrics
    - disagreement buckets
    - shadow advantage
  - benefit: first prove that online shadow behavior matches the offline baseline, then move into assist / guarded override.

Current validation result (2026-05-12):
- live gold compare on the active runtime is now working:
  - heuristic `decision_f1 = 0.6268`
  - ml shadow `decision_f1 = 0.6752`
  - `shadow_advantage = +0.0484`
  - `disagreement_rate = 0.0861`
- main disagreement buckets:
  - `MODEL_MORE_AGGRESSIVE_ACCEPT = 100`
  - `MODEL_MORE_CONSERVATIVE_REVIEW = 21`
- current blocker:
  - the code-level serving contract switch is now complete
  - after live retraining, logs confirm the active runtime is loading from:
    - `runtime/models/decision_catboost_v1.json`
    - `runtime/models/decision_catboost_v1.pkl`
    and no longer falling back to legacy `.cbm` compatibility mode
  - remaining work:
    - wait for the current lightweight evaluation artifact to complete
    - then use that artifact to judge assist rollout readiness

Current implementation progress (2026-05-13):
- `guarded assist recommendation` has been added while keeping the system in `shadow-only` mode
- runtime now emits, in addition to:
  - `heuristic_decision`
  - `model_decision`
  - `disagreement_reason`
  also:
  - `assist_eligible`
  - `assist_recommended_decision`
  - `assist_guard_reason`
  - `assist_policy_mode`
- evaluator now also tracks:
  - `assist_readiness.eligible_count`
  - `assist_readiness.recommended_decision_counts`
  - `assist_readiness.guard_reason_counts`
  - `assist_readiness.gold_match_rate`
- evaluator now also emits a formal artifact:
  - `decision_assist_rollout_readiness`
  - containing:
    - `status`
    - `checks`
    - `shadow_advantage`
    - `disagreement_rate`
    - `eligible_count`
    - `assist_gold_match_rate`
- evaluator now also emits:
  - `decision_threshold_tuning_hints`
  - which maps dominant disagreement buckets directly to candidate tuning points such as:
    - `assist_accept_score_threshold`
    - `assist_accept_parse_score_threshold`
    - `assist_review_score_threshold`
    - `assist_review_parse_score_threshold`
    - `assist_review_reference_score_threshold`
- evaluator now also runs:
  - `assist trial simulation`
  - meaning it simulates the decision outcome that would occur if the current
    `assist_eligible + assist_recommended_decision`
    logic were enabled, without changing the live final decision
- this adds:
  - `assist_trial`
  - `assist_trial_advantage`
  - readiness check:
    - `assist_trial_not_worse_than_shadow`
- evaluator now also emits:
  - `decision_policy_calibration_proposal`
  - which directly specifies:
    - which thresholds to tune
    - adjustment direction
    - suggested step size
    - reason
  - and still keeps:
    - `apply_now = false`
  - meaning:
    - the proposal is generated automatically from evaluation
    - actual threshold changes are now explicitly consumed by the training pipeline and written back into artifacts / registry

Current implementation progress (continued):
- `trainer` now reads the latest active model's:
  - `decision_policy_calibration_proposal`
- and merges supported threshold changes into the next:
  - `decision_policy`
- the currently supported assist thresholds are:
  - `assist_accept_score_threshold`
  - `assist_accept_parse_score_threshold`
  - `assist_review_score_threshold`
  - `assist_review_parse_score_threshold`
  - `assist_review_reference_score_threshold`
- the resulting training artifact and registry now also record:
  - `decision_policy_calibration`
  - including:
    - source model
    - source version
    - applied changes
- they also retain:
  - `decision_policy_before_calibration`
  - `decision_policy`
  so each training run can be audited directly by comparing:
  - thresholds before calibration
  - thresholds after calibration
- to make iterative training/evaluation loops faster and more stable, a formal environment switch now exists:
  - `ADDRESSFORGE_SKIP_CANADA_BENCHMARK=1`
- it applies to:
  - training
  - evaluation
- purpose:
  - skip Canada benchmark
  - validate more quickly:
    - `decision_shadow_assist`
    - `assist_rollout_readiness`
    - `assist_trial`
    - `decision_policy_calibration`
- additionally, `AddressPlatformService` now:
  - lazy-loads the vector retrieval engine
- benefit:
  - evaluation / replay / shadow only initialize vector retrieval when retrieval is actually needed
  - lightweight `DecisionModel` train/eval loops are less likely to be delayed by vector-model startup

The purpose is not to enable override yet. The purpose is to answer:
- which disagreement cases are now safe candidates for assist
- how often those assist recommendations match the latest human gold
- whether the system is already:
  - `ready_for_assist_trial`
  - or should remain:
  - `shadow_only` / `needs_more_assist_calibration`

## 5. Expected Benefit
- evolve ML from “offline is better” to “online is observable and comparable”
- build evidence for later heuristic replacement

## 6. Deliverables
- DecisionModel shadow-assist runtime
- disagreement report
- threshold tuning artifact
- rollout readiness summary

## 7. Completion Criteria
1. DecisionModel is online in shadow-assist mode
2. disagreement can be measured, reviewed, and fed back
3. assist-mode enablement criteria are defined

## 8. Next Dependency
After Phase 15:
- `Phase 16: CandidateRerankerModel Completion`
