# AddressForge Phase 23R Execution Summary

## Registry, Release Gate, Reload, and Rollback Closure

- Date: 2026-07-30
- Status: implementation completed; operational rehearsal pending
- Production promotion, rollback, and Human Gold changes: none

## Problem and Method

Real Registry evidence showed that `workspace_registry.default_model_id` pointed to model ID 1 while no model had `is_default = 1`, and Evaluation had changed the active lifecycle status to `evaluated`. Active resolution could also fall back to the most recently updated model.

This iteration:

- makes `workspace_registry.default_model_id` the primary active-model source
- allows only a unique legacy `is_default = 1` compatibility bridge
- forbids arbitrary latest-model fallback
- prevents Training, Evaluation, and Shadow registration from moving lifecycle state backward
- stops Evaluation and Shadow from changing activation flags
- removes bootstrap mutations from read-only model/workspace GET routes
- creates a structured, read-only release readiness report
- makes Promote workspace-locked and compare-and-swap guarded
- makes Rollback target an explicit immutable, contract-valid version
- performs current demotion, target activation, and workspace-pointer update in one transaction

## Real Candidate Readiness

A fixed command evaluated model ID 51 from its real training and evaluation artifacts without database access or writes.

Passed:

- all absolute benchmark safety floors
- Runtime manifest, physical components, sidecars, and SHA256
- Shadow numeric gate (`shadow_advantage = 0.0604`, `disagreement_rate = 0.0644`)

Blocked:

1. relative Active comparison failed on `reject_rate`
2. Replay had zero successfully processed samples
3. Assist readiness failed three sub-checks: trial-vs-shadow, eligible sample count, and Assist Gold match rate

## Artifact Persistence Fix

The existing ID 51 evaluation JSON is not self-contained: its Registry merged view has the runtime contract, but the evaluation file alone does not. Evaluator now merges the immutable existing contract before writing future evaluation artifacts. The current ID 51 file was not modified.

## Validation and Residual

- 44 targeted Registry, Release, Rollback, Runtime, Replay, and Evaluator tests passed.
- No arbitrary `python -c`, production Registry write, promotion, or rollback was used.

Implementation is complete, but the real Promote → Reload → Rollback rehearsal remains pending because ID 51 correctly fails the Release Gate. Phase 24R will now persist row-level Replay evidence and produce successful real replay samples before the rehearsal is reconsidered.
