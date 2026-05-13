# AddressForge Iteration Execution Plan - 2026-05-12 (Phase 16: CandidateRerankerModel Completion)

## Document Info
- Document type: Execution Plan / Supervised Reranking Delivery Plan
- Effective date: 2026-05-12
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: complete true supervised candidate reranking

## 1. Background And Problem Definition
Current reranking has two gaps:
1. the service layer already expects a CatBoost reranker
2. the training layer is still mainly statistical weighting rather than a full supervised loop

## 2. Main Goal
1. define candidate supervision samples
2. train a real `CandidateRerankerModel`
3. make `RerankerService` consume the supervised model

## 3. Requirements

### Requirement 16-1: Real supervised reranker training
Delivery requirements:
- define winner/loser or pointwise candidate labels
- export a real `.cbm` reranker artifact

### Requirement 16-2: Candidate feature schema v1
Delivery requirements:
- candidate features must use a unified schema
- at minimum cover:
  - parser source
  - candidate completeness
  - unit-hint alignment
  - numbered-road conflict
  - semantic alignment

### Requirement 16-3: reranker compare/shadow
Delivery requirements:
- compare:
  - old weight-based ranking
  - supervised reranker
- quantify best-candidate, building_type, and unit improvements

## 4. Technical Methods
- **Pairwise/pointwise CatBoost baseline**
- **Semantic alignment as structured feature**
- **Best-candidate error audit**

## 5. Expected Benefit
- reduce wrong best candidates
- stabilize apartment/unit performance
- provide a reliable ranking layer for retrieval fusion

## 6. Deliverables
- `CandidateRerankerModel v1`
- reranker `.cbm` artifact
- compare report
- shadow report

## 7. Completion Criteria
1. `RerankerService` truly consumes the supervised model
2. reranking is no longer primarily driven by the old weight logic
3. best-candidate selection improves measurably

## 8. Next Dependency
After Phase 16:
- `Phase 17: BuildingTypeModel And Retrieval Fusion`

