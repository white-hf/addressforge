# AddressForge Iteration Execution Plan - 2026-04-29 (Phase 3: ML Address-Parsing Optimization Requirements)

## Document Info
- Document Type: Execution Plan / Optimization Requirements
- Effective Date: 2026-04-29
- Owner: AddressForge Product / Engineering
- Status: Planned
- Trigger: future address-parsing success gains must no longer come primarily from adding new rules; they must increasingly come from gold-driven model learning and runtime fusion.

## 1. Current Context & Problem Definition
The system has already improved materially through multiple rounds of rule-based fixes:
- reduced `house -> commercial` false positives
- better high-frequency `unit` recall
- partial stabilization of `building_type`

However, the current improvement path still depends mainly on:
- new rules
- fallback logic
- heuristic adjustments

This creates three problems:

1. quality gains are not easily reusable  
   each new round still requires more rule patching, instead of learning automatically from existing gold.

2. the model loop exists, but its contribution is still too weak  
   training, evaluation, replay, shadow, and gate are wired, but model artifacts do not yet dominate actual parsing success gains.

3. apartment / residential unit recognition is still the main bottleneck  
   the main battlefield is not commercial address handling, but:
   - apartment / multi-unit
   - house with sub-unit
   - trailing bare-number unit cases
   - glued unit-keyword cases

Therefore, the core objective of this phase is not more broad rule growth. It is:

**to wire gold-driven learned signals into training artifacts and runtime, so that future quality gains increasingly come from model learning rather than newly added regex rules.**

## 2. Overall Goal
The goals for this phase are:

1. improve the `unit`-related metrics that most directly affect address-parsing success
2. make parser reranking and candidate scoring actually learn from gold
3. make the training artifact a meaningful input to runtime ranking and decision-making
4. make future quality improvements attributable to model learning, not only to new rules

## 3. Core Optimization Targets

### 3.1 Parser Reranking Must Become Learnable
The system must stop relying primarily on fixed parser scores and must learn from gold:

- which parser is more reliable for which address class
- which pattern / match-rule is more trustworthy
- which candidate is more likely to carry the correct `unit`

### 3.2 Unit Presence / Unit Recovery Must Become Learnable
Apartment / residential unit recognition must move from “rule fallback first” toward “model-weighted first”.

Priority scenarios include:
- `APT308`
- `UNIT1302`
- `street 128 CITY`
- `203 UNIT Halifax`
- `A/B`
- `12A`
- `house with sub-unit`

### 3.3 Residential Boundary Must Stay Stable
The system must more stably distinguish:
- `single_unit`
- `multi_unit`

At this stage, the priority is not commercial maximization. The priority is:
- preserve `house`
- improve `apartment / multi_unit`
- avoid harming `building_type` while improving unit quality

### 3.4 Gold-Driven Learning Loop Must Be Strengthened
Future quality gains must increasingly come from:
- human gold
- active learning
- benchmark error cases

and not continue to rely primarily on rule accumulation.

### 3.5 Training Artifacts Must Close the Loop With Runtime
Model improvement must not stop at writing artifact files. It must enter:
- parse
- reranking
- candidate scoring
- replay
- shadow
- benchmark

## 4. Concrete Requirements

### Requirement 1: Training artifacts must learn parser source reliability
Training must learn parser source reliability from deduplicated gold and write it into the artifact.

Delivery requirements:
- artifact includes `parser_weights`
- weights come from real gold comparisons
- no hardcoded constants or fake supervision

### Requirement 2: Training artifacts must learn match-rule / pattern reliability
Training must learn:
- which patterns are more reliable
- which unit extraction paths are more reliable

Delivery requirements:
- artifact includes `match_rule_weights`
- weights cover at least the current high-frequency unit patterns
- the training path can explain where these weights came from

### Requirement 3: Training artifacts must learn unit-related hint signals
Training must explicitly parameterize:
- explicit unit-signal recovery weight
- unit-present bonus / penalty

Delivery requirements:
- these parameters are visible in the artifact
- they must not remain file-only; runtime must be able to consume them

### Requirement 4: Runtime candidate scoring must consume learned weights
Runtime ranking must not depend only on static scores. It must consume learned parameters from the training artifact.

Delivery requirements:
- `parse()` / candidate ranking actually consumes:
  - `parser_weights`
  - `match_rule_weights`
  - unit bonus / penalty
- a specific candidate model version can load its own runtime configuration

### Requirement 5: Unit-related gains must be visible in benchmark output
Optimization results must show up in key quality metrics, not only in a few fixed examples.

Priority metrics:
- `unit_number_f1`
- `unit_recall`
- `building_type_f1`
- `decision_f1`

### Requirement 6: Quality gains must be attributable
After each round, the system must distinguish:
- gains from rules
- gains from artifacts / learned weights / runtime scoring

It is no longer acceptable to only say “the results look better” without explaining the dominant source of improvement.

## 4A. Technical Implementation Evolution

### Requirement 1: Training artifacts learn parser source reliability
Technical methods already used:
- **Parser reliability learning**
  - parser-source correctness is learned from deduplicated gold rather than fixed parser preferences
  - benefit: converts parser preference from code constants into trainable source reliability
- **Artifact parameterization**
  - learned parser reliability is written into `parser_weights`
  - benefit: parser preference becomes a reusable model artifact, not a hardcoded rule

Current code carrier:
- `learning/trainer.py`
- `api/server.py`

### Requirement 2: Training artifacts learn match-rule / pattern reliability
Technical methods already used:
- **Pattern-hit reliability learning**
  - the system learns how trustworthy different unit patterns, match rules, and recovery paths are
  - benefit: high-frequency patterns stop being treated as flat heuristics
- **Pattern-weight runtime consumption**
  - `match_rule_weights` are consumed in runtime candidate scoring
  - benefit: learned pattern experience actually affects parse/ranking behavior

Current code carrier:
- `learning/trainer.py`
- `api/server.py`

### Requirement 3: Training artifacts learn unit-related hint signals
Technical methods already used:
- **Explicit unit-hint parameterization**
  - explicit unit hints, residential unit hints, and commercial hints are turned into learned parameters
  - benefit: unit recognition is no longer limited to if/else fallback logic
- **Unit bonus / penalty modeling**
  - candidates are rewarded or penalized based on whether unit hints are present and whether unit recovery succeeds
  - benefit: unit recovery quality directly influences candidate ranking

Current code carrier:
- `core/common.py`
- `learning/trainer.py`
- `api/server.py`

### Requirement 4: Runtime candidate scoring consumes learned weights
Technical methods already used:
- **Artifact-driven runtime scoring**
  - parse/reranking no longer relies only on static base scores; it adds learned weights from training artifacts
  - benefit: training artifacts materially change runtime selection
- **Version-bound runtime configuration**
  - each candidate model version can load its own artifact configuration
  - benefit: benchmark / replay / shadow can observe real candidate behavior

Current code carrier:
- `api/server.py`
- `services/replay_service.py`
- `learning/shadow.py`

### Requirements 5-6: Gains are visible and attributable
Technical methods already used:
- **Unit-driven metric acceptance**
  - `unit_number_f1`, `unit_recall`, `building_type_f1`, and `decision_f1` are used as the primary phase metrics
  - benefit: prevents local case-fix progress from being mistaken for real system-level gains
- **Rule-vs-model gain separation**
  - each round must distinguish learned-weight gains from rule/fallback gains
  - benefit: avoids “it got better, but nobody knows why”

Current code carrier:
- `learning/evaluator.py`
- `learning/trainer.py`

## 5. In Scope
The following are in scope for this phase:

- parser source reliability learning
- match-rule / pattern reliability learning
- unit-related learned signals
- runtime scoring fusion
- candidate-version participation in benchmark / replay / shadow
- gold-driven improvement centered on `unit`

## 6. Out Of Scope
The following are not the primary path for this phase:

- operations-system UI / page experience
- Dashboard / Reports / Batch workflow restructuring
- job-status visibility fixes
- large continued growth of low-value long-tail rules
- optimization with `commercial_f1` as the primary target

## 7. Acceptance Criteria

### Metric Acceptance
At minimum, this phase should satisfy:

1. `unit_number_f1` improves again, or at least does not regress
2. `unit_recall` improves again, or at least does not regress
3. `building_type_f1` does not materially regress due to unit optimization
4. `decision_f1` remains stably high

### Engineering Acceptance
This phase must also satisfy:

5. training artifacts visibly contain new learned parameters
6. runtime visibly consumes those parameters
7. replay / shadow / benchmark can bind to the candidate version
8. the next round of gains cannot be explained only by newly added regex rules

## 8. Risks And Watchpoints
- if gold still lacks enough `unit` density, learned weights may remain too sparse
- if runtime loads parameters but does not materially change ranking behavior, the “model-led improvement” path is still superficial
- if unit gains still come mainly from rules instead of learned weights, the primary path has not truly shifted to ML
- if `house` accuracy regresses, residential baseline stability must take priority

## 9. Completion Criteria
This phase can be considered complete when:

- unit-related metrics improve again
- training artifacts begin to influence runtime scoring in a stable way
- parser-reranking gains can be learned from gold
- future gains no longer depend primarily on newly added rules

## 10. Post-Execution Requirement
This document is an optimization-requirements and execution-plan document, not an execution summary.

After execution, the result must be written into a separate:
- execution summary
- update summary
- or phase summary

Execution results must not be backfilled into this plan.
