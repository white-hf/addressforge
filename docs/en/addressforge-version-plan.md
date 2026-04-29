# AddressForge Iteration Plan

> English: Iteration plan focused on Canada address quality first.

> 中文：以加拿大地址质量为核心的迭代开发计划。

## 1. Current Goal

At the current stage, AddressForge should no longer prioritize platform shell polish first. The primary targets are:

- make Canada / North America address cleaning accurate
- make model training and tuning real and measurable
- strengthen gold / active learning
- make release benchmark the default evaluation standard
- turn cleaning outputs into reusable canonical address assets

This changes the priority order to:

1. address cleaning accuracy
2. model training and tuning
3. gold / active learning
4. evaluation system
5. building / unit / reference quality

Console polish, platform abstraction, and third-party extensibility remain in scope, but no longer lead the roadmap.

## 2. Iteration Principles

1. Finish Canada first, then think about other countries
2. Make benchmark real before promotion
3. Fix real high-frequency failures before chasing long-tail elegance
4. Build canonical address assets before platform polish
5. Every iteration must answer whether quality improved or regressed

## 3. Iteration Map

### Iteration 1: Canada Parsing Baseline

Goal:

- cover high-frequency Canada address patterns
- stop obvious misses on unit / building type / commercial detection

Scope:

- `apt / suite / rm / fl / #`
- `basement / lower / upper`
- `rear / front / side`
- `main floor / ground floor / gf`
- `2nd/3rd floor`
- `penthouse / ph`
- `building / bldg`
- `house / multi_unit / commercial` boundaries
- city/province tail cleanup and street tail cleanup

Exit criteria:

- the Canada benchmark sample set passes reliably
- parser failures are no longer concentrated in these high-frequency patterns

### Iteration 2: Canada Benchmark and Error Buckets

Goal:

- establish release-grade benchmark
- drive improvements with explicit error buckets rather than intuition

Scope:

- `decision`
- `building_type`
- `unit_number`
- `commercial`
- `accept/review/reject rate`
- failure buckets

Exit criteria:

- evaluator emits a stable release benchmark
- candidate and active results can be compared under the same benchmark

### Iteration 3: Gold and Active Learning

Goal:

- strengthen training signals
- make the system identify which samples are most valuable for human review and learning

Scope:

- human gold
- freeze
- active learning queue
- error-driven sampling
- benchmark set expansion

Exit criteria:

- representative Canada gold set exists
- active learning actively feeds training iteration rather than being passive storage

### Iteration 4: Training, Evaluation, Shadow, Promote

Goal:

- turn the model loop into the main path for measurable quality improvement

Scope:

- train
- eval
- shadow
- promote
- release benchmark gate

Exit criteria:

- a new model cannot be promoted without benchmark evidence
- candidate vs active comparison is reproducible

### Iteration 5: Canonical Address and Reference Quality

Goal:

- turn cleaning results into stable address assets, not just parse output

Scope:

- canonical building
- canonical unit
- reference-first decisions
- building / unit deduplication and consolidation

Exit criteria:

- multiple variants of the same address converge into stable assets
- parser/reference conflicts have explicit handling rules

### Iteration 6: Historical Replay and Release Readiness

Goal:

- make the system ready for historical replay, release comparison, and measurable acceptance

Scope:

- historical replay
- release benchmark report
- version-to-version comparison
- release gate

Exit criteria:

- a large historical batch can be replayed and compared quantitatively
- a release decision can be justified with benchmark output

### Iteration 7: Country Abstraction After Canada

Goal:

- only after Canada is complete, extract the country-level plugin boundary

Scope:

- solidify Canada profile
- parser / reference / benchmark country adapters
- support other countries as a later extension

Exit criteria:

- Canada-specific logic is no longer scattered across the core
- the system starts to support country-level extension structurally

### Iteration 8: Canada Decision Fusion and Real Training

Goal:

- move from policy-only learning to a training path that actually changes candidate ranking and final decisions
- make the trained artifact participate in benchmark, shadow, and replay as a real model version

Scope:

- standardized parser feature vector
- parser reranker / parser weight learning
- decision calibration
- hard binding between training artifact and inference path
- candidate model evaluation by explicit model version
- fix the current training/inference breakpoints:
  - missing `RerankerArtifactLoader`
  - missing `AddressRequest.reranker_version`
  - reranking trainer not aligned with the current schema
- parser-weight learning must come from real gold comparisons, not constant-correct labels

Detailed task requirements:

1. Reranker runtime closure
- implement `RerankerArtifactLoader`
- add `reranker_version` to `AddressRequest`
- make `parse()` load reranker artifacts by requested version or active version
- provide an explicit fallback path when artifacts are missing; no runtime crashes

2. Training data extraction aligned with the live schema
- stop reading nonexistent columns in `reranking_trainer`
- extract usable features from `parser_json` / `validation_json`
- derive supervision labels from `gold_label` vs `address_cleaning_result`
- remove any fake supervision such as `target_is_correct = 1`

3. Standardized parser feature vector
- define parser-level feature fields
- define validation-level feature fields
- keep feature names and types stable across trainer / benchmark / replay

4. Decision-policy learning
- `decision_policy` must learn more than thresholds
- include explainable parser weight / disagreement weight / reference weight terms
- expose these parameters in the training artifact

5. Version-bound evaluation
- benchmark / shadow / replay must load the requested model version runtime
- eliminate cases where a candidate version label is evaluated with default behavior

Exit criteria:

- a newly trained version changes runtime behavior in a measurable way
- candidate vs active differences are reproducible in benchmark, shadow, and replay
- there is no longer any “training succeeded but inference did not change” path
- the parse path no longer crashes on missing reranker runtime pieces

### Iteration 9: Canada Gold Expansion and Review Quality

Goal:

- expand representative Canada gold
- make review and active learning continuously feed training quality

Scope:

- representative gold expansion for house / multi-unit / commercial
- more samples for missing unit, parser disagreement, and reference conflict
- quality checks on the review -> gold_label -> active_learning_queue loop
- error-driven active learning prioritization
- continued benchmark set expansion
- validate that:
  - review outputs and gold labels stay consistent
  - active-learning reasons come from real error buckets
  - LLM evidence affects review/gold quality rather than only appending comments

Detailed task requirements:

1. Gold expansion design
- house
- multi-unit
- commercial
- missing unit
- parser disagreement
- reference conflict
- rural / low-confidence long-tail samples

2. Review loop quality
- review submission must persist reliably into `gold_label`
- `active_learning_queue` status must advance correctly
- review samples must remain traceable to source, reason, and risk points

3. Active-learning prioritization
- priority cannot depend only on confidence
- add error bucket, parser disagreement, reference conflict, and commercial-vs-apartment boundary factors

4. Benchmark expansion
- benchmark must include more than curated happy-path samples
- include replay-derived real error samples
- benchmark must cover the failure classes used by the release gate

Exit criteria:

- gold covers the main Canada address categories with useful representation
- active learning produces high-value training samples instead of passive storage
- evaluator error buckets feed back into review and sampling strategy

### Iteration 10: Canonical Asset Consolidation at Scale

Goal:

- turn parsing outputs into stable building / unit address assets
- validate canonical merge and reference-first semantics at larger Canada scale

Scope:

- final canonical building / canonical unit schema
- workspace-aware canonical asset isolation
- building / unit merge keys and deduplication rules
- reference provenance and conflict priority
- idempotent asset promotion and correct newly-added counts
- remove the long-term compatibility layer between legacy canonical tables and the new canonical semantics

Detailed task requirements:

1. Canonical schema closure
- define final fields for `canonical_building` / `canonical_unit`
- define workspace-aware primary or unique keys
- define source attribution and reference provenance structure

2. Asset merge rules
- building merge key
- unit merge key
- normalization and merge logic for multiple textual variants of the same address
- split-and-reconverge logic for building plus unit identity

3. Promotion semantics correction
- `new_buildings` / `new_units` must mean newly created assets
- repeated upserts must not count as new assets
- promotion must be idempotent

4. Reference-first implementation
- parser vs reference conflict priority
- fallback when reference is missing
- distinct canonical rules for commercial, multi-unit, and single-unit addresses

Exit criteria:

- variants of the same address converge into stable assets
- canonical promotion does not mix workspaces
- promotion counts reflect actual new assets rather than repeated attempts

### Iteration 11: Historical Replay at Canada Scale

Goal:

- run true replay over Canada historical data
- use replay evidence as a release decision input

Scope:

- full replay run / result persistence
- candidate vs active replay comparison
- mismatch buckets
- replay summary report
- replay metrics added into release benchmark / release report
- replace the current replay simulation with:
  - real candidate runtime execution
  - real active runtime execution
  - no simulated decisions or fabricated consistency scores
- replay failure visibility that can block promotion

Detailed task requirements:

1. Replay runtime
- active runtime must load the real active model
- candidate runtime must load the real candidate model
- no simulated decisions or fabricated consistency scores

2. Replay persistence
- `historical_replay_run` stores summary information
- `historical_replay_result` stores row-level comparisons
- mismatch samples must remain queryable and bucketable

3. Replay metrics
- decision match rate
- building type match rate
- unit number match rate
- candidate vs active disagreement rate
- replay failure count

4. Release integration
- replay output must be included in the evaluation artifact
- replay failure, runtime load failure, and insufficient sample size must be written into the release report

Exit criteria:

- a large Canada historical batch can be replayed and compared quantitatively
- replay results can directly support promote / keep_active decisions
- release readiness is no longer judged by small benchmark samples alone
- replay contains no placeholder logic or undefined-variable failure path

### Iteration 12: Canada Release Gate and Production Quality

Goal:

- establish a real Canada release gate
- require the same release discipline for model, rule, and reference changes

Scope:

- merge release benchmark and replay gate
- stricter promote / keep_active / rollback rules
- fixed thresholds for `decision_f1`, `building_type_f1`, `unit_number_f1`, `unit_recall`, and `commercial_f1`
- drift checks for accept / review / reject rates
- rollback semantics for failed releases
- correct the current release-gate failure mode:
  - benchmark/replay parse failures must block promotion
  - missing metrics must not count as pass
- regression risk and shadow gate must both be enforced

Detailed task requirements:

1. Gate failure policy
- missing metrics -> block
- benchmark parse failure -> block
- replay parse failure -> block
- missing shadow result -> block

2. Fixed thresholds
- `decision_f1`
- `building_type_f1`
- `unit_number_f1`
- `unit_recall`
- `commercial_f1`
- `review_rate`
- `reject_rate`
- `regression_risk`

3. Promote / rollback rules
- promote requires benchmark + replay + shadow together
- keep-active must preserve explicit failure reasons
- rollback must identify the active version being restored

4. Release report
- every release must produce a standard-format report
- the report must include benchmark, shadow, replay, and drift sections together

Exit criteria:

- every Canada release produces a fixed quantitative report
- promotion decisions are reproducible and explainable
- regression risk can be blocked before release

### Iteration 13: Canada Profile Extraction and Future Country Boundary

Goal:

- extract the country boundary only after the Canada system is complete and accurate
- keep future country support based on a stable skeleton rather than premature abstraction

Scope:

- solidify `CanadaProfile`
- create parser / reference / benchmark / normalization Canada packs
- pull Canada-specific logic out of the general core path
- preserve plugin boundaries for future countries without implementing them yet
- remove the current import-time singleton profile behavior and replace it with:
  - request/model/workspace-selectable profile runtime
- multiple profile runtimes able to coexist in one process
- profile affecting parsing/normalization/validation, not just response metadata

Detailed task requirements:

1. Runtime profile propagation
- request-level profile
- model-artifact-level profile
- workspace default profile
- the precedence order between the three must be explicit

2. Core de-singletonization
- remove import-time `_ACTIVE_PROFILE` from `common.py` / `utils.py`
- parsing, normalization, and validation must accept an explicit profile runtime

3. Canada pack extraction
- Canada parser patterns
- Canada normalization
- Canada reference rules
- Canada benchmark rules
- Canada-specific decision logic

4. Future extension boundary
- preserve only profile / parser / reference / benchmark extension interfaces
- do not pre-implement other countries yet
- do not regress current Canada performance or accuracy

Exit criteria:

- Canada-specific logic is no longer scattered through the core
- AddressForge presents itself as “Canada default implementation + future country boundary”
- Canada quality work is not disrupted by premature international abstraction
- profile selection is no longer pinned to a process-wide environment singleton

## 4. Current Status After 2026-04-28

Based on `AddressForge Iteration Summary - 2026-04-28` and the current codebase, the more accurate state is:

- Iteration 1 has produced a usable Canada parsing baseline
- Iteration 2 has the benchmark and error-bucket foundation in place
- Iterations 3 through 7 have partial foundations landed, but are not fully closed
- the most important next step is not more platform shell work, but turning those partial foundations into a release-ready Canada system

Representative work already landed includes:

- stronger Canada unit / building / commercial parsing coverage
- release benchmark metric scaffolding
- base training / evaluation / shadow / replay scaffolding
- main-path review -> gold_label and replay persistence
- initial `BaseCountryProfile` / `CanadaProfile` boundaries

Key gaps still open include:

- training still needs to move further toward real reranking and calibration
- replay and release gate still need validation on larger Canada-scale data
- canonical assets still need final schema and larger-scale consolidation checks

For that reason, the next formal execution stage starts at **Iteration 8**, focused on converting Iterations 1-7 foundations into a complete, release-ready Canada system.

## 5. Review-Driven Priority Order After 2026-04-28

While executing Iterations 8-13, the immediate blocking sequence should be:

0. **Fix core request-path stability first**
- `create_run()` and `etl_run` must agree on field names
- new and old signatures for `simple_parse_address()` / `normalize_province()` / `_finalize_parsed()` must be unified
- any `TypeError` in `normalize/parse/validate` must be eliminated before later iteration claims

1. **Iteration 8 first fixes real training/inference breakpoints**
- restore a working reranker runtime path
- make trained artifacts actually participate in parse/validate
- align training data extraction with the live schema

2. **Iteration 11 removes replay simulation**
- candidate vs active must run for real
- replay output must be persisted and included in release reporting

3. **Iteration 12 hardens the release gate**
- any evaluation gap, parse failure, or replay failure must block promotion

4. **Iteration 13 redoes the profile runtime boundary**
- make Canada profile truly runtime-selectable first
- only then preserve the extension boundary for future countries

## 6. Newly Confirmed Blocking Issues From Code Review

The following issues are now confirmed by direct code review and block acceptance of Iterations 8-13:

1. **Runtime breakpoints still exist in the request path**
- `simple_parse_address()` still calls `_finalize_parsed()` with the old signature
- `api/server.py` still calls `normalize_province()` using the old signature
- the profile-runtime refactor is only partially applied and the main path is not yet stable

2. **The reranker runtime is still not closed**
- `RerankerArtifactLoader` is still missing
- `AddressRequest.reranker_version` is still missing
- candidate parsing still cannot truly load version-specific weights

3. **The reranking trainer is still not aligned with the live schema**
- it still reads nonexistent `unit_source` / `feature_vector` columns
- it still uses fake supervision via `target_is_correct = 1`

4. **Historical replay still lacks true runtime binding**
- `_load_model_runtime()` is still a placeholder
- replay still does not truly load separate active and candidate runtimes
- the candidate-difference path still depends on the unresolved reranker-version path

5. **The release gate is still short of the documented requirement**
- missing-metric handling is improved
- but hard thresholds are still not enforced for `building_type_f1`, `unit_number_f1`, `unit_recall`, `commercial_f1`, `review_rate`, and `reject_rate`

## 7. More Detailed Execution Sequence For Iterations 8-13

### Phase A: Runtime Stabilization

Finish these four actions before resuming later iteration claims:

1. align `etl_run` runtime helpers with the schema
2. align function signatures across `common.py` and `api/server.py` for profile-aware normalize/parse helpers
3. remove all stale call sites that can crash the request path
4. run a minimal smoke test for `normalize -> parse -> validate`

### Phase B: Iteration 8 Completion

1. implement `RerankerArtifactLoader`
2. add `reranker_version` to `AddressRequest`
3. make both active and candidate models load their own artifacts
4. fix `reranking_trainer` feature extraction and supervision labels
5. retrain parser weights on real gold samples

### Phase C: Iteration 11 Completion

1. change replay to real active-runtime vs candidate-runtime execution
2. record decision / building / unit comparisons in replay
3. persist replay failures, insufficient samples, and runtime-load failures
4. include replay output in evaluation artifacts and release reports

### Phase D: Iteration 12 Completion

1. enforce the full release-gate metric set
2. let shadow + replay + benchmark jointly decide promotion
3. block on any missing metric, parse error, or replay failure
4. make rollback version selection and logging explicit

### Phase E: Iteration 13 Completion

1. remove the import-time singleton profile behavior
2. define request/model/workspace profile precedence
3. make Canada profile truly govern normalization / parsing / validation
4. only then keep the extension boundary for future countries

## 8. Execution Rhythm

Future development follows this rhythm:

1. work only on tasks belonging to the current iteration
2. finish multiple related tasks continuously inside one iteration
3. summarize only after the iteration is complete
4. move immediately into the next iteration

This means:

- no frequent switching back to console polish or platform shell work
- Canada quality remains the main track until it is complete
