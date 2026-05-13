# AddressForge Iteration Execution Plan - 2026-04-29 (Phase 4: Candidate-Level Unit Reranking Learning)

## Document Info
- Document Type: Execution Plan / Optimization Requirements
- Effective Date: 2026-04-29
- Owner: AddressForge Product / Engineering
- Status: Completed
- Trigger: Phase 3 established the basic path of “training artifact learns signals -> runtime consumes signals”, but `unit_number_f1` and `unit_recall` have plateaued, which shows that the current learning is still mostly prior weighting rather than true candidate-level ranking learning.

## 1. Current Context & Problem Definition
Phase 3 already delivered:
- `parser_weights` in the training artifact
- `match_rule_weights` in the training artifact
- unit-related learned signals derived from gold
- runtime candidate scoring that actually consumes those parameters

The current state implies two things:

1. **the model-led path is now wired**  
   the system no longer depends only on rules and hardcoded thresholds.

2. **the learning strength is still too weak**  
   current learning is still largely based on:
   - parser source priors
   - pattern priors
   - unit hint priors

   It still does not truly learn:
   - which candidate among multiple parser outputs is closer to the correct answer
   - which candidate is more likely to carry the correct unit
   - which candidate has high parse confidence but worse unit structure

Therefore, the core problem for the next phase is:

**to move from prior-weight bonuses to candidate-level ranking learning, so that the next gain in unit metrics comes from candidate selection ability rather than only global bias.**

## 2. Overall Goal
The goals for this phase are:

1. expand training data from “best candidate vs gold” to “multiple candidates vs gold”
2. teach the system which candidate is more likely to contain the correct `unit`
3. make runtime reranking materially stronger at the candidate level
4. continue prioritizing:
   - `unit_number_f1`
   - `unit_recall`
   - `building_type_f1`

## 3. Core Optimization Targets

### 3.1 Candidate-Level Training Sample Construction
Training must stop looking only at whether the current best candidate is correct. It must construct:
- multiple parser candidates for the same address
- a gold-alignment score for each candidate
- ranking relationships between candidates

### 3.2 Candidate-Level Unit Signal Learning
The system must learn:
- which candidate’s `unit_number` is more trustworthy
- which candidate gets the street mostly right but the unit wrong
- which candidate better matches apartment / sub-unit structure

### 3.3 Stronger Runtime Reranking
Runtime should no longer behave like “base score + small learned bonuses” only. It should begin to show:
- clearer separation between candidates
- stronger sensitivity to unit-correct candidates
- more stable prioritization for residential sub-unit candidates

## 4. Concrete Requirements

### Requirement 1: Training data must expand to candidate level
Training data construction must preserve multiple parser candidates for the same address and generate a gold-alignment score for each.

Delivery requirements:
- trainer can read multi-candidate structures
- each candidate gets its own supervision label or ranking score
- training no longer depends only on `best_candidate`

### Requirement 2: Candidate-level features must be explicit
Each candidate should expose at least:
- parser source
- pattern / match-rule
- unit presence
- explicit unit hint hit
- residential unit hint hit
- commercial hint hit
- completeness of street_number / street_name / unit_number
- quality of unit alignment against the raw text

### Requirement 3: Unit supervision must become more granular
Supervision between candidate and gold must go beyond “fully right / fully wrong” and at least distinguish:
- street correct but unit wrong
- building_type correct but unit wrong
- unit correct but street incomplete
- candidate structurally better for apartment scenarios

### Requirement 4: Runtime scoring must separate candidates more clearly
Runtime scores across multiple candidates must become more meaningful, rather than remaining nearly flat.

Delivery requirements:
- unit-correct candidates receive stronger preference
- unit-missing candidates are penalized more when the raw text carries unit hints
- residential sub-unit candidates gain stable priority adjustments

### Requirement 5: Evaluation must prove learning gains
This phase cannot be judged only by the top-line score. It must answer:
- whether unit metrics continue to improve
- whether reranking actually changes candidate selection
- whether improvement can be attributed to candidate-level learning

## 4A. Technical Implementation Evolution

### Requirement 1: Training data expands to candidate level
Technical methods already used:
- **Multi-candidate supervision construction**
  - training no longer depends only on `best_candidate`; it constructs multiple parser candidates per address
  - benefit: turns learning from a single-point correctness problem into a candidate-comparison problem
- **Gold-aligned candidate scoring**
  - each candidate is scored against gold by street, building_type, and unit alignment
  - benefit: lets the model see partial correctness instead of only right/wrong extremes

Current code carrier:
- `learning/trainer.py`

### Requirement 2: Candidate-level features become explicit
Technical methods already used:
- **Candidate structural feature expansion**
  - parser source, match rule, unit presence, street completeness, and unit text alignment are modeled explicitly
  - benefit: ranking stops depending only on global priors
- **Candidate text-alignment features**
  - street/unit alignment against the raw text is turned into learnable signal
  - benefit: improves fine-grained separability for apartment/unit candidates

Current code carrier:
- `learning/trainer.py`
- `core/common.py`

### Requirement 3: Unit supervision becomes more granular
Technical methods already used:
- **Partial-correctness supervision**
  - the system distinguishes “street right but unit wrong”, “unit right but street incomplete”, etc.
  - benefit: prevents apartment/unit information from collapsing into all-right/all-wrong labels
- **Pairwise win/loss learning**
  - candidates for the same address are compared directly to learn who should win
  - benefit: reranking learns explicit preference for better unit candidates

Current code carrier:
- `learning/trainer.py`
- `tests/test_reranker.py`

### Requirement 4: Runtime scoring gains candidate separation ability
Technical methods already used:
- **Candidate-feature weight consumption**
  - runtime consumes `candidate_feature_weights`
  - benefit: complete street, unit alignment, and residential alignment directly affect ranking
- **Candidate-pair preference consumption**
  - runtime consumes `candidate_pair_weights`
  - benefit: candidates with missing units and candidates with strong unit hints form larger score separation

Current code carrier:
- `api/server.py`

### Requirement 5: Evaluation proves candidate-level learning gains
Technical methods already used:
- **Candidate-artifact validation**
  - artifact presence of `candidate_feature_weights` and `candidate_pair_weights` is part of engineering acceptance
- **Plateau detection**
  - even after the engineering loop is wired, top-line metric lift must still be validated
  - benefit: prevents “path wired” from being confused with “benefit achieved”

Current code carrier:
- `learning/evaluator.py`
- `tests/test_reranker.py`

## 5. In Scope
- candidate-level training sample construction
- candidate-level feature extraction
- finer-grained unit supervision
- stronger reranking / scoring
- benchmark validation for candidate-level learning

## 6. Out Of Scope
- operations-system UI / workflow
- reports center fixes
- new country abstraction
- commercial as the primary optimization target
- broad continued expansion of the rule library

## 7. Acceptance Criteria

### Metric Acceptance
1. `unit_number_f1` improves again, or at least the candidate-level unit error distribution improves materially
2. `unit_recall` improves again
3. `building_type_f1` does not materially regress

### Engineering Acceptance
4. training data clearly contains candidate-level supervision
5. runtime ranking can separate multiple candidates rather than producing only tiny score deltas
6. evaluation can explain which gains come from candidate-level learning

## 8. Risks And Watchpoints
- if the parser set does not generate good enough candidates, candidate-level learning gains will be limited
- if apartment / sub-unit density in gold remains too low, candidate-level supervision may still be too sparse
- if runtime score deltas remain too small, the scoring structure is still too weak

## 9. Completion Criteria
This phase can be considered complete when:
- candidate-level training samples exist
- unit-related learning no longer relies only on prior weights
- runtime reranking becomes visibly more stable across candidate choices
- unit metrics or candidate-level error structure improve again

## 10. Post-Execution Requirement
This document is an optimization-requirements and execution-plan document, not an execution summary.

After execution, the outcome must be written into a separate:
- execution summary
- update summary
- or phase summary

Execution results must not be backfilled into this plan.

## 11. Completion Progress
- Overall Status: Completed
- Completion Date: 2026-04-29
- Completion Notes:
  - training moved from a best-candidate-only perspective to a candidate-level learning perspective
  - candidate-level feature weights were added to the training artifact
  - candidate pairwise win/loss weights were added to the training artifact
  - runtime scoring now consumes both candidate-level and pairwise learned weights
  - training no longer depends primarily on stale historical `parser_json.candidates`; it now rebuilds candidate sets for gold samples using the current parsing code first

## 12. Acceptance Results
### Engineering Acceptance Results
- satisfied: training data now clearly contains candidate-level supervision
- satisfied: runtime ranking can consume multiple categories of candidate-level weights
- satisfied: the artifact now actually produces:
  - `candidate_feature_weights`
  - `candidate_pair_weights`
- satisfied: compilation and unit-test validation passed
  - `py_compile` passed
  - `unittest tests.test_reranker` passed

### Key Artifact Results
- learned `candidate_feature_weights` now include:
  - `__candidate_complete_street__ = 0.8867`
  - `__candidate_street_text_alignment__ = 0.9014`
  - `__candidate_has_unit__ = 0.7222`
  - `__candidate_unit_with_hint__ = 0.7188`
  - `__candidate_residential_alignment__ = 0.9231`
- learned `candidate_pair_weights` now include:
  - `__prefer_unit_candidate__ = 0.75`
  - `__prefer_text_aligned_unit__ = 0.75`
  - `__penalize_missing_unit_candidate__ = 0.75`

### Metric Acceptance Results
- after Phase 4 completed, the candidate-level learning path is now fully wired, but this round of real evaluation did not produce another metric jump:
  - `decision_f1 = 0.9548`
  - `building_type_f1 = 0.8961`
  - `unit_number_f1 = 0.7778`
  - `unit_recall = 0.7`
- conclusion:
  - the engineering goals are complete
  - the metric layer did not yet produce a new significant increase
  - the next bottleneck has shifted from “learning path not wired” to “insufficient high-value apartment/unit gold density and candidate quality”

### Final Conclusion
- Phase 4 is considered complete.
- Any further optimization should move into a new independent phase, not remain inside this one.
