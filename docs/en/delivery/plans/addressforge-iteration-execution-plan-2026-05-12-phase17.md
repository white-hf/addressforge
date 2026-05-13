# AddressForge Iteration Execution Plan - 2026-05-12 (Phase 17: BuildingTypeModel And Retrieval Fusion)

## Document Info
- Document type: Execution Plan / ML Task Expansion Plan
- Effective date: 2026-05-12
- Owner: AddressForge Architecture / Senior Engineering
- Status: Planned
- Goal: complete the `BuildingTypeModel` baseline and turn retrieval into a stable fusion layer

## 1. Background And Problem Definition
Retrieval is in the system, but it still behaves more like:
- retrieval-assisted parsing

rather than:
- a stable retrieval-first fusion layer

At the same time, `BuildingTypeModel` has not yet been delivered as a formal baseline.

## 2. Main Goal
1. build `BuildingTypeModel v1`
2. define retrieval’s runtime fusion boundary
3. begin using ML on commercial/incomplete residual buckets

## 3. Requirements

### Requirement 17-1: BuildingTypeModel baseline
Delivery requirements:
- deliver baseline / compare / shadow for:
  - `single_unit`
  - `multi_unit`
  - `commercial`

### Requirement 17-2: Retrieval fusion policy
Delivery requirements:
- define when retrieval is:
  - a hint only
  - a strong anchor
  - protected/overridden by business safety rules

### Requirement 17-3: Commercial/incomplete ML support
Delivery requirements:
- bring:
  - commercial prefix noise
  - incomplete vs recoverable incomplete
  into supervised support

## 4. Technical Methods
- **Building-type structured classifier**
- **Retrieval confidence gating**
- **Residual review bucket learning**

## 5. Expected Benefit
- reduce building_type regressions
- move retrieval from hinting to stable fusion input
- reduce hard-rule dependence for commercial prefix noise

## 6. Deliverables
- `BuildingTypeModel v1`
- retrieval fusion policy
- commercial/incomplete compare report

## 7. Completion Criteria
1. `BuildingTypeModel` has baseline / compare / shadow
2. retrieval fusion boundaries are explainable and auditable
3. commercial/incomplete is no longer handled only by hard rules

## 8. Next Dependency
After Phase 17:
- `Phase 18: Rollout, Gate, And Operations Completion`

