# AddressForge Phase 24R Execution Summary

## Row-level Replay Evidence Persistence

- Date: 2026-07-30
- Status: implementation completed; live migration and replay pending
- Model behavior and production database changes: none

## Problem and Method

The `historical_replay_result` table existed, but Replay never wrote to it. Only 50 in-memory mismatches were retained, failures had no row identity or error evidence, zero successful rows produced a misleading consistency score of 1.0, and the business readiness endpoint used a weaker gate than Promote.

This iteration adds:

- run-level Candidate/Active IDs, runtime identities, requested/processed/failure/disagreement counts, status, error, and completion time
- row-level Current/Candidate/Active outputs and JSON
- Candidate-vs-Active, Candidate-vs-Current, and Active-vs-Current flags
- persisted success and failure rows with error text
- atomic summary and row-evidence upsert
- full mismatch counts independent of the 50-row response preview
- queryable persisted failures
- idempotent forward schema migration
- one shared governed readiness report for business status and Promote

## Validation

- 48 targeted tests passed.
- A broad run executed 148 tests: 1 failure, 17 errors, and 2 skips remained.
- The broad failures are concentrated in tests requiring local MySQL/port 8011, blocked HuggingFace downloads, stale Reranker method expectations, and outdated DummyVectorEngine signatures.

Targeted regression is green; the repository-wide baseline is not yet green and is not reported as such.

## Why Live Replay Was Not Run

Formal Replay requires governed Active and Candidate runtimes. Candidate ID 51 is contract-valid, but active ID 1 is not. Allowing a silent compatibility Active would violate Phase 22R, while backfilling the production Active contract requires a separate behavior-equivalence migration. The production Replay tables also do not yet have the Phase 24R migration.

Live migration and Replay therefore remain pending. Phase 25 can still audit Gold distribution, frozen-set integrity, and field-label trust without changing the production Active model.
