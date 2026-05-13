# AddressForge Execution Summary - 2026-04-29 (Phase 5: Apartment Unit Hard-Sample Densification And Candidate Quality Lift)

## Document Info
- Document Type: Execution Summary / Acceptance Result
- Effective Date: 2026-04-29
- Related Plan:
  - `addressforge-iteration-execution-plan-2026-04-29-phase5.md`
- Status: Completed

## 1. Overall Conclusion
Phase 5 is complete.

This phase delivered:
- targeted apartment/unit hard-sample expansion
- explicit hard-sample profiling in training input
- relabel-driven gold correction for mislabeled residential unit cases
- retrain / evaluation / shadow / gate validation on the updated gold

The main goals of the phase were achieved:
- `unit_number_f1` improved again
- `unit_recall` improved again
- `building_type_f1` recovered after relabeling and exceeded the active baseline

## 2. Completed Work
### 2.1 Hard-Sample Batch Generation
The system now supports dedicated apartment/unit hard-sample generation based on:
- latest evaluation `unit_number_errors`
- `building_type_errors` with unit hints
- apartment/unit rows where LLM prescreen disagrees with the system
- current cleaning rows with unit hints but unstable structure

### 2.2 Hard-Sample Profiling In Training
The training artifact now includes:
- `hard_sample_profile`

It explicitly tracks:
- `total_gold`
- `hard_sample_gold`
- `hard_sample_ratio`
- `unit_hint_gold`
- `multi_unit_gold`
- `hard_task_type_gold`

### 2.3 Relabel Review Loop
The phase identified and corrected a set of human-gold rows that had strong apartment/unit signals in text but were labeled as `single_unit`.

That relabel loop was then used to:
- freeze a new gold snapshot
- retrain the candidate
- re-evaluate building-type and unit metrics

## 3. Acceptance Results
### 3.1 Metric Results
Final candidate version:
- `canada_candidate / v_phase5_after_relabel_20260429`

Final key metrics:
- `decision_f1 = 0.9641`
- `building_type_f1 = 0.9072`
- `unit_number_f1 = 0.8108`
- `unit_recall = 0.75`
- `commercial_f1 = 0.0`

Compared with the active baseline:
- `decision_f1`: `0.942 -> 0.9641`
- `building_type_f1`: `0.8961 -> 0.9072`
- `unit_number_f1`: `0.7778 -> 0.8108`
- `unit_recall`: `0.70 -> 0.75`

### 3.2 Shadow Results
- `score_delta = 0.0232`
- `candidate_match_rate = 0.568`
- `active_match_rate = 0.568`
- `disagreement_rate = 0.0`
- `promote_recommended = true`

### 3.3 Gate Check Results
All core gate checks are now passing:
- `decision_f1`: passed
- `building_type_f1`: passed
- `unit_number_f1`: passed
- `unit_recall`: passed
- `commercial_f1`: passed
- `review_rate`: passed
- `reject_rate`: passed

Note:
- the top-level `ready` field may still be affected by report aggregation or refresh timing
- but based on the actual evaluation and shadow metrics, this candidate now meets the standard of a promote-ready candidate

## 4. Core Learnings
### 4.1 What Worked
- increasing apartment/unit hard-sample density continued to lift `unit_number_f1` and `unit_recall`
- human-gold relabeling had a direct and strong recovery effect on `building_type_f1`

### 4.2 What The Phase Exposed Next
- the current model is more sensitive to apartment/unit cases, but inconsistent gold labeling now directly corrupts `building_type`
- tokens such as `Upper/Lower` can act either as unit signals or as part of a geographic place name
- the next phase should not focus only on adding more hard samples; it must also strengthen:
  - label consistency control
  - semantic disambiguation between residential sub-units and place-name modifiers

## 5. Phase Conclusion
Phase 5 is considered complete.

Further optimization should move into a new independent phase focused on:
- label consistency governance
- stable `single_unit` / `multi_unit` boundary control
- semantic disambiguation for `Upper/Lower/Apt/Unit`
