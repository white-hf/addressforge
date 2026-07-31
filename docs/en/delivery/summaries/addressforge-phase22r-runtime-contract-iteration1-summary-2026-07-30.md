# AddressForge Phase 22R-1 Execution Summary

## Runtime Manifest Completeness and SHA256 Release Gate

## Document Info

- Date: 2026-07-30
- Phase: 22R
- Iteration: 22R-1
- Status: Completed
- Change type: Runtime Contract / Training Artifact / Release Gate
- Production data operations: read-only queries only
- Production model operations: no training, promotion, reload, or rollback

## Requirement

The previous release gate checked only artifact paths that were already present. A completely absent component could therefore produce an empty or incomplete physical-file check. Existing manifests also lacked hashes, so an evaluation could not prove that release consumed the same physical files.

This iteration required:

1. Decision, Reranker, and BuildingType as mandatory components
2. Decision model and metadata sidecar as a pair
3. SHA256 binding for newly trained artifacts
4. Registry and manifest identity agreement
5. Fail-closed promotion on every contract violation
6. No change to current online inference behavior

## Production Evidence Before Development

Read-only inspection of workspace `default` found:

| Object | Current fact | Main issue |
|---|---|---|
| Workspace | `default_model_id = 1` | no registry row has `is_default = 1` |
| Model ID 1 | `canada_default_v1` | versioned Decision files missing; Reranker and BuildingType unbound |
| Model ID 43 | `v1` | latest evaluation but no runtime binding or component artifacts |
| Model ID 50 | `v20260517_week4` | physical component files exist but schema, bundle ID, and hashes are absent |

The generic mutable Decision, Reranker, and BuildingType files still exist. Therefore, old metrics cannot be attributed to one immutable runtime bundle.

## Technical Method

- Added a central manifest resolver with explicit resolution issues.
- Defined required component paths:
  - Decision: model and metadata
  - Reranker: model
  - BuildingType: model
- Added manifest schema `1.0`, deterministic runtime bundle ID, and SHA256 binding for new training artifacts.
- Changed the release gate to fail closed on missing identity, binding, component, file, hash, or hash mismatch.
- Returned structured `runtime_manifest_validation` evidence on failure.

Legacy paths do not satisfy the governed runtime contract.

## Implementation

- Added `src/addressforge/models/runtime_manifest.py`
- Updated Trainer to emit hash-bound runtime contracts
- Updated Registry Release Gate to use central validation
- Added contract, hash, identity, nested-evaluation, and gate tests

No production registry rows, model files, inference policies, or data were changed.

## Validation

- Python compilation: passed
- Targeted Runtime/Registry/Trainer/Evaluator/Replay tests: `25 passed`
- A complete hash-bound manifest passed the simulated release gate.
- Missing components, modified files, and identity mismatches failed closed.
- Nested evaluation metrics preserved the complete runtime contract.

Full test discovery ran 120 tests with 2 skipped, 1 failure, and 17 errors. The observed failures were dominated by sandbox-blocked local DB/API access, online embedding loading, and stale test interfaces. All 25 tests in the changed runtime-contract scope passed.

The new validator was then run read-only against the production registry:

| Model ID | Validation | Issues | Main finding |
|---:|---|---:|---|
| 1 | Failed | 7 | missing files/components and no schema/hash |
| 43 | Failed | 7 | missing runtime binding and all components |
| 50 | Failed | 7 | missing schema, bundle ID, and four SHA256 values |

These results matched the pre-development audit.

## Before and After

| Capability | Before | After |
|---|---|---|
| Required components | only present paths checked | all three components mandatory |
| Decision sidecar | partial check | mandatory contract field |
| File identity | path existence | path plus SHA256 |
| Manifest identity | distributed fields | schema, bundle ID, registry agreement |
| Failure evidence | reason string | reason plus structured issues |
| New training output | no hash contract | automatic SHA256 binding |
| Online behavior | current fallback behavior | unchanged |

## Residual Risk and Next Iteration

Evaluator, Replay, API, and Worker still duplicate manifest merge and fallback logic. No current production registry model satisfies the new contract. Legacy manifests must not be silently backfilled with hashes because that would misattribute current files to historical evaluations.

Phase 22R-2 will:

1. move Evaluator and Replay to the shared resolver
2. prohibit silent legacy fallback for an explicitly selected model version
3. emit separate Active and Candidate runtime identities
4. introduce compatibility and governed-strict modes
5. validate strict behavior against real model IDs 1, 43, and 50
