# AddressForge Iteration Execution Plan - 2026-04-29 (Phase 5: Apartment Unit Hard-Sample Densification And Candidate Quality Lift)

## Document Info
- Document Type: Execution Plan / Optimization Requirements
- Effective Date: 2026-04-29
- Owner: AddressForge Product / Engineering
- Status: Completed
- Trigger: Phase 4 completed the candidate-level learning and runtime-consumption loop, but `unit_number_f1` and `unit_recall` did not materially improve again. That means the current bottleneck has shifted from “learning path not wired” to “insufficient high-value apartment/unit gold density and unstable candidate quality.”

## 1. Current Context & Problem Definition
Phase 4 already completed:
- candidate-level training sample construction
- candidate feature learning
- candidate pairwise win/loss learning
- real runtime consumption of candidate-level learned weights

The current state now implies two things:

1. **the model-learning path is already wired**
   the system can now use gold to drive candidate-level ranking learning.

2. **the next bottleneck is data density and candidate quality**
   the lack of additional metric lift now looks more like:
   - apartment/unit high-value gold is still too sparse
   - some hard cases have candidates, but the candidates are still not separable enough
   - candidate quality is improving more slowly than the learning pipeline itself

Therefore, the next core problem is:

**to keep prioritizing apartment unit parsing success, but shift the method from “keep wiring learning signals” to “increase high-value apartment/unit sample density + improve candidate quality + train from more focused hard cases.”**

## 2. Overall Goal
The goals for this phase are:

1. materially increase high-value apartment/unit hard-case gold density
2. focus training more directly on the error patterns that are still suppressing `unit_number_f1` and `unit_recall`
3. improve parser candidate separability and candidate quality rather than only adding more learned weights
4. continue prioritizing:
   - `unit_number_f1`
   - `unit_recall`
   - `building_type_f1`

## 3. Core Optimization Targets

### 3.1 Apartment Unit Hard-Sample Densification
The system needs to systematically strengthen high-value samples such as:
- trailing bare-number units
- glued `APT/UNIT/ROOM/FLOOR`
- `A/B`, `12A`, `203B`
- house with sub-unit / secondary suite
- missing commas, wrong order, city/province tail pollution

### 3.2 Candidate Quality Improvement
The ranking layer can now work, but the candidate set itself still needs further quality improvement:
- candidates should more often contain one clearly better apartment/unit interpretation
- avoid having multiple candidates that are equally incomplete or equally wrong
- keep moving unit recovery earlier into the parse stage

### 3.3 Hard-Case-Driven Training Loop
Training should no longer expand mainly through average gold distribution. It should prioritize:
- the latest evaluation error buckets
- replay / shadow rows that diverge from current behavior
- apartment/unit samples where LLM and system disagree

## 4. Concrete Requirements

### Requirement 1: High-value apartment/unit samples must be expanded deliberately
The next round of manual review samples should come first from:
- `unit_number` error cases
- `multi_unit` misclassification cases
- parser-disagreement samples that contain unit hints
- apartment/unit samples where LLM and system disagree

Delivery requirements:
- active-learning queue can output dedicated apartment/unit hard-sample batches
- queue generation continues to avoid already reviewed samples

### Requirement 2: Candidate quality must keep improving
At parse time, the system should continue moving unit recovery earlier, rather than relying heavily on validate-time fallback.

Delivery requirements:
- a higher share of parse candidates should directly carry the correct `unit_number`
- apartment/unit candidates should become easier for the ranking model to separate

### Requirement 3: Training must prioritize hard cases
Training should no longer learn mostly from average gold distribution. It should increase the weight of hard cases.

Delivery requirements:
- training input can distinguish routine samples from hard samples
- hard samples can be counted and replayed separately

### Requirement 4: Evaluation must target the apartment/unit primary objective
Evaluation should explicitly answer:
- which apartment/unit error types still suppress the metrics
- whether the current candidate set is actually separable enough
- whether new gains come from:
  - better candidate quality
  - or denser hard-sample supervision

## 4A. Technical Implementation Evolution

### Requirement 1: High-value apartment/unit samples are deliberately expanded
Technical methods already used:
- **Error-bucket-driven sampling**
  - hard samples are drawn first from `unit_number` errors, `building_type` errors, and LLM/system conflict samples
  - benefit: manual review is concentrated on the samples most likely to improve unit metrics
- **Deduplicated review-batch generation**
  - queue generation avoids already-reviewed and historically duplicated samples
  - benefit: gold growth increases effective density instead of repeating work

Current code carrier:
- `learning/gold.py`
- `api/routes/review.py`

### Requirement 2: Candidate quality keeps improving
Technical methods already used:
- **Unit recovery is moved earlier into parse**
  - unit recovery is pushed into parse candidates instead of relying mostly on validate-time fallback
  - benefit: candidate sets become more separable
- **Apartment/unit pattern correction**
  - glued `APT/UNIT`, trailing bare-number units, and house sub-unit patterns are repaired first
  - benefit: candidate sets more often contain one clearly better answer

Current code carrier:
- `core/common.py`
- `api/server.py`

### Requirement 3: Training prioritizes hard cases
Technical methods already used:
- **Hard-sample profile explicitization**
  - the training artifact reports hard-sample ratio, unit-hint count, and multi-unit count
  - benefit: average gold distribution no longer hides whether the phase truly trained on hard cases
- **Hard-case source traceability**
  - routine samples and high-value apartment/unit hard samples are separated
  - benefit: later gains can be attributed to denser supervision rather than generic retraining

Current code carrier:
- `learning/trainer.py`

### Requirement 4: Evaluation targets the apartment/unit main objective
Technical methods already used:
- **Unit-driven metric acceptance**
  - `unit_number_f1`, `unit_recall`, and `building_type_f1` remain the phase success metrics
- **Gain-source breakdown**
  - each round separates gains from hard-sample density vs. gains from candidate-quality improvement
  - benefit: avoids attributing every gain to training by default

Current code carrier:
- `learning/evaluator.py`
- `learning/trainer.py`

## 5. In Scope
- apartment/unit high-value sample expansion
- hard-sample generation and batch management
- continued parser candidate quality improvement
- hard-case-driven training input strengthening
- apartment/unit-focused evaluation and diagnosis

## 6. Out Of Scope
- operations-system UI/workflow redesign
- reports-center fixes
- commercial as the primary optimization direction
- country abstraction and multi-country support
- large new platform features

## 7. Acceptance Criteria

### Metric Acceptance
1. `unit_number_f1` improves again
2. `unit_recall` improves again
3. `building_type_f1` does not materially regress

### Data And Training Acceptance
4. the new gold set shows a materially higher share of apartment/unit hard cases
5. training input can explicitly identify hard-sample sources
6. candidate-quality diagnostics can explain the major remaining apartment/unit error buckets

## 8. Risks And Watchpoints
- if manual review continues to focus mostly on ordinary houses, Phase 5 gains will be diluted
- if parser candidate quality does not improve enough, additional hard samples may still produce only limited gains
- if candidates are already good enough but gold remains too sparse, the bottleneck will stay at supervision density

## 9. Completion Criteria
This phase can be considered complete when:
- apartment/unit hard-sample gold density is materially higher
- training input clearly prioritizes high-value unit error cases
- parser candidate quality or separability improves again
- `unit_number_f1` and `unit_recall` increase again

## 10. Post-Execution Requirement
This document is an optimization-requirements and execution-plan document, not an execution summary.

After execution, the outcome must be written into a separate:
- execution summary
- update summary
- or phase summary

Execution results must not be backfilled into this plan.
