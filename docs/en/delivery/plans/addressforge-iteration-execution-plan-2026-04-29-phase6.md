# AddressForge Iteration Execution Plan - 2026-04-29 (Phase 6: Residential Unit Label Consistency And Semantic Disambiguation)

## Document Info
- Document Type: Execution Plan / Optimization Requirements
- Effective Date: 2026-04-29
- Owner: AddressForge Product / Engineering
- Status: Completed
- Trigger: Phase 5 further improved `unit_number_f1` and `unit_recall`, and relabeling restored `building_type_f1`. The next bottleneck has now shifted to inconsistent human-gold labeling and mixed semantics in tokens such as `Upper/Lower/Apt/Unit`.

## 1. Current Context & Problem Definition
After Phase 5, the system now has:
- targeted apartment/unit hard-sample expansion
- hard-sample-driven training
- metric recovery after relabel review

The current state implies two things:

1. **high-value apartment/unit sample expansion works**
   `unit_number_f1`, `unit_recall`, and `building_type_f1` have all improved or recovered.

2. **the next problem is no longer “too few samples,” but “unstable sample semantics”**
   the current gold set already contains cases where:
   - strong apartment/unit signals are labeled as `single_unit`
   - `Upper/Lower` sometimes mean a unit and sometimes mean only part of a place name
   - the model and rules can learn a polluted boundary from inconsistent labels

Therefore, the next core problem is:

**to stabilize the semantic boundary between `single_unit` and `multi_unit`, and to disambiguate residential sub-unit tokens from geographic modifiers more reliably.**

## 2. Overall Goal
The goals for this phase are:

1. establish a building-type label-consistency scan and relabel-review mechanism
2. reduce gold pollution from rows that clearly carry unit hints but are labeled as `single_unit`
3. separate true residential sub-unit signals from geographic `Upper/Lower` place-name tokens
4. while protecting the current unit gains, continue to stabilize or improve:
   - `building_type_f1`
   - `unit_number_f1`
   - `unit_recall`

## 3. Core Optimization Targets

### 3.1 Label Consistency Governance
The system must proactively identify and surface high-risk label inconsistencies such as:
- `single_unit` + strong apartment/unit text signals
- `multi_unit` + no unit evidence
- `commercial` + clearly residential patterns

### 3.2 Semantic Disambiguation For Unit-Like Tokens
The system must distinguish more cleanly between:
- `Upper/Lower` used as a unit
- `Upper/Lower` used only as part of a place name
- `Apt/Unit/Suite/#` used as real unit signals
- fake unit fragments created by raw street/city/province tail pollution

### 3.3 Training Guardrails Against Label Pollution
Training must gain a preflight consistency-check capability so obviously inconsistent gold labels do not flow directly into the learning loop.

## 4. Concrete Requirements

### Requirement 1: Add dedicated gold relabel review batches
The system should be able to generate dedicated relabel review batches for likely mislabeled rows.

Delivery requirements:
- the system can generate standalone `building_type` relabel queues
- it can exclude already-known geographic `Upper/Lower` noise rows
- the queue can be batch-prescreened with LLM support for faster human review

### Requirement 2: Add label-consistency diagnostics
The system should output label-consistency diagnostics before training or inside training reports.

Delivery requirements:
- it can count and surface:
  - `single_unit` + strong unit hints
  - `multi_unit` + missing unit evidence
  - `commercial` + residential-like patterns
- it can emit concrete sample lists for human relabel review

### Requirement 3: Strengthen residential sub-unit semantic disambiguation
Parsing and feature extraction should better separate:
- `Upper/Lower` as geographic modifiers
- residential sub-unit structure hints
- real unit hints vs. tail-noise pollution

Delivery requirements:
- parse/runtime features can explicitly distinguish:
  - `unit-like token`
  - `geographic modifier token`
- training and runtime can consume that distinction

### Requirement 4: Evaluation must prove gains after label stabilization
Evaluation should explicitly answer:
- whether `building_type_f1` improves because of relabel consistency
- whether `unit_number_f1` / `unit_recall` remain protected
- how many remaining `building_type` errors come from labeling issues vs. parsing issues

## 4A. Technical Implementation Evolution

### Requirement 1: Gold label-consistency relabel batches
Technical methods already used:
- **Suspicious-label scanning**
  - the system automatically detects `single_unit + strong unit hint` and similar `building_type` inconsistencies
  - benefit: relabeling becomes systematic rather than purely manual discovery
- **Dedicated relabel review batches**
  - standalone `building_type` relabel queues are generated while excluding known geographic noise
  - benefit: manual review focuses on samples that truly pollute model learning

Current code carrier:
- `learning/gold.py`
- `api/routes/review.py`

### Requirement 2: Label-consistency diagnostics
Technical methods already used:
- **Pre-training consistency scan**
  - before training, the system counts patterns such as `single_unit + strong unit hint` and `multi_unit + missing unit evidence`
  - benefit: obviously inconsistent gold does not silently flow into training
- **Artifact-level diagnostics writeback**
  - `label_consistency_diagnostics` is written into the training artifact
  - benefit: the level of gold pollution becomes visible at training time

Current code carrier:
- `learning/trainer.py`
- `tests/test_training_diagnostics.py`

### Requirement 3: Residential sub-unit semantic disambiguation
Technical methods already used:
- **Geographic-modifier vs sub-unit separation**
  - the system distinguishes whether `Upper/Lower` is part of a place name or a real residential sub-unit
  - benefit: preserves `Upper 123 Main St` while avoiding false units for `Upper Lahave`
- **Semantic features enter parse/runtime/training**
  - geographic-modifier and unit-like-token signals are written into feature vectors and consumed by scoring/training
  - benefit: the semantic boundary is no longer enforced only by hand-coded rules

Current code carrier:
- `core/common.py`
- `api/server.py`
- `learning/trainer.py`

### Requirement 4: Evaluation validates gains from label stabilization
Technical methods already used:
- **Before/after relabel metric comparison**
  - `building_type_f1`, `unit_number_f1`, and `unit_recall` are checked after relabel consistency fixes
- **Semantic-disambiguation stability validation**
  - the system verifies that semantic disambiguation does not regress metrics and no longer pollutes training/runtime with geographic noise

Current code carrier:
- `learning/evaluator.py`
- `learning/shadow.py`

## 5. In Scope
- relabel review batch generation
- label-consistency diagnostics
- semantic disambiguation for `Upper/Lower/Apt/Unit`
- training preflight consistency checks
- linked validation of building_type and unit metrics

## 6. Out Of Scope
- operations-system UI redesign
- release center / reports center bug fixes
- commercial as the main optimization target
- multi-country support
- large-scale canonical asset platform work

## 7. Acceptance Criteria

### Metric Acceptance
1. `building_type_f1` remains stable or improves
2. `unit_number_f1` does not regress
3. `unit_recall` does not regress

### Data And Training Acceptance
4. the system can produce dedicated relabel-consistency batches
5. training preflight can quantify high-risk label inconsistency counts
6. evaluation can explain which remaining `building_type` errors come from parsing and which come from label semantics

## 8. Risks And Watchpoints
- if relabeling remains semantically inconsistent, the model will continue to absorb polluted boundaries
- if `Upper/Lower` disambiguation is too aggressive, it may damage real residential sub-unit cases
- if only data governance is improved but runtime semantic features are not updated, gains may remain limited

## 9. Completion Criteria
This phase can be considered complete when:
- relabel-consistency batch generation is stable and reusable
- pre-training consistency checks can quantify high-risk rows
- `building_type_f1` remains stable or improves
- unit metrics do not regress after semantic disambiguation

## 10. Post-Execution Requirement
This document is an optimization-requirements and execution-plan document, not an execution summary.

After execution, the outcome must be written into a separate:
- execution summary
- update summary
- or phase summary

Execution results must not be backfilled into this plan.
