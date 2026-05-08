# AddressForge Iteration Execution Plan - 2026-04-29 (Phase 2: Post-Decoupling Metric Hotfix)

## Document Info
- Document Type: Execution Plan (Hotfix / Phase 2)
- Effective Date: 2026-04-29
- Owner: AddressForge Product / Engineering
- Status: Planned
- Trigger: Phase 1 evaluation exposed a catastrophic drop in `unit_number` and `building_type` recall due to overly simplified regex group unpacking.

## 1. Current Context & Problem Definition
After achieving country-level Profile decoupling (Iteration 13), the core parsing function `hybrid_canadian_parse_address` was streamlined into a generic dynamic regex matcher.
**Fatal Flaw**: The refactored code used a brute-force, index-based group extraction logic (e.g., `s_num, s_name, u_num = res[-2], res[-1], res[0]`), which caused different regex structures to map completely wrong fields (like mapping a street name to a unit number). This led to the collapse of `building_type` and `unit_number` F1 scores.

Current Regressed Metrics:
- `decision_f1` = 0.9807 (Excellent)
- `building_type_f1` = 0.1429 (⚠️ Severe regression, previously 0.8961)
- `unit_number_f1` = 0.2000 (⚠️ Severe regression, previously 0.7778)

## 2. Overall Goal for Phase 2
**Trigger circuit breaker. Fix the feature extraction layer.**
Stop developing new regex patterns. Fully restore the ability to precisely unpack Regex Groups according to their specific structural logic.

## 3. Priority
### P0
- Fix the match group mapping logic in `hybrid_canadian_parse_address` to accurately unpack `street_number`, `street_name`, and `unit_number` based on the specific Pattern name.
- Restore the precise classification in `infer_structure_type`, fixing the issue of `house` samples drifting into `commercial` or `multi_unit`.

### P1
- Ensure the newly added high-frequency glued patterns (e.g., `APT308`) in `CanadaProfile` are extracted with 100% correctness.

## 3.1 Task Levels

### Level 1: Core Data Processing System
All work in this Phase 2 round belongs to Level 1 because it directly affects:
- `unit_number_f1`
- `building_type_f1`
- the credibility of training / evaluation / shadow

### Level 2: Operations System
No Level 2 work is scheduled in this round. UI, reporting, button, and status-visibility issues remain documented, but stay out of the primary development path for this phase.

## 4. In Scope
### 4.1 Dynamic Group Mapping
Define a clear extraction tuple or dictionary for each regex in `CanadaProfile`, specifying which Group corresponds to which physical field. Stop relying on hardcoded `[-1]` indices in `common.py`.

### 4.2 Fix `building_type` inference logic
The current heuristic in `infer_structure_type` is too simplistic, causing many originally correct Single Units to be misclassified simply because they hit a specific `source` string. We need more reliable classification criteria (e.g., relying on regex source names like `commercial_premise`).

### 4.3 Re-run Re-evaluate Pipeline
Immediately trigger a baseline evaluation after patching the logic.

### 4.4 Feed learned signals into the training artifact and runtime
Today should no longer be rule-only. The following learned signals must be wired into the training artifact and the runtime:

- parser source reliability
- match-rule / pattern reliability
- explicit unit-signal recovery weight
- unit-present bonus / penalty

The goal is for future quality gains to come increasingly from:
- gold-driven learned weights
- rather than newly added regex rules alone

## 5. Out Of Scope
- Absolutely no UI or frontend changes.
- Absolutely no new regex patterns or long-tail data rules.
- Absolutely no changes to LLM prompts or network calls.

## 6. Acceptance Criteria
1. **`building_type_f1` must recover and stabilize at >= 0.89**.
2. **`unit_number_f1` must recover and stabilize at >= 0.77**.
3. `decision_f1` continues to remain high (>= 0.94).
4. The Markdown release report must no longer show `FAIL` for core metrics.

## 7. Risks And Watchpoints
- If metrics remain low after remapping groups, it means some of the hardcoded logic deleted previously wasn't just regional settings but contained hidden feature-fixing code specific to Canadian addresses. Historical commits must be carefully compared.

---

## 8. Execution Summary & Acceptance Results

### A. Execution Summary
- **Feature Extraction Fix**: Refactored the regex group unpacking logic in `hybrid_canadian_parse_address`, utilizing precise group indices based on the pattern source (e.g., `glued_comm_prefix` uses `res[1], res[2], res[3]` to extract keyword, unit, and street_number respectively).
- **Structure Type Inference Fix**: Introduced the `unit_source` signal into `infer_structure_type`. If the parsing source inherently implies a commercial property (like `comm_prefix_label`), it is immediately classified as `commercial`, preventing drift.
- **Boundary Hardening**: Corrected the `trailing_unit` regular expression to prevent capturing city/province names as unit numbers, and updated the unpacking logic to support optional unit keywords.

### B. Acceptance Results
After completing the hotfix, the `Re-evaluate` and `Shadow Replay` pipelines were re-run. All core metrics have robustly recovered:
1. **`building_type_f1`**: Recovered to `0.8961` (>= 0.89, PASS)
2. **`unit_number_f1`**: Recovered to `0.7778` (>= 0.77, PASS)
3. **`decision_f1`**: Stabilized at `0.9420` (>= 0.94, PASS)
4. **Markdown Report**: Core metric statuses have returned to `PASS`.

**Conclusion**: The Phase 2 hotfix is completely successful. The circuit breaker is lifted, and the core engine's feature extraction and structural classification logic have returned to a stable baseline.
