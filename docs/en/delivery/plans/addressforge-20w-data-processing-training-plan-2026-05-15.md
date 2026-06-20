# AddressForge 20w Data Processing and Training Execution Plan - 2026-05-15

## Document Info
- Document Type: Data Processing & Training Execution Plan
- Effective Date: 2026-05-15
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: Turn the existing 20w address dataset into a trainable, verifiable, re-seedable, production-safe asset without adding new features

## 1. Current Context
The system already has the following base capabilities:
- dirty address diagnostics
- review opportunity leaderboard
- preview / reclean / evidence flows
- residual bucket detection and reseeding
- runtime identity for DecisionModel / Reranker / BuildingTypeModel
- `shadow -> assist -> guarded override -> promote / rollback`

However, directly feeding the full 20w dataset into training still risks:
- an overly conservative review distribution
- historical backlog pollution
- residual samples not feeding back into gold
- inconsistent training, evaluation, and replay contracts

So the current focus is not new features. It is:
1. consuming the existing backlog
2. feeding evidence-backed boundary samples back into gold
3. validating model reliability with holdout, shadow, replay, and gates
4. tightening the loop until production is safe

## 2. Overall Goal
1. Partition the 20w raw dataset into trainable layers
2. Reduce the review backlog using the current runtime
3. Re-seed gold and calibration data from residual buckets
4. Establish reliable model decisions through holdout, shadow, replay, and gate checks
5. Complete the training loop without adding new product capabilities

## 3. Operating Constraints
1. Do not add new product features or console features
2. Every action must fit the existing operational loop
3. Training must follow data partitioning and deduplication first
4. Re-seeded samples must remain traceable
5. Every training round must compare against the prior baseline
6. Any metric improvement must be checked for regression risk

## 4. Data Partition Strategy
Manage the 20w dataset in the following layers:

### 4.1 Raw
- original imported data
- source of truth, but not the main training set

### 4.2 Clean
- data the current runtime can handle reliably
- main coverage layer for online operation

### 4.3 Review
- data still requiring human judgment
- input for active learning, calibration, and residual analysis

### 4.4 Gold
- human-confirmed, deduplicated supervision data
- core source for training and evaluation

### 4.5 Residual
- stubborn samples that still survive the latest runtime
- boundary samples for the next human review and retraining cycle

## 5. Execution Cadence
Proceed through the following 6 phases in order. Each phase can be run batch-by-batch or week-by-week, but the sequence should not change.

### Phase 1: Baseline Freeze and Data Audit
Goal:
- freeze the current active baseline
- understand the true composition of the 20w dataset
- identify the initial distributions of review / accept / enrich / reject / residual

Work items:
- profile the 20w distribution
- freeze a holdout set
- output the current baseline metrics:
  - `decision_f1`
  - `building_type_f1`
  - `unit_number_f1`
  - `review_rate`
  - `disagreement_rate`
- confirm the current runtime identity

Completion criteria:
- a frozen baseline report exists
- a non-trainable holdout exists
- future training no longer contaminates the baseline

### Phase 2: Batch Review Backlog Consumption
Goal:
- prioritize the sources and batches with the largest review pressure
- move automatically recoverable samples back to `accept` or `enrich`

Work items:
- rank batches using the review opportunity leaderboard
- run:
  - `Preview Reclean`
  - `Reclean Reviews`
  - `Load Evidence`
  - `Load Residual Buckets`
- track recovery by `source_name / batch_id`

Completion criteria:
- review backlog is materially smaller
- per-batch recovery is explainable
- residual reasons can be bucketed

### Phase 3: Residual Bucket Re-seeding into Gold
Goal:
- convert stubborn residual samples into new gold and active-learning samples

Work items:
- select the most valuable boundary samples from residual buckets
- sample by residual reason / building type / disagreement kind
- deduplicate before seeding the active-learning queue
- have human review them and write them back to gold

Completion criteria:
- residual buckets successfully feed new gold
- new gold is deduplicated
- boundary sample quality improves

### Phase 4: Retrain DecisionModel / Reranker / BuildingType
Goal:
- retrain the existing models using the new gold and residual feedback
- keep the architecture stable; only update weights and thresholds

Work items:
- retrain DecisionModel
- retrain Reranker
- retrain BuildingTypeModel
- emit training artifacts and runtime identity
- record decision policy calibration

Completion criteria:
- new model artifacts are persisted
- runtime identity matches evaluation outputs
- training metadata is auditable

### Phase 5: Shadow / Replay / Gate Validation
Goal:
- verify the new model is actually better than the baseline
- ensure it does not regress house / apartment / commercial boundaries

Work items:
- run shadow comparison
- run replay comparison
- check release readiness
- check assist trial advantage
- check reranker impact direction

Completion criteria:
- key metrics do not regress
- shadow advantage is positive
- gate passes or a concrete blocker is identified

### Phase 6: Production Replay and Controlled Closure
Goal:
- promote only when the evidence is sufficient
- keep rollback available when the gate fails

Work items:
- only models that pass the promote gate may be promoted
- update runtime with `/reload`
- use `/rollback` if needed
- feed the next backlog into the next loop

Completion criteria:
- model upgrades are rollback-safe
- production state is auditable
- the next iteration has fresh backlog input

## 6. Evidence Required Each Round
Each iteration must output at least:
- the batch currently being processed
- before/after changes in review / accept / enrich / reject
- residual bucket changes
- gold delta
- training artifact paths
- runtime identity
- shadow / replay / gate outcomes

## 7. Recommended Order
1. Baseline freeze and data audit
2. Batch review backlog consumption
3. Residual bucket re-seeding into gold
4. Retrain existing models
5. Shadow / replay / gate validation
6. Promote / reload / rollback closure

## 8. Completion Criteria
The 20w data training loop is complete only when all of the following are true:
1. Most auto-recoverable samples have been moved out of review
2. residual buckets are feeding back into gold consistently
3. the frozen holdout is stable and better than the old baseline
4. shadow / replay / gate no longer show systemic regression
5. runtime identity is present in training, evaluation, replay, and production
6. production can safely promote, reload, and rollback

