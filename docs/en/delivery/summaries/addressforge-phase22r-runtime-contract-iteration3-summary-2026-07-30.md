# AddressForge Phase 22R-3 Execution Summary

## API and Worker Runtime Contract Closure

- Date: 2026-07-30
- Status: Completed
- Production model, registry, and Human Gold changes: none

## Requirement and Method

Evaluator, Replay, and Shadow already consumed the shared governed runtime bundle. This iteration aligned API startup, API reload, and Worker reload with the same contract.

The implementation now:

- uses a governed bundle exclusively when API startup validates the active contract
- keeps the current invalid active model in explicit compatibility mode, preserving current production behavior
- validates and physically loads a complete bundle before atomically replacing API services
- fails closed and preserves existing in-memory services when reload validation fails
- remembers the service instance workspace instead of silently reloading the global workspace
- validates the governed bundle before Worker index reload
- distinguishes `manifest`, `configured_path`, and `legacy_path` artifact sources
- provides `scripts/inspect_runtime_state.py` as a fixed, auditable read-only runtime check instead of arbitrary inline Python

## Real Evidence

A real startup and reload check against the current workspace showed:

- the active model contract is invalid
- startup remains in explicit `compatibility`
- Decision uses the configured generic artifact
- reload is blocked with `runtime_manifest_invalid`
- current Decision and Reranker service instances remain unchanged after failure

Candidate model ID 51 had already passed the same shared loader's contract, SHA256, and three-component physical-load checks in 22R-2.

## Validation

- Python compilation passed.
- 31 targeted Runtime, API reload, Worker reload, Registry Gate, Replay, and Evaluator tests passed.
- Covered governed startup/reload, fail-closed preservation, workspace isolation, Worker pre-index blocking, and honest artifact-source identity.

## Conclusion and Next Step

Training, Evaluator, Replay, Shadow, API, and Worker now share the same governed runtime semantics. Compatibility fallback is explicit and cannot pass a governed gate.

Production remains in compatibility because the currently selected legacy registry model lacks a complete immutable contract. Phase 23R will address the single active-model source of truth, lifecycle-state preservation, transactional activation, and readiness reporting without promoting a production model before its quality and evidence gates pass.
