# AddressForge Phase 22R-2 Execution Summary

## Governed Runtime Bundle and Real Candidate Lifecycle

- Date: 2026-07-30
- Status: Completed
- New candidate: model ID 51
- Production action: no promotion, reload, rollback, or active-model change

## Requirement and Method

Iteration 22R-1 added manifest validation, but Evaluator and Replay still assembled manifests independently and could silently fall back.

This iteration added a shared Runtime Bundle Loader with:

- `governed` mode: validate identity, components, files, and SHA256 before load; reject every fallback after load
- `compatibility` mode: preserve legacy behavior while reporting contract and fallback evidence
- separate service instances for each Active/Candidate bundle
- immutable governed decision policy without local `decision_policy.json` override

Evaluator, Replay, and Shadow now use governed bundles for selected model versions. Trainer also preserves schema, bundle ID, and hash algorithm in registry metrics so evaluation cannot lose the contract when artifact_path changes.

## Real Validation

Legacy IDs 1, 43, and 50 all failed governed loading. Replay and Evaluator returned the same `runtime_manifest_invalid` result for ID 50.

Compatibility loading of ID 1 explicitly reported:

- Decision: `legacy_path`
- Reranker: `legacy_path`
- BuildingType: `fallback`

A new non-promoted candidate was trained from existing Human Gold:

- training run: 4694
- model ID: 51
- version: `v_phase22r_contract_20260730_2217`
- distinct Human Gold: 1,740

After training, the contract, all hashes, and all three manifest-bound services passed. A governed evaluation then completed:

- evaluation run: 4698
- Gold rows: 1,748
- status after evaluation: `evaluated`
- is_default: 0
- contract after artifact_path update: still valid

## Metric Comparison

| Metric | ID 43 | ID 51 | Delta |
|---|---:|---:|---:|
| Decision F1 | 0.9416 | 0.9031 | -0.0385 |
| Building Type F1 | 0.8700 | 0.8689 | -0.0011 |
| Unit F1 | 0.8392 | 0.8369 | -0.0023 |
| Unit Precision | 0.9325 | 0.9300 | -0.0025 |
| Unit Recall | 0.7628 | 0.7607 | -0.0021 |
| Commercial F1 | 0.3010 | 0.2886 | -0.0124 |

ID 51 proves the runtime contract, not a quality improvement. It remains unpromoted because metrics did not improve and Replay/Shadow evidence is absent.

## Validation and Residual Work

- Python compilation passed.
- 31 targeted Runtime/Registry/Replay/Evaluator/Trainer tests passed.
- Training took about 15 minutes, dominated by repeated full parsing and repeated service initialization across four derived-weight passes.

Phase 22R-3 will make API startup choose governed loading for valid models, preserve explicit compatibility for the current invalid active model, make Reload fail closed, move Worker reload to the shared loader, and expose registry/contract/actual-source identity.
