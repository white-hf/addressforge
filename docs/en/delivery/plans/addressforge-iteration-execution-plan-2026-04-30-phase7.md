# AddressForge Iteration Execution Plan - 2026-04-30 (Phase 7: Canonical Address Quality, Reference Fusion, And Assetization Convergence)

## Document Info
- Document Type: Execution Plan / Optimization Requirements
- Effective Date: 2026-04-30
- Owner: AddressForge Product / Engineering
- Status: Completed
- Trigger: Phase 6 completed the residential label-consistency and semantic-disambiguation mainline. The next bottleneck has now moved upward from parser/unit boundaries to canonical quality, reference-backed convergence, and stable address assetization quality.

## 1. Current Context & Problem Definition
After Phase 5 and Phase 6:
- the core apartment/unit parsing metrics have already improved materially
- the `building_type` semantic boundary has been stabilized
- label pollution and `Upper/Lower` semantic noise are now explicitly handled in training and runtime

The current state implies two things:

1. **the core address-parsing pipeline is now in a sustainably improvable state**
   the system is no longer primarily blocked by basic parser/unit capability.

2. **the next problem shifts to canonical and reference quality**
   the system still needs to answer:
   - how many high-confidence cleaned rows are converging into stable canonical building / unit assets
   - whether reference-backed and non-reference assetization converge with similar quality
   - whether asset promotion still contains weak-reference, merge, or unit-coverage gaps

Therefore, the next core problem is:

**to push the system from “it can parse” to “it can stably produce canonical address assets,” while making reference fusion and canonical convergence measurable, diagnosable, and improvable.**

## 2. Overall Goal
The goals for this phase are:

1. establish canonical building / unit quality diagnostics
2. establish side-by-side statistics for reference-backed vs. non-reference assetization
3. quantify convergence quality, coverage, and high-risk gaps inside asset promotion
4. provide an actionable diagnostic foundation for later reference-first and canonical-merge improvements

## 3. Core Optimization Targets

### 3.1 Canonical Asset Quality Diagnostics
The system must quantify canonical asset quality, including:
- eligible accepted rows
- unique building keys / unit keys
- reference-backed canonical convergence
- unit-coverage gaps inside multi-unit rows

### 3.2 Reference Fusion Visibility
The system must distinguish between:
- building / unit convergence driven by external reference
- building / unit convergence that still relies only on base-address-key logic
- high-confidence accepted results that still have no reference backing

### 3.3 Assetization Risk Surfacing
The system must explicitly surface:
- high-risk multi-unit rows that still fail to produce unit assets
- accepted rows without reference backing
- hotspot building/unit keys with weak convergence quality

## 4. Concrete Requirements

### Requirement 1: Add canonical/reference quality diagnostics
The system should produce an asset-quality diagnostic result set.

Delivery requirements:
- quantify accepted + promotable rows
- distinguish reference-backed vs. non-reference-backed building / unit candidates
- report unique building keys, unique unit keys, and rows-per-key convergence levels
- include concrete high-risk sample examples

### Requirement 2: Add an asset quality report
The system should generate a dedicated canonical/reference quality report.

Delivery requirements:
- the report is written into `runtime/reports`
- the report includes at least:
  - promotion coverage
  - reference-backed ratio
  - multi-unit-without-unit gap
  - canonical convergence indicators
- the report can be directly reused by later phases

### Requirement 3: Make asset-promotion results explainable
Asset promotion should return more than building/unit counts.

Delivery requirements:
- report reference-backed promotion coverage
- report unresolved accepted rows
- report duplicate-heavy building-key hotspots

### Requirement 4: Later reference-first optimization must be driven by diagnostics
This phase establishes observability first, not a major merge-strategy rewrite.

Delivery requirements:
- later merge/reference improvements must be explainable using this phase’s diagnostics

## 5. Expected Benefit Mapping

### Task 1: Canonical/reference quality diagnostics
- Expected benefit:
  - turn canonical gaps from raw count differences into explainable quality gaps
  - prevent later merge/reference work from becoming blind tuning
- Primary metrics:
  - `canonical_building_gap`
  - `canonical_unit_gap`
  - `promotion_skip_reason_counts`
- Secondary metrics:
  - `reference_backed_building_ratio`
  - `reference_backed_unit_ratio`

### Task 2: Asset quality report
- Expected benefit:
  - make the canonical/reference mainline produce reviewable, archivable, comparable outputs
  - let later iterations choose priorities directly from report evidence
- Primary metrics:
  - stable report generation
  - report includes sample-level examples
- Secondary metrics:
  - high-risk example coverage
  - readability of gap buckets

### Task 3: Asset-promotion observability enhancement
- Expected benefit:
  - make assetization explainable instead of exposing only final building/unit counts
  - separate reference-backed and non-reference contribution to asset convergence
- Primary metrics:
  - `reference_backed_rows_processed`
  - `non_reference_rows_processed`
  - `unique_building_keys_processed`
  - `unique_unit_keys_processed`
- Secondary metrics:
  - `rows_with_units_processed`
  - `avg_rows_per_building_key`

### Task 4: Canonical gap reason buckets and sample-level examples
- Expected benefit:
  - turn “why it did not enter canonical” into directly actionable next-round fixes
  - separate locality loss, reference absence, and unit-asset gaps into different follow-up tracks
- Primary metrics:
  - `promotion_skip_reason_counts`
  - `multi_unit_without_unit_examples`
  - `no_reference_examples`
- Secondary metrics:
  - `duplicate_building_key_hotspots`
  - `multi_unit_unit_coverage`

## 6. Technical Implementation Evolution

This section explains how one requirement may be delivered through multiple technical rounds.  
Future optimization work must be attached back to one of these requirement tracks, instead of only saying “Phase 7 was optimized again.”

### Requirement 1: Canonical/reference quality diagnostics
Technical methods already used:
- **Promotable asset pool filtering**
  - instead of treating all accepted rows as canonical candidates, the system first builds a promotable asset pool from accepted + high-confidence rows
  - benefit: separates asset-quality gaps from low-quality parsing noise
- **Multi-source structured field extraction**
  - locality and street fields are extracted from normalize output, best-candidate parse output, and validation output
  - benefit: reduces false diagnostics when one structured source is incomplete
- **Raw-text locality recovery**
  - when city/province is missing from structured outputs, the system falls back to raw-address locality recovery
  - benefit: reduces false canonical gaps caused by missing locality fields
- **Conservative city -> province backfill**
  - when only city is recovered, province is conservatively backfilled from stable mappings in existing data
  - benefit: further reduces locality-driven promotion skips
- **Sample-level gap evidence**
  - the diagnostics emit `no_reference_examples`, `multi_unit_without_unit_examples`, and `skipped_examples`
  - benefit: turns diagnostics directly into actionable repair targets

Current code carrier:
- `asset_service.py::_derive_asset_quality_diagnostics()`
- `asset_service.py::_classify_promotion_row()`
- `asset_service.py::_extract_structured_fields()`
- `asset_service.py::_recover_locality_from_raw_text()`
- `asset_service.py::_load_city_to_province_map()`

Evolution rule:
- every future enhancement under this requirement must state whether it is:
  - a new diagnostic dimension
  - deeper sample-level explainability
  - or a correction of locality / skip-reason misclassification

### Requirement 2: Asset quality report
Technical methods already used:
- **Dedicated asset-quality report**
  - canonical/reference quality is reported separately from model evaluation reports
  - benefit: assetization quality can be governed independently from parser/model quality
- **Hotspot row-level evidence**
  - building-key and unit-key hotspots are expanded into raw row-level examples
  - benefit: operators can inspect concrete addresses instead of only aggregated counts
- **Canonical object cross-check**
  - hotspot output includes canonical building detail and canonical unit values
  - benefit: makes it possible to distinguish source-row issues from canonical write-path issues
- **Incremental risk-view expansion**
  - the report has progressively added:
    - `reference_gap_reason_summary`
    - `reference_gap_hotspot_details`
    - `unit_convergence_quality_summary`
  - benefit: the report evolves from “status output” into “repair-navigation output”

Current code carrier:
- `asset_service.py::generate_asset_quality_report()`
- `asset_service.py::_fetch_hotspot_row_details()`
- `asset_service.py::_attach_hotspot_details()`

Evolution rule:
- later report work must explicitly state whether it adds:
  - a new risk perspective
  - new evidence detail
  - or a more actionable repair view

### Requirement 3: Asset-promotion observability enhancement
Technical methods already used:
- **Observable promotion process**
  - promotion returns reference-backed/non-reference/unique-key processing statistics
  - benefit: assetization is no longer a black box that only exposes final building/unit counts
- **Pre-write row classification**
  - each row is classified before canonical write
  - benefit: write-path failures become explainable instead of silent
- **Locality fallback before promotion**
  - raw-text locality recovery and conservative `city -> province` backfill run before promotion skips out
  - benefit: reduces avoidable skips on otherwise promotable rows
- **Reference fallback fusion**
  - under street-tail mismatch or weak locality split, the system uses a conservative reference-fallback candidate
  - benefit: reduces non-reference hotspots that are not truly reference-free
- **Authoritative canonical refresh**
  - when reference/fallback evidence exists, canonical building street/locality fields are refreshed from the authoritative reference
  - benefit: avoids a state where the key is reference-backed but the canonical body still carries polluted fields
- **Canonical unit normalization before write**
  - unit strings are normalized before canonical-unit write, such as `NUMBER 2904 -> 2904`
  - benefit: reduces dirty tail values in canonical units

Current code carrier:
- `asset_service.py::promote_results_to_assets()`
- `asset_service.py::_classify_promotion_row()`
- `asset_service.py::_recover_locality_from_raw_text()`
- `asset_service.py::_load_city_to_province_map()`
- `asset_service.py::_select_reference_fallback_candidate()`
- `asset_service.py::_apply_reference_fallback_enrichment()`
- `asset_service.py::_normalize_canonical_unit_value()`

Evolution rule:
- future work here must clearly state whether it improves:
  - promotion coverage
  - reference-fusion correctness
  - or canonical building / canonical unit write-path correctness

### Requirement 4: Diagnostic-driven reference-first / merge optimization
Technical methods already used:
- **Hotspot risk stratification**
  - duplicate keys are not treated as one generic merge problem; they are stratified by reference support, unit spread, and repeat pattern into:
    - normal repeat
    - likely reference gap
    - likely merge review
    - likely multi-unit convergence
  - benefit: avoids large-scale false-positive merge alerts
- **Reference-gap reason decomposition**
  - non-reference hotspots are decomposed into:
    - true no-reference
    - locality mismatch
    - street-tail mismatch
    - street conflict
  - benefit: turns “reference problem” into several actionable subclasses
- **Unit-convergence quality stratification**
  - multi-unit hotspots are further divided into:
    - benign multi-unit convergence
    - unit-normalization issue
    - building-type mixing
    - commercial-unit convergence
  - benefit: clarifies whether the tail problem is in merge, reference, or unit normalization
- **Canonical-unit final-value cross-check**
  - canonical-unit final values are read back to verify whether the write path already corrected the issue
  - benefit: prevents risk classification from relying only on raw-row text
- **Homogeneous single-unit repeat downgrade**
  - when the same building key is only receiving repeated copies of the same `single_unit` address and no unit split exists, it is downgraded to `low_risk_repeat`
  - benefit: prevents duplicate sampling from being misreported as reference gap or merge risk

Current code carrier:
- `asset_service.py::_classify_hotspot_risk()`
- `asset_service.py::_derive_reference_gap_diagnostics()`
- `asset_service.py::_classify_unit_convergence_quality()`
- `asset_service.py::_fetch_canonical_unit_values()`

Evolution rule:
- future work under this requirement must explicitly state whether it is reducing:
  - reference-gap residuals
  - merge-risk residuals
  - or canonical-unit quality residuals

## 7. Current Residual Work

At this point, most high-level Phase 7 goals have largely been achieved.  
The remaining work is no longer about new canonical gaps, but about tail-quality closure:

1. residual `mixed_building_type_review`
- technical methods involved:
  - detection of building-type mixing inside multi-unit hotspots
  - sample-level hotspot detail attachment
- representative cases:
  - the same canonical building still contains a small number of `single_unit` rows
  - while the overall building clearly behaves like multi-unit convergence
- current problem:
  - the report can already identify mixed hotspots
  - but benign noise and true relabel-worthy contamination are not yet fully separated
- objective:
  - separate benign single-unit noise from true relabel-worthy building-type contamination

2. residual `true no_reference_candidate_found`
- technical methods involved:
  - reference-gap reason decomposition
  - conservative reference-fallback attempt
- the main reference-gap line has already been significantly reduced
- the remaining cases are now closer to genuine reference coverage gaps, not street-tail misses
- objective:
  - prepare a later reference expansion list instead of misclassifying them as merge issues

3. residual `reference_candidate_found_but_street_conflict`
- technical methods involved:
  - parser-street / base-key conflict diagnostics
  - hotspot risk layering with row-level detail comparison
- current problem:
  - a small number of rows are not truly reference-free, but still contain parser-street vs reference-street conflict
- objective:
  - continue separating true street conflict from benign repeat
  - prepare a concrete sample list for later reference fusion or parser-street cleanup

## 8. In Scope
- canonical asset quality diagnostics
- reference-backed vs. non-reference assetization statistics
- asset quality report generation
- asset promotion observability enhancement
- high-risk canonical gap examples

## 9. Out Of Scope
- operations-system UI redesign
- known release center / reports center defects
- multi-country canonical strategy
- large-scale asset schema refactoring
- returning parser/unit handling to the main optimization thread

## 10. Acceptance Criteria

### Quality Observability Acceptance
1. the system can output canonical/reference quality diagnostics
2. the system can distinguish reference-backed vs. non-reference assetization coverage
3. the system can quantify multi-unit assetization gaps

### Reporting And Engineering Acceptance
4. the system generates a standalone asset quality report
5. the diagnostics include sample-level examples, not only aggregate counts
6. later phases can directly use these diagnostics to drive merge/reference improvements

## 11. Risks And Watchpoints
- if canonical quality remains unobservable, later merge/reference work will regress into blind tuning
- if only total building counts are tracked, convergence-quality issues will remain hidden
- if reference-backed and non-reference-backed rows are not separated, it will be hard to measure the real benefit of reference fusion

## 12. Completion Criteria
This phase can be considered complete when:
- canonical/reference quality diagnostics are stable and reusable
- an asset-quality report is generated and includes high-risk sample examples
- the gap between reference-backed and non-reference assetization can be quantified and explained
- later merge/reference work now has an observable baseline

## 13. Post-Execution Requirement
This document is an optimization-requirements and execution-plan document, not an execution summary.

After execution, the outcome must be written into a separate:
- execution summary
- update summary
- or phase summary

Execution results must not be backfilled into this plan.
