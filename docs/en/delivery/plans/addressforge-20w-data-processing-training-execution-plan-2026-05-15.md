# AddressForge 20w Data Processing and Training Execution Plan - 2026-05-15

## Document Info
- Document Type: Execution Plan / Delivery Plan
- Scope: Governance, feedback, training, and validation for the existing 200k-address dataset
- Owner: AddressForge Architecture / Senior Engineering
- Status: In Progress
- Goal: Improve the reliability of the existing models and the quality of the 200k dataset without adding new product features

## 1. Design Premises
The system already provides:
- dirty address diagnostics
- review opportunity leaderboard
- preview / reclean / evidence
- residual bucket forecast / seed
- DecisionModel shadow-assist
- BuildingTypeModel guarded override
- versioned runtime bundles
- release gate / reload / rollback
- runtime identity audit output

This plan therefore focuses on execution, not new features:
1. dataset layering and freezing
2. batch-oriented backlog digestion
3. residual bucket reseeding
4. gold / calibration / holdout reconstruction
5. retraining, shadow evaluation, and gate validation

### 1.1 Week 1 baseline completed
- `raw_address_record` rows: `221,873`
- `address_cleaning_result` rows: `221,873`
- human-accepted `gold_label`: `1,406`
- `active_learning_queue` total: `1,850`
- current frozen holdout snapshot:
  - `gold_set_version = gold_v20260515`
  - `split_version = v20260515`
  - `snapshot_id = 26`
  - `sample_count = 1,406`
  - `train/eval/test = 1,145 / 129 / 132`
- top review reasons:
  - `Parser confidence is moderate; review is safer.`: `7,591`
  - `Address is incomplete and needs manual confirmation.`: `1,286`
- top review batches:
  - `third_party / HASUB-202605112209`
  - `third_party / HASUB-202605072129`
  - `third_party / HASUB-202605092211`

### 1.2 Week 2 execution started
- Ran `preview-top-review-opportunities` for `third_party / HASUB-202605112209`
- 120-sample preview result:
  - `accept = 1`
  - `review = 119`
  - `projected_recovery_rate = 0.0083`
- Triggered scoped reclean for the same batch
- Ran two `run_cleaning_once` passes, processing 2000 rows in total
- Current SQL distribution for that batch:
  - `accept = 6027`
  - `pending = 2364`
  - `enrich = 4`
  - `review = 2`
- Remaining dominant reasons:
  - `Parser confidence is moderate; review is safer.`
  - `Address is incomplete and needs manual confirmation.`
  - `LOCALITY_MISMATCH`
  - `LOW_SCORE_MATCH`
- Ran a scoped residual reseed for `third_party / HASUB-202605072129`
  - target buckets: `history_mismatch`, `asset_gap`, `building_type_gap`
  - inserted into active learning queue: `120`
  - current `active_learning_queue` total: `1,970`
  - `residual_bucket` rows in queue: `120`

## 2. Overall Goal
1. Split the 200k dataset into stable layers so auto-processing and human review are explicit
2. Consume the highest-value review batches first
3. Turn stubborn residual buckets into new gold / active-learning samples
4. Build a repeatable training loop with frozen holdout, shadow, replay, and release gates
5. Keep training artifacts, runtime binding, console visibility, and release decisions aligned

## 3. Data Governance Principles
### 3.1 Data Layers
The 200k dataset is organized into five layers:
- `raw`: original imports
- `clean`: stable auto-processed records
- `review`: records still requiring human judgment
- `gold`: human-confirmed high-quality labels
- `residual`: stubborn edge cases that remain after replay

### 3.2 Training Discipline
- Do not train the main model directly on the full `review` set
- Use `gold` as the primary supervised source
- Use `residual` only for targeted strengthening
- Keep the holdout frozen and immutable across training waves
- `ml_gold` / multi-task samples may reuse the same `raw_id` across different `sample_type` values, but `train/eval/test` must remain mutually exclusive within each `sample_type`
- Any `raw_id_cross_split` metric must first distinguish expected multi-task reuse from true within-task leakage

### 3.3 Operating Discipline
- Prefer batch-level operations over full-dataset sweeps
- Always `preview` before `reclean`, then validate with `evidence`
- Any reseeding action must have an explicit `source_name` / `batch_id` or residual scope

## 4. Weekly Execution Plan

### Week 1: Dataset Audit and Holdout Freeze
Goal:
- Establish a stable baseline for the 200k dataset
- Define train / validation / holdout boundaries

Actions:
- Audit current `raw / clean / review / gold / residual` distributions
- Break down the dataset by `source_name`, `batch_id`, `building_type`, and `reason`
- Freeze a holdout set that will not be used for training
- Identify the current highest-review batches as the first governance target

Deliverables:
- 200k baseline summary
- frozen holdout list
- ranked top-batch list

Completion Criteria:
- Holdout is fixed and excluded from future training
- Dataset layers are explicit and explainable

### Week 2: Review Backlog Digestion
Goal:
- Reduce the highest-value review backlog using the current runtime

Actions:
- Use `Review Opportunity Leaderboard` to select top batches
- Run `Preview Top Batches` for each batch
- Execute `Reclean Top Batches` only on high-value batches
- Validate actual recovery with `Load Evidence`

Deliverables:
- batch-level recovery summary
- real reclean results
- residual review list

Completion Criteria:
- It is clear which batches are worth continuing
- `review -> accept/enrich` gains are quantified

### Week 3: Residual Bucket Reseeding
Goal:
- Convert stubborn residual samples into the next round of supervision
- Use the current gold distribution to strengthen rare and boundary classes instead of expanding the already large review class

Current execution progress:
- Scoped residual reseed completed for `third_party / HASUB-202605112209`
- Target buckets used: `history_mismatch`, `asset_gap`, `location_drift`, `building_type_gap`, `parser_disagreement`
- Active learning queue insertions: `150`
- A second scoped residual reseed was executed for `third_party / HASUB-202605072129`
- Second round inserted: `150`
- A source-scoped residual reseed was executed for `historical_db_backfill`
- Active learning queue insertions: `150`
- A third scoped residual reseed was executed for `third_party / HASUB-202605092211`
- Third round inserted: `150`
- `decision calibration` follow-up reseed returned `inserted = 0`
- `decision minority` follow-up reseed returned `inserted = 120`
- A batch prescreen was executed for the currently queued review samples: `200`

Actions:
- Use `Load Residual Buckets` to identify stubborn buckets
- Classify by `reason`, `building_type`, `parser_disagreement_kind`, and `reference_gap_reason`
- Use `Seed Residual for Review` to feed high-value residual samples into active learning / gold
- Deduplicate reseeded samples to avoid duplicate labels
- Prioritize the following supplementation buckets:
  - `decision`
  - `commercial`
  - `hard_correction`
  - `gps_conflict`
  - `reference_review`
  - `calibration_accept`
  - `unit_boost_accept`
- Keep `review` sampling focused only on true hard cases; do not expand it indiscriminately

Deliverables:
- residual bucket summary
- reseeded sample list
- gold increment from residuals
- gold supplementation priority list
- gold increment from residuals
- gold supplementation priority list

Completion Criteria:
- Residuals are no longer just observable
- Residuals can be reliably converted into supervised samples
- Supplemented samples materially increase coverage of rare and boundary classes

### Week 4: Gold / Calibration Reconstruction
Goal:
- Strengthen minority classes and boundary cases with new samples

Current execution progress:
- A new human gold baseline has been frozen:
  - `gold_set_version = gold_v20260517`
  - `split_version = v20260517`
  - `snapshot_id = 27`
  - `sample_count = 1406`
  - `train/eval/test = 1126 / 154 / 126`
- Another queued review prescreen batch has been run:
  - `processed = 79`
  - `cached = 121`
  - `skipped = 0`
- Building-type edge cases have been strengthened:
  - `semantic_disambiguation = 3`
  - `label_consistency = 8`
- `decision minority` queue has been expanded further:
  - `inserted = 154`
- Another queued review batch prescreen has been run:
  - `processed = 55`
  - `cached = 145`
  - `skipped = 0`

Actions:
- Rebuild `decision minority`
- Rebuild `decision calibration`
- Recheck `building_type edge cases`
- Review duplicate address texts and conflicting labels

Deliverables:
- new gold snapshot
- calibration sample set
- deduplication report

Completion Criteria:
- Gold is cleaner and more balanced
- Minority and edge-case coverage is materially stronger

### Week 5: Retraining and Shadow Evaluation
Goal:
- Validate the retrained artifacts through shadow and replay

Actions:
- Retrain using the refreshed gold set
- Run baseline evaluation
- Run shadow-assist
- Inspect runtime identity, reranker metrics, and decision metrics
- Compare active vs candidate behavior

Deliverables:
- new training artifacts
- shadow evaluation report
- replay evaluation report

Completion Criteria:
- The new model is stable or better on holdout and shadow
- Runtime identity is traceable

### Week 6: Gate Validation and Release Decision
Goal:
- Decide whether the new model may be promoted

Actions:
- Run `promote_model()` consistency checks
- Verify `decision_model_artifact.metadata_path`
- Verify `reranker_model_artifact` and `building_type_model_artifact`
- Check `assist_trial`, `shadow_advantage`, and `assist_trial_advantage`
- Validate `reload` / `rollback` if needed

Deliverables:
- release readiness summary
- promote / hold / rollback decision
- production regression record

Completion Criteria:
- A new model only moves forward when the gate approves it
- Rollback is verifiable and auditable

## 5. Key Metrics
This plan does not rely on a single F1 score. It must track:
- `decision_f1`
- `building_type_f1`
- `unit_number_f1`
- `review_rate`
- `reclean recovery rate`
- `residual recovery rate`
- `shadow_advantage`
- `assist_trial_advantage`
- `reranker impact_rate`
- `runtime_identity` coverage

## 6. Risks and Constraints
### Risks
- Over-relying on global replay can amplify historical noise
- Residual buckets may still contain some noisy samples
- Training and serving may drift if runtime contracts are not enforced

### Constraints
- No new product features
- No bypassing the release gate
- No skipping holdout / shadow / replay
- No empty-scope residual reseeding

## 7. Success Definition
The 200k data processing and training plan is complete only when all of the following are true:
- the 200k dataset is stably layered
- the main review backlog has been consumed batch by batch
- residual buckets feed gold / calibration
- the new model is stable or better on holdout and shadow
- runtime / gate / reload / rollback are consistent end to end
- the console can explain each batch result and the remaining residue
