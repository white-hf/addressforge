# AddressForge Iteration Execution Plan - 2026-07-30

## Phase 22-29: Production Trust, Model Quality, and Asset Convergence

## Document Info

- Document Type: Iteration Execution Plan / Delivery Plan
- Status: Proposed
- Evidence Basis: 2026-07-30 read-only production audit, current product goals, next-generation ML design, and the Phase 19-24 plan
- Plan Role:
  - re-accept the unfinished Phase 22-24 outcomes
  - open Phase 25-29 only after a trustworthy baseline exists
- Overall Goal: Move the system from “operational and capable of producing promising reports” to “measurably trustworthy, runtime-consistent, quality-qualified, continuously asset-producing, and safe to release and roll back”

## 1. Why This Convergence Plan Is Needed

The target architecture remains valid:

- Parser / Normalization recovers structure
- Reference / Canonical provides facts and standard entities
- DecisionModel / Reranker / BuildingTypeModel provides supervised learning
- Policy / Safety Guard controls model impact
- Human Review / Gold / Freeze / Evaluation / Shadow / Gate forms the learning loop

The main gap is not missing architecture. The gap is that the production facts across registry, artifacts, runtime, evaluation, replay, and release status are not fully consistent.

This plan therefore restores four forms of trust before another tuning cycle:

1. runtime identity
2. gold and evaluation
3. release gates
4. active/candidate comparison

## 2. Planning Baseline From the 2026-07-30 Audit

### 2.1 Data and Operations

- Raw records: `270,874`
- Cleaning results: `270,874`
- Decision distribution:
  - `accept = 268,438`
  - `enrich = 2,034`
  - `reject = 384`
  - `review = 16`
  - `pending = 2`
- Human Gold rows: `1,789`
- Active-learning rows: `3,215`
- Queued active-learning tasks: `1,402`

The gap between only 16 current review results and 1,402 queued tasks needs an explicit operational explanation and lifecycle.

### 2.2 Registry and Runtime

- Newest registered candidate:
  - ID 50
  - `v20260517_week4`
  - `decision_f1 = 0.2991`
  - not promoted
- Most recently evaluated target:
  - ID 43
  - `v1`
  - updated 2026-06-20
  - `promote_recommended = false`
- Workspace default:
  - `default_model_id = 1`
  - registry row is `evaluated`
  - `is_default = 0`
- Model IDs 51 and 52 mentioned in a later summary are not present in the current production registry

The current runtime also mixes missing versioned sidecars, mutable fallback artifacts, and files produced at different times. A model version does not yet resolve uniquely to one immutable runtime bundle.

### 2.3 Latest Auditable Metrics

| Metric | Previous Baseline | Latest Evaluation | Documented Target | Assessment |
|---|---:|---:|---:|---|
| `decision_f1` | 0.7214 | 0.9416 | ≥0.95 or significant gain | Strong relative gain; below absolute target |
| `building_type_f1` | 0.8441 | 0.8700 | ≥0.97 | Not met |
| `unit_number_f1` | 0.8311 | 0.8392 | Non-regressing improvement | Small gain |
| `unit_recall` | 0.7505 | 0.7628 | ≥0.70 | Met |
| `unit_precision` | 0.9312 | 0.9325 | ≥0.98 | Not met |
| `commercial_f1` | 0.1966 | 0.3010 | Stable improvement | Still weak |
| `review_rate` | 0.0014 | 0.0001 | Lower without quality loss | Requires false-accept audit |
| Replay disagreement | - | 0.0088 | ≤0.05 | Numerically met |
| Assist Gold Match | - | 0.7722 | ≥0.90 | Not met |

Additional evidence:

- ML Shadow Decision F1: `0.9640`
- Assist Trial F1: `0.9419`
- Assist Trial advantage: only `+0.0003`
- Assist status: `needs_more_assist_calibration`
- BuildingType ML shadow measurement is currently invalid

These values are an audit baseline, not yet a release baseline, because runtime identity is not fully trustworthy.

### 2.4 Data, Reference, and Asset Risks

The audit found:

- suspicious human labels containing locality/street tails as units
- unit/civic reversal cases
- 72 saved unit errors in `REFERENCE_MISSING_UNIT`
- reference-bearing cleaning results: `15,911` or about `5.87%`
- only one current external-reference source
- canonical building/unit data not refreshed through the latest raw-data date

The quality bottleneck has therefore moved beyond parser-only work.

## 3. Governing Rules

1. Do not tune against an untrusted measurement system.
2. Restore runtime and evaluation truth before optimizing metrics.
3. Keep Human Gold authoritative.
4. Protect house precision, apartment-unit quality, building-type stability, commercial boundaries, decision safety, and review cost together.
5. Keep parser/reference/canonical as the structural backbone.
6. Progress gradually:

```text
Shadow
  → Assist
  → Guarded Override
  → Partial Rollout
  → Default On
```

## 4. Execution Sequence

```text
Phase 22R Runtime Contract Re-acceptance
  → Phase 23R Registry / Gate / Reload / Rollback Re-acceptance
  → Phase 24R Observability and Evidence Persistence
  → Phase 25 Gold and Evaluator Integrity
  → Phase 26 Decision Safety and Assist Calibration
  → Phase 27 House / Apartment / Commercial Quality
  → Phase 28 Reference / Canonical / Retrieval Convergence
  → Phase 29 Long-running Shadow and Controlled Release
```

`R` means re-acceptance of an existing phase, not a redesign.

## 5. Phase 22R: Manifest-bound Runtime Contract

### Goal

Make one model version resolve to one immutable runtime bundle used consistently by training, evaluation, replay, shadow, API, and worker paths.

### Technical Methods

- immutable version directories
- validated manifest schema
- complete Decision/Reranker/BuildingType sidecars
- parser/rule/reference/policy version binding
- artifact SHA256
- separate active and candidate runtime instances
- explicit, recorded fallback semantics

### Completion Criteria

- Registry, workspace, runtime endpoint, and evaluation artifact report the same model ID/version/hash
- all physical artifacts and sidecars are traceable
- missing sidecars block evaluation and promotion
- silent fallback is impossible
- production behavior is unchanged during this phase

## 6. Phase 23R: Registry, Gate, Reload, and Rollback

### Goal

Create one source of truth for the active model and make lifecycle operations transactional, verifiable, and auditable.

### Technical Methods

- transactional activation
- consistent `default_model_id`, `is_default`, and `status`
- evaluation status protection
- cache invalidation before reload
- fail-closed preflight and release gates
- immutable rollback targets

### Completion Criteria

- exactly one active model exists
- reload does not silently change model selection
- promote and rollback synchronize registry, memory, and output
- gate failures are structured and explainable
- a non-production-impacting lifecycle drill succeeds

## 7. Phase 24R: Observability and Evidence Persistence

### Goal

Make every quality statement traceable to runtime evidence and representative samples.

### Requirements

- persist every replay mismatch with raw ID and runtime identity
- retain active, candidate, and current-production outputs
- persist failures rather than recording false success
- separate disagreement rate, regression risk, and adjudicated candidate win rate
- align dashboard/report queries with the same source of truth
- explain current review results versus queued review tasks

### Completion Criteria

- all latest replay mismatches are queryable
- candidate win rate comes only from Human Gold or formal adjudication
- console/report figures match direct database checks

## 8. Phase 25: Gold and Evaluator Integrity

### Goal

Build trustworthy supervision and a frozen release baseline.

### Technical Methods

- human audit of suspicious labels
- task-aware Gold identity using `(source_id, task_type)`
- field-level label validation
- corrected BuildingType ML evaluation
- duplicate and split-leakage audit
- separate correction and calibration/fresh-production pools
- immutable holdout snapshot

### Human Gate

Agents and LLMs may export, group, prioritize, and suggest corrections. Only humans may approve label changes as Human Gold or approve a formal holdout.

### Completion Criteria

- suspicious labels are human-resolved
- conflict, duplicate, and leakage reports exist
- all model metrics evaluate the intended Gold field
- active and candidate are re-evaluated on the same frozen set
- a trustworthy baseline report is published

## 9. Phase 26: Decision Safety and Assist Calibration

### Goal

Improve DecisionModel behavior while controlling aggressive accepts and false rejects.

### Technical Methods

- transition-specific assist policies
- correction/calibration dual-pool sampling
- minority-label weighting
- candidate-level conflict features
- independent accept/reject safety guards
- proposal → offline comparison → shadow-only calibration

### Completion Criteria

- `decision_f1 ≥ 0.95`, or an agreed significant gain on the trusted frozen set
- Assist Gold Match ≥0.90
- Assist Trial materially beats the heuristic baseline
- aggressive-accept errors do not increase
- reject precision and recall are reported
- the system remains shadow-only if gates fail

## 10. Phase 27: House, Apartment, and Commercial Quality

### Goal

Improve apartment-unit handling while protecting house precision and commercial boundaries.

### Technical Methods

- unit/civic candidate-pair construction
- candidate-level negative features
- exact numeric alignment
- supervised reranking
- supervised BuildingType classification
- commercial entity plus suite/floor joint features
- parser/reference evidence fusion

### Completion Criteria

- `building_type_f1 ≥ 0.97`
- `unit_precision ≥ 0.98`
- unit recall does not regress from the trusted baseline
- `unit_number_f1` improves materially
- commercial quality improves without regressions
- representative house samples show no systemic regression
- gains primarily come from learning, candidates, and data quality rather than isolated regex growth

## 11. Phase 28: Reference, Canonical, and Retrieval Convergence

### Goal

Move reference- and asset-driven failures to the correct architectural layer.

### Technical Methods

- continuous canonical building/unit production
- canonical convergence audit
- multi-source reference fusion
- entity resolution
- exact numeric guards
- lexical/spatial/vector hybrid retrieval
- pairwise reranking
- provenance-backed unit mining

### Completion Criteria

- canonical jobs process new data continuously
- reference coverage improves from the trusted baseline
- Candidate Recall@10 ≥0.995
- Reranker MRR ≥0.98
- duplicate-entity fusion accuracy ≥0.99
- every mined unit retains source and confidence provenance
- asset gains reduce unit, review, or enrichment failures

## 12. Phase 29: Long-running Shadow and Controlled Release

### Execution Path

1. Frozen Gold offline gate
2. large historical replay
3. 7-14 day online shadow
4. human adjudication of disagreement samples
5. guarded assist
6. partial rollout
7. default-on or keep-active decision

### Completion Criteria

- candidate disagreement win rate ≥0.90
- zero unhandled crashes during shadow
- per-address latency delta ≤10ms
- no key quality regression
- no abnormal review/reject distribution drift
- offline, replay, and shadow use the exact same manifest
- promote/reload/rollback drill succeeds
- monitoring, alerts, and audit records are complete

Auto-promotion stays disabled until this phase is complete.

## 13. Stage Gates

### Gate A: Measurement Trust

Requires Phase 22R-25.

Before it passes:

- no model-improvement claims
- no production threshold tuning
- no candidate promotion

### Gate B: Offline Quality

Requires the relevant Phase 26-28 goals.

Before it passes:

- no guarded override
- no partial rollout

### Gate C: Production Release

Requires Phase 29.

Before it passes:

- no default-on
- no auto-promotion

## 14. Required Loop for Every Phase

1. query current production data
2. freeze the phase baseline and sample scope
3. emit error buckets and representative samples
4. define named requirements
5. document technical methods and protected metrics
6. implement the smallest complete slice
7. run unit, integration, and regression tests
8. validate with real DB, artifact, replay, or route evidence
9. compare metrics and samples against baseline
10. publish an execution summary
11. decide whether to continue or advance

## 15. Required Evidence Per Iteration

- environment and code version
- data time range
- frozen dataset/snapshot
- active/candidate runtime identity
- artifact paths and hashes
- before/after metrics
- before/after error buckets
- representative before/after samples
- regression checks
- gate outcome
- residual risks
- next recommendation

## 16. Explicit Non-goals Before Phase 27 Completion

- global multi-country expansion
- end-to-end Transformer parser
- large database migration
- unrelated console visual redesign
- product features unrelated to core quality
- unvalidated full rule rewrite
- storing LLM output as Human Gold

## 17. Plan Success Definition

This plan is complete only when:

1. Active/Candidate/Runtime/Artifact identity is immutable and consistent
2. Gold, frozen sets, and evaluators are trustworthy
3. Decision, BuildingType, Unit, and Commercial meet agreed quality gates
4. Reference/Canonical continuously processes new data
5. Replay persists real per-sample differences
6. 7-14 day shadow has human-adjudicated win evidence
7. Gate, promote, reload, and rollback are verifiable
8. production state is observable, explainable, and auditable
9. no critical-path phase remains open

## 18. Recommended First Slice

After plan approval, the first iteration must not change model behavior.

It should only:

1. freeze the current registry, workspace, runtime identity, and physical artifact inventory
2. produce the Phase 22R discrepancy report
3. define the single source of active-model truth and the manifest contract
4. define the smallest Phase 22R implementation slice and regression-test scope

Implementation begins only after that evidence package is reviewed.
