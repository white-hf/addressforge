# AGENTS.md

## Purpose
This document defines the required working method for agents developing, testing, and tuning the AddressForge model and core address-processing system.

The goal is to ensure every agent follows the same closed-loop workflow:

1. inspect the current system state
2. query real data from the database
3. analyze model outputs and failure patterns
4. plan the next optimization requirement
5. implement the change
6. validate on real data
7. compare against previous results
8. repeat only based on evidence

This is mandatory for model, parsing, training, evaluation, replay, canonicalization, reference fusion, and asset-quality work.

## Core Principle

Agents must not optimize blindly.

Every meaningful model or parsing change must be driven by:
- real database evidence
- real address examples
- measurable benchmark change
- clear error-pattern analysis

Do not rely only on:
- code intuition
- synthetic examples
- isolated regex fixes
- UI impressions
- one-off assumptions about model behavior

## Required Development Loop

For all core data-processing and model-quality work, agents must follow this loop:

### 1. Query Real Data First
Before changing model or parsing behavior, inspect the current database state.

Required activities:
- query representative production samples
- query recent human gold
- query current review queue composition
- inspect latest model metrics
- inspect latest evaluation errors
- inspect latest benchmark and release-gate output

Typical goals:
- verify the real failure mode
- confirm whether the issue is distributional, logical, or implementation-related
- confirm whether the issue affects house, apartment, multi-unit, commercial, canonical assets, or reference fusion

Do not start with code changes if the real data shape is still unclear.

### 2. Analyze Failure Patterns
Agents must explicitly identify what kind of failure is occurring.

Examples:
- false unit extraction from double-number house addresses
- true apartment unit under-recall
- single_unit vs multi_unit boundary drift
- commercial misclassification
- reference gap due to street-tail mismatch
- canonical unit normalization tail errors
- gold distribution skew toward hardest cases

The analysis must answer:
- what is failing
- where it is failing
- whether the problem is caused by data distribution, model weighting, runtime logic, parser behavior, or reference coverage
- whether the issue is local or systemic

### 3. Decide the Next Requirement Based on Evidence
Agents must turn the observed problem into an explicit requirement before coding.

A requirement must describe:
- the product/data-processing goal
- the expected benefit
- the technical method category
- the target metrics
- the risk of overfitting or regression

Examples:
- rebalance human-sample selection to avoid hardest-case dominance
- reduce false unit extraction on double-number single-unit houses
- improve apartment unit recall without regressing house precision
- improve canonical unit normalization convergence
- improve reference fusion fallback for street-tail mismatch cases

Do not treat random code edits as iteration work.
Every significant change must correspond to a named requirement or phase task.

### 4. Implement Using Explicit Technical Methods
Agents must describe and apply technical methods, not just "tweak code".

Examples of acceptable technical-method descriptions:
- dual-pool sampling for correction vs calibration
- weighted training to downweight legacy hardest-case review samples
- candidate-level negative features for false unit patterns
- runtime fallback tightening for bare-number unit recovery
- locality recovery using raw-tail and city-to-province mapping
- reference-backed canonical-field refresh
- hotspot risk stratification for canonical convergence

Do not describe the work only as:
- changed function X
- updated file Y
- fixed bug Z

Function and file references are supporting detail, not the method itself.

### 5. Validate on Real Data, Not Only Unit Tests
Unit tests are required but not sufficient.

After implementation, agents must validate using:
- real database queries
- real model artifacts
- real evaluation outputs
- real benchmark comparison
- real replay/shadow output when applicable

Validation should confirm:
- whether the intended failure mode changed
- whether key metrics moved in the expected direction
- whether unrelated areas regressed

Typical metrics include:
- decision_f1
- building_type_f1
- unit_number_f1
- unit_recall
- commercial_f1
- review_rate
- reject_rate
- replay disagreement_rate
- canonical/reference quality counts

### 6. Compare Against Previous Model Behavior
Agents must compare the new output against the previous active or candidate baseline.

At minimum, compare:
- current metric values
- metric deltas
- error buckets
- sample-level output changes on representative cases

Agents must explain whether change came from:
- rules
- learned weights
- data rebalance
- candidate quality
- reference/canonical improvements

Do not report "improved" without showing what improved relative to what.

### 7. Use Iterative Evidence to Plan the Next Step
After validation, agents must decide whether:
- the current requirement is complete
- the current phase still has residual work
- a new phase should begin
- more gold is needed
- more balanced sampling is needed
- the issue is actually data distribution, not model logic
- the next step should move upward to canonical/reference/asset quality

Agents must not keep adding fixes in the same direction if evidence shows the bottleneck moved elsewhere.

## Environment Access Rules

Agents working on AddressForge core logic are expected to use the local runtime environment as part of development and verification.

This includes:
- MySQL
- `.env.local`
- local model artifacts
- local API endpoints
- local console endpoints
- local LLM prescreen endpoint when relevant

Agents must understand how to discover and use the current environment before attempting evidence-based tuning.

## Configuration Discovery

### Primary configuration sources
Agents should inspect configuration in this order:
1. `addressforge/.env.local`
2. `addressforge/.env`
3. `addressforge/src/addressforge/core/config.py`

### What these files define
Typical runtime values include:
- MySQL connection
- workspace name
- active model defaults
- artifact directories
- ingestion mode and source
- third-party ingestion API endpoints
- local API ports
- local console ports
- local LLM endpoint

### Important current code carrier
- `addressforge/src/addressforge/core/config.py`

Agents should not hardcode environment assumptions when the value is already driven by `.env.local` or `config.py`.

## Database Access

### Required database usage
Agents working on model quality, parser accuracy, gold composition, replay, shadow, canonical assets, or reference fusion are expected to query the real MySQL database.

Database-backed verification is not optional for these tasks.

### Current database configuration source
Read from:
- `addressforge/.env.local`
- then resolved in:
- `addressforge/src/addressforge/core/config.py`

### Current database access pattern
Core DB helpers are in:
- `addressforge/src/addressforge/core/common.py`

Typical helper methods:
- `fetch_all(...)`
- `db_cursor()`
- `create_run(...)`
- `finish_run(...)`

### When to use direct SQL
Direct SQL is appropriate for:
- checking gold distribution
- checking review queue composition
- checking recent model versions
- checking replay results
- checking canonical/reference tables
- checking recent raw samples
- validating whether runtime outputs match claimed metrics

### Typical tables agents should inspect
Examples:
- `raw_address_record`
- `address_cleaning_result`
- `gold_label`
- `gold_set_snapshot`
- `active_learning_queue`
- `model_registry`
- `historical_replay_result`
- `canonical_building`
- `canonical_unit`
- `external_building_reference`

### Required behavior
Before claiming a model or parsing improvement, agents should verify at least one of:
- direct SQL sample inspection
- registry metrics inspection
- real queued/reviewed sample inspection
- real canonical/reference asset inspection

## API Access

### Core local API
AddressForge core API is implemented in:
- `addressforge/src/addressforge/api/server.py`

Typical local endpoints include:
- `/api/v1/normalize`
- `/api/v1/parse`
- `/api/v1/validate`
- `/api/v1/explain`
- `/api/v1/gold/labels`
- `/api/v1/gold/freeze`
- `/api/v1/active-learning/queue`
- `/api/v1/active-learning/seed`

Default local API port is defined by:
- `ADDRESSFORGE_PORT`
- current default in config is `8010`

### Console API
Console routes are implemented in:
- `addressforge/src/addressforge/console/server.py`

Typical console endpoints include:
- `/api/v1/control/status`
- `/api/v1/jobs/...`
- `/api/v1/business/...`
- `/api/v1/review/...`

Default console port is defined by:
- `ADDRESSFORGE_CONSOLE_PORT`
- current default in config is `8011`

### When agents should use API instead of direct function calls
Use API or service-layer behavior when validating:
- real request/response shape
- console-visible workflow behavior
- route integration correctness
- request serialization / deserialization effects

Use direct Python calls when:
- validating model logic internally
- testing training/evaluation functions
- faster iteration is needed and route behavior is not the target

## Ingestion Dependency Access

### Ingestion sources
AddressForge supports multiple ingestion modes. Agents must inspect current mode before working on import or incremental sync behavior.

Relevant config fields are in:
- `addressforge/src/addressforge/core/config.py`

Typical ingestion modes include:
- API-driven ingestion
- DB-driven ingestion
- CSV/manual import

### Third-party ingestion API configuration
Inspect:
- `ADDRESSFORGE_INGESTION_API_URL`
- `ADDRESSFORGE_INGESTION_API_ADAPTER`
- `ADDRESSFORGE_INGESTION_API_BATCHLIST_ENDPOINT`
- `ADDRESSFORGE_INGESTION_API_DRIVER_COUNT_ENDPOINT`
- `ADDRESSFORGE_INGESTION_API_ORDERS_ENDPOINT`

### Ingestion provider implementation
See:
- `addressforge/src/addressforge/ingestion/providers.py`

### Required behavior
Before debugging sync/import behavior, agents must confirm:
- ingestion mode
- source adapter
- API endpoint settings
- cursor behavior
- whether the job queue is actually processing

Do not assume a sync issue is a model issue.

## Model Artifact Access

### Artifact location
Model artifacts are stored under:
- `runtime/models`

Configured by:
- `ADDRESSFORGE_MODEL_ARTIFACT_DIR`

### Typical artifact types
Examples:
- `*_training.json`
- `*_eval.json`
- `*_eval.md`
- `*_shadow.json`

### Required artifact inspection
Agents should inspect artifacts when validating:
- learned decision policy
- parser weights
- match-rule weights
- candidate feature weights
- candidate pair weights
- hard-sample profile
- label consistency diagnostics

Do not assume training changes were actually consumed by runtime until the artifact and downstream runtime both confirm it.

## Local LLM Dependency Access

### Current local LLM pattern
LLM prescreening and review assistance use local Ollama/Qwen by default.

Implementation:
- `addressforge/src/addressforge/core/llm_refiner.py`

Typical config:
- `ADDRESSFORGE_LLM_API_URL`
- `ADDRESSFORGE_LLM_MODEL`

Default local endpoint pattern:
- `http://127.0.0.1:11434/api/generate`

### Required behavior
Agents should verify whether LLM output is:
- real local output
- cached output
- fallback output

Do not assume a displayed LLM suggestion came from the live model without checking the actual runtime path.

## Human Review Handling Rule

### Human review remains authoritative
When a workflow step requires:
- human review
- human relabeling
- human gold confirmation
- human batch validation

the agent must treat that step as a real human gate, not an optional delay.

### Required behavior
When such a step is reached:
1. the agent must explicitly notify that human handling is required
2. the agent may wait for human response
3. if there is no immediate response, the agent may continue only with supporting automation

Allowed supporting automation includes:
- LLM prescreening
- draft review suggestions
- queue prioritization
- review batch export
- sample grouping
- relabel candidate preparation

### Forbidden behavior
The agent must not:
- directly convert LLM output into formal human gold
- mark LLM-reviewed results as `label_source = human`
- mark LLM-reviewed results as final accepted human review
- silently replace human review with automated review

### If unattended continuation is required
If work must continue without immediate human response, the agent may only store outputs using explicitly non-human semantics, such as:
- `llm_draft`
- `silver_label`
- `pending_human_review`

Anything that affects:
- training
- evaluation
- release gate
- benchmark comparison
- gold-based model tuning

must still rely on final human confirmation.

## Practical Access Examples

### Use database helpers when:
- checking whether new gold is dominated by `review`
- counting `queued` vs `labeled` review items
- reading recent model registry metrics
- validating canonical/reference coverage
- checking whether a new candidate actually wrote artifacts and metrics

### Use direct Python training/evaluation calls when:
- iterating on parser/model logic quickly
- validating learned weights
- inspecting benchmark metrics before route-level validation

Typical examples:
- `run_baseline_training(...)`
- `run_baseline_evaluation(...)`
- `run_baseline_shadow(...)`

### Use artifact inspection when:
- confirming learned weights were written
- confirming hard-sample profile changed
- confirming replay/shadow/eval outputs were produced

### Use local API routes when:
- validating external request/response behavior
- validating console-triggered workflows
- validating integration-level input/output semantics

## Special Rules For Model Tuning

### A. Never Trust Hardest-Case Samples As Distribution
Review-derived gold is valuable for correction, but it does not represent production distribution.

Agents must distinguish between:
- correction samples
- calibration samples
- fresh data samples
- historical data samples

If model drift appears after small-batch human review, check whether the new gold is overly concentrated in:
- review
- apartment/unit hard cases
- double-number edge cases
- semantic ambiguity cases

### B. Protect the Main System Goal
Model tuning must serve the overall system goal, not only local edge cases.

The current system priority is:
- real address accuracy for houses and apartments in Canada
- especially apartment unit handling
- without collapsing into only a unit extractor
- while protecting house precision and stable building-type classification

### C. Do Not Overfit to One Metric
Improving `unit_recall` while collapsing `building_type_f1` is not acceptable.
Improving `decision_f1` while losing apartment structure quality is not acceptable.

Agents must evaluate the full tradeoff set.

## Required Evidence Before Declaring Success

Agents must not declare model improvement complete unless they can show:
- what data source was inspected
- what environment was used
- what metric changed
- what baseline it changed from
- what real samples were checked
- whether regression risk was checked

At least one of the following must be present:
- DB-backed metric verification
- artifact-backed metric verification
- route-level output verification
- sample-level before/after comparison on real addresses

## Documentation Requirement

For each meaningful iteration:
- define the requirement
- describe expected benefit
- describe technical methods
- describe environment used for validation
- validate actual outcome
- record residual work

Do not describe progress only as "optimized another round".
The documentation must make clear:
- what requirement was being solved
- how it was solved technically
- what changed in the data or metrics
- what remains unresolved

## Completion Standard

A requirement is not considered complete just because:
- code compiles
- tests pass
- logic seems better

A requirement is complete only when:
- the implementation is done
- real validation has been performed
- results are compared against the prior baseline
- the residual problem is understood
- the next step is evidence-based

## Short Operating Summary

Agents must work like this:

1. inspect real data
2. identify the actual failure pattern
3. define the next requirement
4. implement using explicit technical methods
5. validate on real database-backed outputs
6. compare against the previous baseline
7. decide the next iteration based on evidence

This loop is mandatory for all non-console core model and address-processing development.
