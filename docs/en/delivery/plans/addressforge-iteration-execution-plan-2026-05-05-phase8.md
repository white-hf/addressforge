# AddressForge Iteration Execution Plan - 2026-05-05 (Phase 8: Incremental Data Intake, Reference Coverage Expansion, And Fresh-Data Quality Validation)

## Document Info
- Document Type: Execution Plan / Optimization Requirements
- Effective Date: 2026-05-05
- Owner: AddressForge Product / Engineering
- Status: Planned
- Trigger: Phase 7 completed the canonical/reference quality baseline. The system now has a relatively stable parsing, assetization, reference-fusion, and quality-diagnostics foundation. The next bottleneck is no longer “how to keep refining known internal cases,” but “how to intake fresh incremental address data, expand reference coverage, and validate real gains on new data.”

## 1. Current Context & Problem Definition
After Phase 3 through Phase 7:
- unit-related parsing quality has improved materially
- the human-gold -> training -> evaluation -> replay -> shadow -> gate loop is connected
- canonical gap, locality gap, and actionable reference gap have been largely reduced to zero
- the asset-quality report can now distinguish benign convergence from real quality risks

The current state implies three things:

1. **the mainline on known internal data is largely stable**
   the return from repeatedly mining the same internal review pool is now diminishing.

2. **the next phase must move toward fresh-data validation**
   without ingesting new incremental address data, the system cannot prove that current model behavior, reference fusion, and canonical strategy still hold on fresh data.

3. **reference coverage will re-emerge as a real bottleneck**
   once fresh data arrives, the system will encounter:
   - new locality / building / unit patterns
   - areas or buildings missing from current reference coverage
   - new tail cases not covered by the existing canonical rules

Therefore, the next core problem is:

**to move the system from “it is accurate on existing data” to “it can stably intake fresh incremental address data, expand reference coverage, and continuously validate parsing and assetization quality on new data.”**

## 2. Overall Goal
The goals for this phase are:

1. establish controlled incremental address-data intake and processing
2. establish fresh-data parsing quality and canonical/reference quality validation
3. identify and quantify reference coverage gaps introduced by new data
4. prepare the foundation for later reference expansion, fresh-gold growth, and new-data quality governance

## 3. Core Optimization Targets

### 3.1 Incremental Intake Stability
The system must process newly arriving address data reliably, not only historical data.

### 3.2 Fresh-Data Quality Validation
The system must explicitly distinguish:
- performing well on known historical data
- and still performing well on new incremental data

### 3.3 Reference Coverage Expansion Readiness
Once new data enters the system, it must quickly identify:
- true no-reference coverage gaps
- locality / street normalization mismatches
- correctly parsed but reference-missing buildings / units

### 3.4 Incremental Assetization Confidence
After new data arrives, the canonical/reference mainline must continue to provide:
- stable asset promotion
- explainable canonical convergence
- quality observability that does not degrade under incremental import

## 4. Concrete Requirements

### Requirement 1: Incremental address data must support controlled intake
The system must support batch-based import of third-party incremental address data, with each batch processed and tracked independently.

Delivery requirements:
- incremental data can enter the ingestion / cleaning / assetization mainline in batches
- each new batch has its own processing scope and result set
- new data must not be mixed with historical data in a way that prevents fresh-data analysis

### Requirement 2: Add fresh-data quality validation
The system must provide a dedicated validation view for newly imported data.

Delivery requirements:
- the system can distinguish fresh imported data from historical processed data
- it can quantify fresh-data:
  - decision quality
  - building_type stability
  - unit recovery quality
  - canonical/reference convergence quality

### Requirement 3: Add reference coverage gap detection for fresh data
The system must identify reference coverage gaps on new data, rather than only observing parse success.

Delivery requirements:
- the system can distinguish:
  - no reference candidate
  - weak locality/street normalization mismatch
  - parse-correct but reference-missing rows
- it can emit sample-level fresh-data gap evidence

### Requirement 4: Add a fresh-data canonical/reference report
The system must generate a dedicated asset/report view for each fresh-data batch.

Delivery requirements:
- the report includes at least:
  - fresh rows processed
  - fresh accepted rows
  - fresh reference-backed ratio
  - fresh canonical gap
  - fresh no-reference examples
- the report can be compared directly against the historical baseline

### Requirement 5: Add fresh-gold expansion readiness
The system must identify the most valuable fresh-data samples for later human review and gold expansion.

Delivery requirements:
- the system can identify fresh-data:
  - new apartment/unit hard cases
  - new reference coverage gaps
  - new building_type boundary samples
- those samples can directly enter the later review / gold / training loop

### Requirement 6: Add balanced human-sample selection
The system must support splitting human-review samples into a correction pool and a calibration pool, instead of letting hardest cases dominate the full review input.

Delivery requirements:
- the system can distinguish:
  - hardest correction samples
  - calibration samples close to real production distribution
  - fresh-data-specific high-value samples
- the system can sample by target mix, for example:
  - regular `single_unit`
  - regular `multi_unit`
  - apartment/unit hard cases
  - double-number house boundary cases
  - numbered-road / highway cases
  - reference-gap cases
- generated review batches must carry sample-pool category and sampling reason
- before training, the system can quantify the sample-pool structure of the new gold mix, so hardest-case concentration is visible

### Requirement 7: Add decision-boundary calibration and historical gold semantic decontamination
After the apartment/unit mainline has recovered, the system must explicitly calibrate the `accept/review/reject` decision boundary and isolate historical non-semantic task labels from training semantics.

Delivery requirements:
- the system can distinguish:
  - true semantic task types used for learning
  - historical pool/process labels used only for sampling or workflow tracking
- decision-threshold learning must be able to read:
  - task_type
  - notes/sample_pool
  - raw_text
  - building_type
  and related context instead of relying only on bare confidence
- historical `review` hardest-case samples must not continue to dominate decision-threshold learning without control
- the optimization must validate:
  - `decision_f1`
  - `review_rate`
  while protecting `building_type_f1 / unit_number_f1 / unit_recall`

### Requirement 8: Add a supervised model baseline layer
The system must evolve from “statistical weight calibration” toward a true supervised model layer, without replacing the existing parser/reference/canonical mainline.

Delivery requirements:
- the new model layer must first be introduced as a parallel baseline, not as a direct runtime replacement
- the first target tasks are limited to:
  - `decision`
  - `building_type`
  - candidate reranking
- the first model version must prioritize existing structured runtime features instead of jumping directly to end-to-end neural parsing
- the new model layer must be evaluated side-by-side with the current weight-based approach on at least:
  - `decision_f1`
  - `building_type_f1`
  - `unit_number_f1`
  - `unit_recall`
  - `OVER_SENSITIVE_REVIEW`
- the first version must not aim to replace the full parsing chain as a black box; the existing responsibilities of:
  - parser mainline
  - reference matching
  - canonical assetization
  must remain intact

### Requirement 9: The console must support a decision minority-label batch entry point
The backend already supports `decision minority-label` seeding, but the console must expose a direct frontend entry point so the capability does not remain API-only.

Delivery requirements:
- the `/review` page must be able to trigger `decision minority-label` batch generation when the queue is empty or when targeted decision minority-label reinforcement is needed
- the `Batch Management` page must provide a dedicated button that distinguishes:
  - general review batches
  - `decision minority-label` batches
- the frontend trigger must call the dedicated endpoint directly instead of reusing the old `seed_review_batch`
- after generation, the operator must be able to refresh or jump directly into the review queue

### Requirement 10: The review page must support structured address-field correction
When the address problem is not only `building_type / unit`, but also a parsing failure in `street_number / street_name / city / province / postal_code`, the review page must allow direct structured correction.

Delivery requirements:
- the `/review` page must display and allow editing of:
  - `street_number`
  - `street_name`
  - `city`
  - `province`
  - `postal_code`
  - `building_type`
  - `unit_number`
- `submit_review` must write those structured corrections into `gold_label.label_json`
- the new structured corrections must not remain only in free-form notes; they must enter the downstream training and benchmark flow
- for cases such as `two Heritage Court ...`, human correction must become formal gold instead of being preserved only as commentary

## 5. Expected Benefit Mapping

### Task 1: Controlled incremental data intake
- Expected benefit:
  - move the system from a historical-data optimization tool to a production system that can continuously handle new address data
- Primary metrics:
  - fresh batch processed count
  - fresh batch accepted count
- Secondary metrics:
  - batch-level processing completeness

Planned technical methods:
- **Configurable DB historical backfill**
  - allow console ingestion to switch from API mode to DB mode and point directly at historical address tables such as `address_raw_history`.
  - benefit: historical address backfill can enter the main processing loop without separate one-off scripts.
- **Console-side ingestion configuration switching**
  - add a console control that can switch between `API / DB` ingestion modes and maintain DB table, cursor, tie-breaker, and field-mapping settings.
  - benefit: historical backfill and day-to-day third-party incremental intake can be switched safely inside the console instead of relying on manual `.env.local` edits.
- **Configuration persistence and pre-sync synchronization**
  - after moving ingestion settings into the new `System Settings` page, add explicit save behavior, unsaved-change visibility, and automatic synchronization of pending ingestion settings before `Start Sync`.
  - benefit: prevents the UI from showing `API` mode while the backend still runs with the old `DB` runtime config, reducing misleading import failures after the console refactor.
- **Composite cursor pagination**
  - for historical tables with many duplicate `created_at` values, page by a composite cursor such as `created_at + order_id` instead of a single timestamp cursor.
  - benefit: avoids row loss during 180k-scale DB backfill.
- **Dedicated historical backfill source isolation**
  - use a distinct source name for DB historical backfill so it does not mix with the third-party incremental API stream.
  - benefit: makes fresh-vs-historical validation and training-impact analysis cleaner.

### Task 2: Fresh-data quality validation
- Expected benefit:
  - prove whether the current model and rules generalize to new data
- Primary metrics:
  - fresh decision quality
  - fresh building_type quality
  - fresh unit recovery quality
- Secondary metrics:
  - fresh review rate
  - fresh reject rate

### Task 3: Reference coverage gap detection
- Expected benefit:
  - turn reference coverage from “it seems incomplete” into something quantifiable, sampleable, and extensible
- Primary metrics:
  - fresh no-reference count
  - fresh reference-backed ratio
- Secondary metrics:
  - reference-gap reason buckets
  - fresh hotspot evidence count

### Task 4: Fresh-data canonical/reference reporting
- Expected benefit:
  - create a direct quality comparison between fresh data and the historical baseline
- Primary metrics:
  - fresh canonical gap
  - fresh asset-quality report generation stability
- Secondary metrics:
  - fresh hotspot explainability

### Task 5: Fresh-gold expansion readiness
- Expected benefit:
  - let the next training round gain real high-value supervision from new data
- Primary metrics:
  - fresh hard-sample candidate count
  - fresh review candidate count
- Secondary metrics:
  - new pattern discovery count

### Task 6: Balanced human-sample selection
- Expected benefit:
  - prevent human-review data from being overly dominated by hardest cases and pulling the model in the wrong direction
  - let gold serve both correction supervision and distribution calibration
- Primary metrics:
  - correction-pool sample count
  - calibration-pool sample count
  - fresh balanced review candidate count
- Secondary metrics:
  - hard-case ratio in new gold
  - calibration coverage ratio
  - double-number-house negative-sample count

### Task 7: Decision-boundary calibration and historical gold semantic decontamination
- Expected benefit:
  - improve `decision_f1` without giving back the recovered apartment/unit quality
  - prevent non-semantic historical task labels from distorting decision-threshold learning
- Primary metrics:
  - `decision_f1`
  - `review_rate`
- Secondary metrics:
  - `reject_rate`
  - `GENERAL_MISMATCH` error-bucket count
  - `OVER_SENSITIVE_REVIEW` error-bucket count

### Task 8: Supervised model baseline layer
- Expected benefit:
  - upgrade the current “learned-weight system” into a true discriminative model layer
  - improve learning of complex boundary interactions beyond manual threshold tuning
- Primary metrics:
  - `decision_f1`
  - `building_type_f1`
  - candidate reranking win rate
- Secondary metrics:
  - `unit_number_f1`
  - `unit_recall`
  - `OVER_SENSITIVE_REVIEW`
  - model-vs-weights delta on fresh historical data

Planned technical methods:
- **Tabular supervised baseline**
  - use `CatBoost`, `HistGradientBoosting`, or a comparable GBDT model to build a supervised baseline over existing structured features.
  - benefit: improves complex interaction learning while preserving explainability and engineering control.
- **Parallel dual-track evaluation**
  - run the new model layer in parallel with the current `decision_policy / candidate_feature_weights / candidate_pair_weights` approach instead of replacing it immediately.
  - benefit: explicitly measures whether supervised models are actually better than the current learned-weight system.
- **Phased task introduction**
  - phase 1: `decision`
  - phase 2: candidate reranking
  - phase 3: evaluate whether `building_type` should become a separate supervised model
  - benefit: lowers replacement risk and keeps regressions easier to localize.

### Task 9: Console decision minority-label entry completion
- Expected benefit:
  - upgrade the `DecisionModel` minority-label reinforcement ability from “backend available” to “console directly operable”
- Primary metrics:
  - minority-label batch generated count
  - minority-label labeled count
- Secondary metrics:
  - review queue visibility
  - human-to-gold turnaround time

Planned technical methods:
- **Empty-queue direct generation from the review page**
  - add a `Generate Decision Minority Batch` button to the empty-state of `/review`.
  - benefit: when no regular review task is available, reviewers can directly pull high-value decision minority-label samples instead of falling back to the legacy generic batch.
- **Dedicated Batch Management entry**
  - add a dedicated button in the batch management page that calls `seed-decision-minority-labels`.
  - benefit: operators can clearly distinguish “general review batch” from “DecisionModel minority-label reinforcement batch”.
- **Explicit frontend route split**
  - the frontend button must call `/api/v1/review/seed-decision-minority-labels` directly instead of reusing the old `jobs/trigger -> seed_review_batch` path.
  - benefit: avoids a misleading UI path that appears to support decision minority-label generation but still seeds the wrong sample pool.
- **Existing-source exclusion before limit truncation**
  - `decision minority-label` seeding must exclude already reviewed/queued source_ids before applying the final limit cut.
  - benefit: prevents false-empty behavior where the pool still has new samples but the first N candidates are already consumed.
- **Address-text deduplication for minority-label samples**
  - `decision minority-label` seeding must not dedupe only by `source_id`; it must also dedupe by normalized `raw_address_text`.
  - the comparison scope must cover all already reviewed/queued address texts in the workspace, not only the current candidate `source_id` subset.
  - benefit: prevents the same address from entering human review multiple times through different `raw_id` values or repeated imports, protecting minority-label training quality.

### Task 10: Structured field correction support in the review page
- Expected benefit:
  - allows parser/normalization failures to become structured gold instead of degrading into free-form notes
- Primary metrics:
  - structured-review correction count
  - street-number/street-name corrected gold count
- Secondary metrics:
  - number-word normalization sample count
  - review-to-gold structured completeness ratio

Planned technical methods:
- **Structured field editing on the review page**
  - add `street_number / street_name / city / province / postal_code` inputs to the review page, prefilled from current parser or LLM output.
  - benefit: reviewers can directly fix structure-level mistakes instead of only changing `building_type/unit`.
- **Structured gold submission extension**
  - extend `submit_review` so the resulting `gold_label` stores the structured field corrections alongside decision/building_type/unit.
  - benefit: training, benchmark, and reranking can directly consume these corrected structured truths.
- **Number-word address correction loop**
  - for examples like `two Heritage Court ...` or `Fourteen fifty six ...`, the corrected civic number and street can become formal gold.
  - benefit: provides real supervision for future number-word normalization and parser-learning work.

### Task 11: Post-minority-batch DecisionModel retraining and effect validation
- Expected benefit:
  - verify whether the two reviewed minority-label batches actually improve minority-class learning in the `DecisionModel`
- Primary metrics:
  - normalized decision label balance
  - `model_macro_f1`
  - per-label precision-recall-f1 for `review` and `reject`
- Secondary metrics:
  - heuristic-vs-model delta
  - minority-label support count

Planned technical methods:
- **Immediate baseline rerun after reviewed minority labels**
  - rerun the decision baseline training and comparison as soon as the new human gold lands instead of relying on pre-review conclusions.
  - benefit: ensures the ML evaluation reflects the newest supervision distribution rather than an outdated snapshot.
- **Minority-label balance re-audit**
  - emit a dedicated balance artifact for the normalized `accept/review/reject` distribution.
  - benefit: avoids confusing “many reviews were completed” with “the DecisionModel actually learned review/reject boundaries”.

Current implementation and validation status:
- the latest normalized human-gold `decision` distribution has improved to:
  - `accept = 1322`
  - `review = 47`
  - `reject = 36`
- the live `CatBoost` baseline has been retrained and compared:
  - `eval_macro_f1 = 0.4908`
  - `model_accuracy = 0.8512`
  - `model_macro_f1 = 0.5536`
  - `heuristic_accuracy = 0.7120`
  - `heuristic_macro_f1 = 0.2818`
- this confirms a real ML gain from the reviewed minority-label batches:
  - the model now clearly outperforms the current heuristic `decision` logic
  - `review/reject` minority classes are starting to be learned instead of only `accept`

Next closure direction:
- improve minority-class precision, especially false-positive control for `review/reject`
- connect the `DecisionModel` to shadow-assist / compare before any runtime replacement
- continue minority-label reinforcement, but prevent repeated addresses from re-entering review

## 6. Technical Implementation Evolution

### Requirement 1: Controlled incremental address-data intake
Planned technical methods:
- **Batch-isolated import**
  - third-party incremental data enters ingestion and cleaning as separate batches
  - benefit: fresh data can be tracked and analyzed independently
- **Batch-level processing linkage**
  - ingestion / cleaning / assetization results are linked back to batch scope
  - benefit: fresh vs. historical data does not get mixed during analysis

Expected code carriers:
- `ingestion/service.py`
- `pipelines/import_csv.py`
- `services/business_service.py`

### Requirement 2: Fresh-data quality validation
Planned technical methods:
- **Fresh-data subset metrics**
  - compute parsing / validation / assetization metrics on the new-data subset only
  - benefit: separates historical performance from fresh-data performance
- **Fresh-vs-baseline comparison view**
  - place fresh-subset metrics next to current overall / active baseline metrics
  - benefit: makes generalization regressions visible

Expected code carriers:
- `learning/evaluator.py`
- `services/business_service.py`
- `api/routes/business.py`

### Requirement 3: Fresh reference coverage gap detection
Planned technical methods:
- **Fresh no-reference bucketization**
  - decompose fresh-data no-reference cases into no-reference, locality/street mismatch, and parse-correct-but-reference-missing
  - benefit: prevents fresh-data reference gaps from being misread as parser defects
- **Fresh sample-level gap evidence**
  - emit row-level evidence for fresh-data reference gaps
  - benefit: provides direct input for later reference expansion

Expected code carriers:
- `services/asset_service.py`
- `core/reference.py`

### Requirement 4: Fresh-data canonical/reference reporting
Planned technical methods:
- **Fresh-scope reporting**
  - generate a report that is restricted to the new-data batch/source scope
  - benefit: isolates new-data quality from global quality
- **Historical-baseline side-by-side reporting**
  - show fresh-subset results alongside the current system-wide baseline
  - benefit: makes real generalization comparisons possible

Expected code carriers:
- `services/asset_service.py`
- `api/routes/business.py`

### Requirement 5: Fresh-gold expansion readiness
Planned technical methods:
- **New-pattern candidate discovery**
  - detect new apartment/unit hard cases, reference gaps, and building_type boundary samples inside fresh data
  - benefit: the next gold expansion will not depend only on old data
- **Fresh review seeding**
  - seed review/gold candidates directly from the fresh-data subset
  - benefit: connects new data directly into the continuous-learning loop

Expected code carriers:
- `learning/gold.py`
- `api/routes/review.py`

## 7. In Scope
- incremental address-data intake and batch tracing
- fresh-data parsing / assetization quality validation
- fresh reference coverage gap detection
- fresh-data canonical/reference reporting
- fresh-gold review candidate preparation

## 8. Out Of Scope
- large operations-system UI redesign
- old release center / reports center defect fixes
- multi-country canonical strategy
- full reference-platform redesign
- returning parser/unit rule growth to the main optimization path

## 9. Acceptance Criteria

### Fresh-Data Quality Acceptance
1. the system can distinguish fresh-data vs historical-data processing results
2. the system can output a fresh-data canonical/reference quality report
3. the system can quantify fresh-data reference gaps

### Engineering Acceptance
4. incremental data can enter the processing pipeline in controlled batches
5. fresh-data gap diagnostics include sample-level evidence
6. fresh-data review/gold candidates can enter the later continuous-learning loop directly

## 10. Technical Implementation Evolution

This section explains how one requirement may be delivered through multiple technical rounds.  
Future work must be attached back to one of these requirement tracks, instead of only saying “Phase 8 was optimized again.”

### Requirement 1: Controlled incremental address-data intake
Planned technical methods:
- **Batch-isolated import**
  - third-party incremental data is first formed into an explicit batch and only then enters ingestion and cleaning
  - benefit: fresh data can be tracked and analyzed separately from historical data
- **Batch-level processing linkage**
  - ingestion, cleaning, and assetization outputs are explicitly linked to batch/source scope
  - benefit: later fresh-data reports, review seeding, and reference-gap analysis all have a stable filter boundary
- **Incremental import idempotency**
  - repeated intake of the same third-party batch is controlled through source-level keys, import status, or uniqueness semantics
  - benefit: “new batches” remain truly incremental instead of reprocessing old data and distorting fresh-data metrics

Expected code carriers:
- `ingestion/service.py`
- `pipelines/import_csv.py`
- `services/business_service.py`

Evolution rule:
- future work under this requirement must explicitly state whether it is improving:
  - batch isolation coverage
  - import idempotency
  - or batch-to-processing result linkage

### Requirement 2: Fresh-data quality validation
Planned technical methods:
- **Fresh-data subset metrics**
  - parsing / validation / assetization metrics are computed on the fresh batch/source subset only
  - benefit: separates “stable on historical data” from “stable on new data”
- **Fresh-vs-baseline comparison view**
  - fresh-subset metrics are shown alongside the current baseline in the same view
  - benefit: makes generalization regressions visible without manual report stitching
- **Fresh acceptance funnel**
  - fresh rows are split into ingest -> cleaned -> accepted -> promotable funnel stages
  - benefit: clarifies whether the main loss is in parsing, decisioning, canonicalization, or reference coverage

Expected code carriers:
- `learning/evaluator.py`
- `services/business_service.py`
- `api/routes/business.py`

Evolution rule:
- future work under this requirement must explicitly state whether it is improving:
  - fresh-subset metric coverage
  - baseline comparison
  - or funnel-stage explainability

### Requirement 3: Add reference coverage gap detection for fresh data
Planned technical methods:
- **Fresh no-reference bucketization**
  - fresh-data non-reference cases are decomposed into true no-coverage, locality/street mismatch, and parse-correct-but-reference-missing
  - benefit: prevents reference coverage gaps from being misread as parser-quality issues
- **Fresh sample-level gap evidence**
  - fresh reference-gap rows are emitted with row-level evidence, including raw text and structured locality/street clues
  - benefit: later reference expansion can start directly from concrete evidence
- **Fresh reference hotspot clustering**
  - fresh non-reference rows are clustered by locality / building / street pattern
  - benefit: later reference expansion can target high-yield hotspots instead of isolated one-off rows

Expected code carriers:
- `services/asset_service.py`
- `core/reference.py`

Evolution rule:
- future work under this requirement must explicitly state whether it is improving:
  - reason decomposition
  - sample evidence
  - or hotspot clustering

### Requirement 4: Add a fresh-data canonical/reference report
Planned technical methods:
- **Fresh-scope reporting**
  - a dedicated report is generated for a batch/source-scoped fresh-data subset instead of relying only on global asset quality
  - benefit: fresh-data canonical/reference issues are not hidden inside historical totals
- **Historical-baseline side-by-side reporting**
  - the same report shows both fresh-subset results and the current overall baseline
  - benefit: makes generalization comparison direct and reviewable
- **Fresh actionable evidence**
  - the report emits fresh no-reference examples, fresh review candidates, and fresh hotspot buckets
  - benefit: the report becomes direct input for the next repair loop instead of only a status view

Expected code carriers:
- `services/asset_service.py`
- `api/routes/business.py`

Evolution rule:
- future work under this requirement must explicitly state whether it is improving:
  - fresh-scope reporting
  - baseline comparison
  - or actionable evidence output

### Requirement 5: Add fresh-gold expansion readiness
Planned technical methods:
- **New-pattern candidate discovery**
  - the system detects new apartment/unit hard cases, building_type boundary samples, and reference-coverage gaps inside fresh data
  - benefit: later training can learn from new-distribution problems instead of only old hard cases
- **Fresh review seeding**
  - review/gold candidates are seeded directly from the fresh-data subset
  - benefit: new data enters the human-in-the-loop loop immediately
- **Fresh hard-sample density profiling**
  - fresh review/gold candidates are bucketed and profiled by pattern density
  - benefit: the system can explain what new problem classes were introduced by the new batch

Expected code carriers:
- `learning/gold.py`
- `api/routes/review.py`

Evolution rule:
- future work under this requirement must explicitly state whether it is improving:
  - new-pattern discovery
  - review seeding
  - or fresh hard-sample profiling

### Requirement 6: Add balanced human-sample selection
Planned technical methods:
- **Dual-pool sampling**
  - split human-review intake into:
    - correction pool: highest-value hardest cases
    - calibration pool: more production-like regular samples
  - benefit: prevents hardest cases from dominating new gold on their own.
- **Stratified ratio sampling**
  - define target ratios across `single_unit`, `multi_unit`, double-number house, numbered-road, reference-gap, and similar strata.
  - benefit: lets review output both fix boundaries and preserve a realistic training distribution.
- **Fresh-vs-historical separated sampling**
  - sample fresh imported data separately from historical stock, then combine them under explicit ratios.
  - benefit: prevents fresh-data validation from being drowned by the old review pool.
- **Explicit negative-sample reinforcement**
  - build a dedicated negative-sample pool for addresses that look like unit cases but are actually not unit cases, such as double-number houses and numbered-road houses.
  - benefit: directly addresses the boundary that most easily drifts in apartment/unit learning.
- **Sample-pool structure profiling**
  - emit a structured summary of the new gold mix before freeze/training.
  - benefit: makes “this round is too hard-case heavy” visible before the model is retrained.

Expected code carriers:
- `learning/gold.py`
- `services/review_service.py`
- `api/routes/review.py`
- `learning/trainer.py`

Evolution rule:
- future work under this requirement must explicitly state whether it is improving:
  - pool splitting
  - ratio control
  - negative-sample reinforcement
  - or pre-training sample-structure diagnostics

### Requirement 7: Add decision-boundary calibration and historical gold semantic decontamination
Planned technical methods:
- **Historical non-semantic task-type normalization**
  - strip labels such as `calibration_accept`, `unit_boost_accept`, and `hard_correction_pending` out of training semantics and keep them only as sample-pool evidence.
  - benefit: the training loop will no longer confuse workflow provenance with semantic supervision.
- **Decision-threshold context completion**
  - include:
    - task_type
    - notes/sample_pool
    - raw_address_text
    - building_type
  in decision-policy learning.
  - benefit: `accept/review/reject` thresholds are calibrated with real sample context, not only confidence values.
- **Legacy review downweighting**
  - explicitly reduce the influence of older `review` hardest-case samples, especially rows without clean sample-pool provenance.
  - benefit: prevents early review-process bias from continuing to pull the candidate toward the wrong decision boundary.
- **Decision-only regression validation**
  - validate:
    - `decision_f1`
    - `GENERAL_MISMATCH`
    - `OVER_SENSITIVE_REVIEW`
  after each iteration.
  - benefit: separates “address parsed correctly but final action is wrong” from apartment/unit parsing quality.
- **Legacy review accept recovery**
  - specifically recover historically reviewed rows that should now become `accept` by enhancing:
    - incomplete-candidate downweighting
    - complete-street candidate promotion
    - prefix/suffix noise stripping
    - reversed civic order recovery
    - leading bare-unit comma apartment recovery
    - glued explicit-unit + civic recovery
    - commercial/prefix-noise glued-tail repair

### Requirement 8: Add a supervised model baseline layer
Planned technical methods:
- **Keep the parser/reference mainline, add a supervised model layer**
  - do not replace the current parsing, reference, and canonical mainline; instead, add a discriminative model layer on top of it.
  - benefit: preserves the existing engineering strengths while materially upgrading learning capacity.
- **Structured-feature-first modeling**
  - the first version should rely on existing stable runtime features such as:
    - parser confidence
    - parser pattern
    - unit_source
    - reference score
    - parser_disagreement
    - numbered-road flag
    - explicit/commercial hints
  - benefit: achieves stronger supervision with lower implementation risk.
- **Prefer tabular models before neural models**
  - the first stage should prioritize `CatBoost` / `GBDT` / `HistGradientBoosting`, not an end-to-end Transformer parser.
  - benefit: better aligned with current gold size, structured task shape, and explainability requirements.
- **CatBoost as the primary baseline implementation**
  - in the current implementation, the first `DecisionModel` baseline now prefers `CatBoost`, and only falls back to the `numpy/scipy` softmax baseline when the preferred library is unavailable or fails.
  - benefit: satisfies the “best-fit library first” requirement while preserving engineering continuity under environment constraints.
- **Parallel baseline evaluation**
  - the new model layer must be benchmarked in parallel with the current weight-based approach on benchmark, shadow, and fresh historical subsets.
  - benefit: prevents “adding ML for its own sake” and keeps replacement evidence-driven.
- **Environment-safe baseline fallback**
  - when `sklearn/CatBoost` is not installed, the first `DecisionModel` baseline may fall back to a `numpy/scipy` softmax baseline so the offline training loop still runs.
  - benefit: the next-generation ML rollout is not blocked by one missing dependency before dataset, feature, and label assumptions are validated.

Expected code carriers:
- `learning/trainer.py`
- `learning/reranking_trainer.py`
- `learning/evaluator.py`
- `api/server.py`
- `learning/supervised_baseline.py`

Evolution rule:
- future work must explicitly state whether it is improving:
  - the `decision` supervised model
  - the candidate reranking supervised model
  - the `building_type` supervised model
  - or a later neural reranker
  - and whether it is improving:
    - dataset export
    - feature vectorization
    - the primary CatBoost baseline
    - baseline training fallback
    - or parallel evaluation evidence
    - route-only/no-civic recovery
    - single-unit parser-disagreement relaxation
    - decision-calibration review batch generation
    - ordinal-street plus trailing residential-keyword recovery
    - compound residential-unit keyword recovery
    - repeated unit-civic apartment recovery
    - repeated civic single-unit acceptance recovery
    - glued token spacing repair
    - malformed explicit-unit prefix recovery
    - leading explicit-unit and residential-keyword civic recovery
    - no-fallback explicit-unit city-tail recovery
  - benefit: directly compresses `OVER_SENSITIVE_REVIEW` without regressing the apartment/unit mainline.

Expected code carriers:
- `learning/trainer.py`
- `learning/evaluator.py`
- `services/review_service.py`
- `core/common.py`
- `api/server.py`

Evolution rule:
- later iterations must state whether they are improving:
  - historical task-type normalization
  - decision-threshold context
  - legacy review downweighting
  - legacy review accept recovery
  - or decision-only regression validation

## 11. Execution Order

1. First establish batch isolation and batch-level result linkage for incremental intake.
2. Then add fresh-data subset metrics and fresh-vs-baseline comparison.
3. Next add fresh reference-gap bucketization and sample-level evidence.
4. Then generate a dedicated fresh-data canonical/reference report.
5. Finally seed high-value fresh review/gold candidates into the later continuous-learning loop.
6. Add balanced review-pool composition and stratified ratio control so hardest cases do not dominate the new gold mix.
7. After the apartment/unit mainline is recovered, separately recover `decision_f1` and remove historical non-semantic task-type pollution from decision training.
8. Implement the first supervised `decision` baseline by adding dataset export, structured-feature vectorization, and parallel benchmark comparison without replacing the runtime mainline yet.

## 12. Residual Problems That Triggered Phase 8

Phase 7 largely closed the canonical/reference mainline on known internal data, but it did not yet solve the following:

1. **the system still cannot reliably separate fresh data from historical data**
   - most quality judgment is still dominated by global totals.
   - this can hide real regressions on new data.

2. **reference coverage will reappear as a bottleneck on fresh data**
   - Phase 7 cleared actionable gaps for the current known pool.
   - once third-party incremental data arrives, reference coverage gaps will reappear in real production form.

3. **the continuous-learning loop still lacks a real new-data source**
   - current review/gold/training inputs are still mainly driven by the historical processing pool.
   - without fresh data entering that loop, the system will gradually lose adaptation to new distribution patterns.

4. **the current human-review mix is visibly hard-case heavy**
   - those samples are valuable for correction, but not suitable to represent the full training distribution by themselves.
   - without a calibration pool and ratio control, the model is more likely to drift on boundary patterns.

## 13. Risks And Watchpoints

1. **batch isolation is not strict enough**
   - if fresh and historical data are mixed at write time, all fresh-data reports become misleading.

2. **new-data evaluation still relies only on global averages**
   - this can make the system look stable while the fresh subset is actually regressing.

3. **reference gaps are confused with parser defects**
   - if fresh no-reference cases are not bucketed by reason, later optimization will misclassify coverage problems as parsing problems.

4. **fresh review seeding degenerates back into old repeated samples**
   - if the seeding logic is not fresh-data aware, the system will drift back into mining the old review pool.

5. **insufficient calibration samples cause training-distribution drift**
   - if new gold continues to be dominated by review/hardest cases, the model will keep drifting on apartment/unit vs double-number-house boundaries.

6. **historical workflow labels may continue to pollute decision training**
   - if task labels such as `calibration_accept`, `unit_boost_accept`, or `hard_correction_pending` are still treated as semantic supervision, `decision_f1` may remain artificially low even when apartment/unit parsing recovers.

7. **fresh historical review is now dominated by two recoverable parser/decision patterns**
   - the 186k historical backfill completed with `5,728` review rows, and the dominant bucket is:
     - `single_unit`
     - `Parser confidence is moderate; review is safer.`
   - early sample review shows two especially high-value sub-patterns:
     - repeated leading unit-civic apartment rows such as `505-1000 MICMAC BLVD 505 DARTMOUTH NS`
     - repeated civic single-unit rows such as `33 MOUNTAIN MAPLE DR 33 TIMBERLEA NS`
   - these should be handled as a dedicated decision/parser recovery loop rather than treated as generic review noise.

## 14. Completion Criteria

Phase 8 can be considered complete when all of the following are true:

1. third-party incremental address data can be imported in stable batches and enter the processing pipeline.
2. fresh-subset processing / quality / assetization results are independently viewable.
3. fresh reference gaps can be bucketed by reason and emitted with sample evidence.
4. a fresh canonical/reference report can be generated reliably and compared side-by-side with the historical baseline.
5. fresh-data review/gold candidates can be seeded reliably, without collapsing back into repeated historical samples.
6. fresh-gold review candidates can feed directly into later human review and training
7. new human-review batches can be generated with explicit correction-pool vs calibration-pool composition, and the resulting gold mix is diagnosable before training.
8. `decision_f1` recovers to a level that can compete with the active baseline without sacrificing `building_type_f1 / unit_number_f1 / unit_recall`.
9. the first `DecisionModel baseline` can stably export training data, train an offline supervised baseline, and compare it in parallel against the current weight-based approach on benchmark / shadow evidence.

## 10. Risks And Watchpoints
- if fresh data cannot be isolated by batch, fresh-data analysis will be distorted
- if data is imported without a fresh-data quality view, new problems will be lost inside overall aggregates
- if reference coverage gaps are not decomposed, later reference expansion will fall back into blind tuning

## 11. Completion Criteria
This phase can be considered complete when:
- new incremental data can be ingested stably
- fresh-data canonical/reference quality is independently observable
- fresh reference gaps are quantifiable and accompanied by sample-level evidence
- fresh review/gold candidates can flow into the later continuous-learning loop

## 12. Post-Execution Requirement
This document is an optimization-requirements and execution-plan document, not an execution summary.

After execution, the outcome must be written into a separate:
- execution summary
- update summary
- or phase summary

Execution results must not be backfilled into this plan.
