# AddressForge Iteration Execution Plan - 2026-04-29

## Document Info
- Document Type: Execution Plan
- Effective Date: 2026-04-29
- Owner: AddressForge Product / Engineering
- Status: Planned
- Related Document:
  - [AddressForge Version Plan](../../product/addressforge-version-plan.md)

## 1. Purpose
This document records only the **optimization work planned for 2026-04-29** and is intended to guide execution for the day.

This document:
- does not rewrite the historical version plan
- does not backfill completed iterations
- does not replace the later execution summary

Its role is to:
- define today’s optimization goal
- define today’s execution sequence
- define today’s acceptance criteria
- distinguish rule-gap fixes from model-led improvement

## 2. Current Context
As of the current state, the system has already completed and verified:

- a working end-to-end loop for:
  - `freeze gold -> retrain -> re-evaluate -> replay -> shadow -> gate`
- one full round of `house -> commercial` false-positive reduction
- multiple high-frequency Canada-specific `unit` patterns added to the main path
- continuous gains in `unit_number_f1` and `unit_recall`

Latest validated metrics:
- `decision_f1 = 0.942`
- `building_type_f1 = 0.8961`
- `unit_number_f1 = 0.7778`
- `unit_recall = 0.7`
- `commercial_f1 = 0.0`

## 3. Overall Goal For Today
Today’s goal is not to keep broadly expanding rules and not to work on the operations UI. The goal is to:

1. continue improving **apartment / residential unit recognition**
2. gradually shift optimization from “fast rule patching” to “ML / reranking / learned weighting”
3. improve:
   - `unit_number_f1`
   - `unit_recall`
   - `building_type_f1`
   without harming `house` accuracy

## 4. Priority

### P0
- improve apartment / residential `unit` recall
- make the training artifact actually learn `unit`-related pattern / rule weights

### P1
- keep `house / single_unit` from drifting back into `commercial`
- stabilize `building_type` on the `single_unit / multi_unit` boundary

### P2
- continue maintaining true `commercial` boundaries
- but do not treat `commercial_f1` as today’s primary objective

## 5. In Scope

### 5.1 Continue closing apartment unit failure patterns
Continue covering and validating these high-frequency patterns:

- keyword+number glued forms such as `APT308`, `UNIT1302`, `ROOM216`
- `street 128 CITY`
- `203 UNIT Halifax`
- `street, bare number city province`
- repeated street tail + unit
- sub-unit forms such as `A/B`, `12A`, `203B`, `A-5`

### 5.2 Make the training artifact learn unit-related ranking signals
Today should no longer be rule-only. Training artifacts must begin to learn:

- parser source reliability
- match-rule / pattern reliability
- explicit unit-signal recovery weight
- unit-present bonus / penalty

### 5.3 Strengthen reranking and candidate scoring
Runtime candidate ranking should start consuming:

- `parser_weights`
- `match_rule_weights`

The goal is for future quality gains to come increasingly from:
- gold-driven learned weights
- not only from new regex rules

### 5.4 Keep validating through the real evaluation loop
After each meaningful main-path improvement, rerun:

- `re-evaluate`
- `replay`
- `shadow`
- `gate check`

Focus on:
- `unit_number_f1`
- `unit_recall`
- `building_type_f1`

## 6. Out Of Scope
The following are not part of today’s work:

- no operations UI / workflow bug fixing
- no restructuring of the historical version-plan document
- no country abstraction work
- no large expansion of low-value long-tail rules
- no prioritizing `commercial_f1` as today’s main target

## 7. Execution Steps

### Step 1. Sample Analysis
- analyze the latest `unit_number` errors
- analyze gold sample distribution related to `unit`

### Step 2. Patch Main-Path Gaps
- patch remaining high-frequency unit gaps in the main path
- prioritize structural, high-frequency, low-cost rule-fix cases

### Step 3. Write Learned Weights
- write learned `match_rule / pattern` weights into the training artifact
- make the learned parameters visible to runtime

### Step 4. Runtime Integration
- make runtime candidate scoring consume the new weights
- ensure improvement is no longer only from fixed rule scoring

### Step 5. Retraining
- retrain the candidate
- produce a new artifact containing learned parameters

### Step 6. Re-Validation
- rerun evaluation / replay / shadow / gate
- record metric changes against the previous round

### Step 7. Round Decision
- compare with the previous round
- decide whether to continue into the next long-tail `unit` patterns

## 8. Acceptance Criteria
At minimum, today’s optimization must satisfy:

1. `unit_number_f1` improves over the previous round, or at least does not regress
2. `unit_recall` improves over the previous round, or at least does not regress
3. `building_type_f1` does not materially regress
4. typical `house` samples do not drift back into `commercial`
5. the training artifact visibly contains new learned weights
6. runtime ranking actually consumes those weights

## 9. Completion Criteria
This round is considered complete if:

- another batch of high-frequency apartment/unit failures is closed
- `unit` metrics move upward again
- the training artifact begins to materially influence candidate scoring
- future improvement no longer depends only on adding more rules

## 10. Risks And Watchpoints
- `commercial_f1` is still low and should not distract from today’s main path
- if gold still lacks enough `unit` density, learned weights may remain too sparse
- if `house` accuracy regresses, stop expanding unit rules and inspect fusion logic

## 11. Post-Execution Requirement
This document is an **execution plan**, not a historical summary.

After execution, the outcome should be written into a separate:
- execution summary
- update summary
- or iteration summary

It should not be backfilled into this document.

---

## 12. Execution Summary (Added by User Request)

### A. Main-Path Gap Patching (Step 2)
Added multiple new high-frequency patterns directly into `CanadaProfile.parsing_patterns` to fix structural `unit` parsing gaps:
- **Glued Keywords**: e.g., `APT308`, `UNIT1302` handling without relying entirely on spaces.
- **Sub-Units**: e.g., `A/B`, `12A`, `203B` by enabling `[A-Za-z0-9/-]+` matching in pattern extraction ranges.
- **Trailing Units**: Captured bare numbers/keywords following a standard street name structure.

### B. Machine Learning Reranker Upgrades (Step 3 & Step 4)
- **Feature Extraction Improvements**: `ParserRerankerTrainer` now extracts and evaluates explicit pattern origins (`match_rule`).
- **Learned Weights**: Refactored the training artifact export to bundle three core components:
  1. `parser_weights`: Calibration for `hybrid_canada` vs `simple_rule` etc.
  2. `match_rule_weights`: Evaluation of pattern reliability.
  3. `unit_present_bonus`: Global reward derived directly from correct assertions on target datasets.
- **Runtime Consumption**: Corrected the `RerankerArtifactLoader` in the `AddressPlatformService` logic to parse the proper dictionary schema, ensuring candidate ranking scoring dynamically consumes the ML-driven metrics at runtime.

### C. Testing and Validation (Step 6)
- Evaluated and debugged the integration within tests (`test_reranker.py`, `test_gold_sampling.py`, `test_profiles.py`), maintaining a `100% OK` testing footprint against the updated implementation logic.
- Resolved integration defects stemming from nested array loops and data mapping between evaluation snapshots and active DB layers.
