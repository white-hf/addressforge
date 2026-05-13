# AddressForge Execution Summary - 2026-04-29 (Phase 6: Residential Unit Label Consistency And Semantic Disambiguation)

## Document Info
- Document Type: Execution Summary / Acceptance Result
- Effective Date: 2026-04-29
- Related Plan:
  - `addressforge-iteration-execution-plan-2026-04-29-phase6.md`
- Status: Completed

## 1. Overall Conclusion
Phase 6 is complete.

This phase delivered:
- relabel-consistency review batch generation
- pre-training label-consistency diagnostics
- semantic disambiguation for `Upper/Lower/Apt/Unit`
- semantic-ambiguity review batch generation and source-pool expansion
- runtime, training, and evaluation protection against label pollution

The main goal of this phase was achieved:
- stabilize the `single_unit` / `multi_unit` boundary
- prevent place-name noise such as `Upper Lahave` from being over-learned as unit structure
- protect `building_type_f1`, `unit_number_f1`, and `unit_recall` from regression

## 2. Completed Scope
### 2.1 Relabel Consistency Batch Generation
The system can now generate dedicated relabel review batches for likely mislabeled `building_type` rows, especially:
- `single_unit` rows with strong residential unit hints
- cases that should be re-reviewed as `multi_unit`

The relabel seeding logic also avoids repeatedly dispatching already-reviewed rows.

### 2.2 Training-Time Label Consistency Diagnostics
Training artifacts now include:
- `label_consistency_diagnostics`

They explicitly quantify:
- `single_unit` + strong unit hint
- `multi_unit` + missing unit evidence
- `commercial` + residential-like pattern

This gives the training loop a preflight consistency layer instead of blindly trusting all human-gold rows.

### 2.3 Semantic Disambiguation In Parse / Runtime / Training
The parser, runtime scoring, and training features now distinguish between:
- true residential sub-unit signals
- geographic modifier tokens such as `Upper/Lower` used only as part of a place name

Examples:
- `48 Rudolf Road, Upper Lahave, NS` remains `single_unit`
- `Upper 123 Main St, Halifax, NS` remains a true residential sub-unit case

### 2.4 Semantic Ambiguity Review Batch Generation
The system now has a dedicated semantic-ambiguity review queue generator, and it can pull candidates from:
- current cleaning results
- latest evaluation `building_type` errors

The fact that recent runs produced `inserted = 0` is considered a positive result: current ambiguity candidates are already covered by historical review and deduplication.

## 3. Acceptance Results
### 3.1 Engineering Acceptance
Completed:
- relabel-consistency batch generation
- label-consistency diagnostics in training artifacts
- semantic disambiguation feature wiring in parse/runtime/training
- semantic-ambiguity review queue generation
- ambiguity source-pool expansion beyond the original queue

### 3.2 Runtime / Training Validation
Confirmed runtime behavior:
- geographic `Upper/Lower` place-name cases are no longer rewarded as residential unit signals
- true residential prefix-unit patterns are still recoverable

Confirmed training behavior:
- training artifacts now carry semantic-disambiguation feature signals
- label-consistency diagnostics are produced in real training outputs

### 3.3 Metric Outcome
Latest validated candidate metrics after the semantic phase:
- `decision_f1 = 0.9641`
- `building_type_f1 = 0.9072`
- `unit_number_f1 = 0.8108`
- `unit_recall = 0.75`
- `commercial_f1 = 0.0`

Compared with the previous relabel-stabilized candidate:
- no new regression was introduced
- semantic disambiguation stabilized the boundary
- the main gain of this phase was quality protection and semantic hygiene, not another large top-line jump

## 4. Main Learnings
### 4.1 What Worked
- label consistency and semantic hygiene are now explicit parts of the learning pipeline
- `Upper/Lower` ambiguity can be managed without damaging real sub-unit recovery
- preventing bad supervision is as important as adding more hard samples

### 4.2 What Became The Next Bottleneck
- the current review/gold pool for semantic ambiguity has largely been consumed
- further gains are less likely to come from the same ambiguity cases
- the next bottleneck shifts upward to:
  - canonical address quality
  - reference-backed convergence
  - stable address assetization quality

## 5. Phase Conclusion
Phase 6 is considered complete.

The next phase should move to a new mainline focused on:
- canonical address quality
- reference fusion confidence
- address assetization quality and convergence
