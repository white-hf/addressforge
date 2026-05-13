# AddressForge Iteration Execution Plan - 2026-05-12 (Phase 14: ML Foundation Alignment)

## Document Info
- Document type: Execution Plan / Architecture Delivery Plan
- Effective date: 2026-05-12
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: align the training, feature, and artifact foundations of the next-generation ML system

## 1. Background And Problem Definition
The system already has:
- a `DecisionModel` CatBoost baseline
- review/gold/freeze/eval loops
- retrieval and reranker service entry points

But the ML foundation is still inconsistent:
- training features and online inference features do not match
- artifact contracts are inconsistent
- model loading is fragmented
- runtime cannot reliably prove that it is using the trained model

## 2. Main Goal
1. establish `FeatureSchema v1`
2. establish a unified model artifact contract
3. establish a unified model loader / activation protocol
4. provide a stable base for Phase 15-18

## 3. Requirements

### Requirement 14-1: Unified training/inference feature schema
Delivery requirements:
- `DecisionModel` training and online inference must share one schema
- `CandidateRerankerModel` must reuse the same schema registry
- every feature must define:
  - name
  - type
  - missing-value strategy
  - version

### Requirement 14-2: Unified artifact contract
Delivery requirements:
- every model must emit at least:
  - metadata json
  - binary artifact
  - feature schema reference
  - metric summary
- runtime must not rely on implicit file-name conventions

### Requirement 14-3: Unified model loading protocol
Delivery requirements:
- unified model path resolution
- unified active/shadow version selection
- unified fallback strategy

### Requirement 14-4: Unified shadow/compare output
Delivery requirements:
- `DecisionModel` compare, shadow, and artifact summaries must follow one structure
- outputs must be directly consumable by later gate logic

## 4. Technical Methods
- **FeatureSchema registry**
- **Artifact manifest**
- **Model loader abstraction**
- **Schema-validated inference**

Current priority slice:
- **DecisionModel training/inference schema alignment**
  - first add a shared inference feature builder for `DecisionModel`
  - make `ModelService` assemble online inputs from the training metadata schema instead of continuing to use the old 28-d numeric vector
  - publish standardized runtime sidecars:
    - `decision_catboost_v1.json`
    - `decision_catboost_v1.pkl`
    - so serving no longer depends on a bare `.cbm` file only
  - benefit: remove the most dangerous runtime drift first, then expand toward a full schema registry

## 5. Expected Benefit
- remove training/inference drift
- make online ML outputs trustworthy
- create a hard foundation for later runtime adoption and gate logic

## 6. Deliverables
- `FeatureSchema v1`
- artifact manifest
- unified model loader
- schema validation report
- Phase 14 execution summary

## 7. Completion Criteria
1. `DecisionModel` training and inference use the same schema
2. runtime loads models from the artifact manifest correctly
3. compare/shadow outputs are reusable by later gate layers

## 8. Next Dependency
After Phase 14:
- `Phase 15: DecisionModel Runtimeization`
