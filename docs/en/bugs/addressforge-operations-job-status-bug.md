# AddressForge Operations Job Status Bug

## Issue Type
- Functional gap
- Status visibility defect
- Task orchestration inconsistency

## Summary
In the current operations system, when a user clicks `Start Training` on the `Dashboard`, the UI only shows `job dispatched`, but the user cannot reliably determine from the page whether training has finished, and therefore cannot safely decide whether it is time to run the next step, `Run Evaluation`.

This is not merely a UX optimization problem. It is a clear functional defect: **the training action is not fully integrated into the unified job-status system, and the status endpoint does not return the data required by the page.**

## Reproduction Path
1. Open `Dashboard`
2. Click `Start Training`
3. The page shows `job dispatched`
4. Check the `Recent Jobs` table at the bottom of the page
5. Observe that the new training task does not appear with a reliable lifecycle state, so the user cannot tell:
   - whether it is still running
   - whether it has completed successfully
   - whether it has failed
   - whether it is safe to proceed to `Run Evaluation`

## Current Code-Level Problems

### 1. The frontend expects `recent_jobs`, but the backend does not return it
The `Dashboard` task table depends on `/api/v1/control/status` returning a `recent_jobs` field.

However, the current backend implementation:
- [src/addressforge/console/server.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/console/server.py:63)

returns only:
- `workspace`
- `gold_labels`
- `active_learning`
- `job_counts`
- `job_kind_counts`
- `continuous_mode`

It does not return:
- `recent_jobs`

As a result, the frontend table is empty or cannot reflect real task records.

### 2. `training_once` does not enter the unified job queue
The `Dashboard` training button currently calls:
- `POST /api/v1/jobs/trigger`

In the backend:
- [src/addressforge/api/routes/jobs.py](/Users/whitetang/Desktop/work/AddressesSystem/addressforge/src/addressforge/api/routes/jobs.py:51)

`training_once` is executed synchronously via:
- `run_training_pipeline(...)`

instead of:
- `enqueue_job(...)`

This means:
- training does not enter the unified `control_job` / `job_service` tracking system
- training does not naturally appear in `Recent Jobs`
- training does not share the same state model as `ingestion_once / cleaning_once / evaluation_once`

### 3. The page message does not match the actual execution model
After clicking training, the frontend says:
- `job dispatched`

But the backend is not actually dispatching a queued async job.
It is executing synchronously.

This creates a frontend/backend semantic mismatch:
- the UI implies a trackable queued task
- the backend behaves like an immediate execution path

### 4. Training, evaluation, and shadow use inconsistent task models
In the current system:
- `ingestion_once` / `cleaning_once` / `evaluation_once` use the unified queue
- `training_once` uses synchronous execution
- `shadow` is an automatic follow-up after evaluation

This makes it hard for operations users to form a stable task mental model:
- which actions have visible task states
- which actions do not
- which actions auto-follow

## Direct Impact on the Workflow
This issue directly affects the operations execution chain:

1. users cannot confirm whether training has finished
2. users cannot know whether they should proceed to `Run Evaluation`
3. users cannot distinguish between “training failed” and “training still running”
4. the `Recent Jobs` panel cannot be used as a reliable execution indicator
5. the workflow `freeze gold -> retrain -> evaluate` is blocked at the status-check stage

## Explicit Repair Requirements
This section lists repair requirements only, not product solutions.

### Required Repair Goals
1. `training_once` must be integrated into the unified job-status system, or provide an equivalent traceable state model
2. the `Dashboard` `Recent Jobs` section must return and display real recent task records
3. the user must be able to see the training task lifecycle clearly:
   - `queued`
   - `running`
   - `succeeded`
   - `failed`
4. the user must be able to use the task state to decide whether it is safe to proceed to `Run Evaluation`
5. frontend messaging must match the backend execution model; the system must not continue to say “job dispatched” for actions that are not actually represented as jobs

## Conclusion
This is a functional defect that can block the operations workflow and should not be treated as a pure UX issue.

At its core, the current system has:
- incomplete job-status API output
- training not integrated into the unified job system
- inconsistent task semantics between frontend and backend

It should therefore be handled as a functional repair item, not merely a usability improvement.
