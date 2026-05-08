# AddressForge Development Alignment Prompts

## Document Info
- Document Type: Development Alignment Reference
- Scope: Ongoing AddressForge product and engineering development
- Language: English
- Status: Active

## Purpose
These prompts are intended to continuously realign future development work, so the system does not drift into local error chasing, operations-system-first prioritization, or a rule-patch-heavy path again.

## Alignment Prompts
1. **Prioritize the system design goal, not local error chasing.**
2. **The current main objective is real Canada address accuracy for houses and apartments, especially apartment unit parsing, but the system must not collapse into only being a unit extractor.**
3. **Further quality gains should increasingly come from gold-driven learned weights, candidate quality, and hard-sample training, not mainly from adding more regex rules.**
4. **Every optimization round must explain whether the gain came from rules, models, data density, or candidate quality.**
5. **While improving `unit_number_f1` and `unit_recall`, the system must also protect `building_type_f1`, `decision_f1`, and avoid regressions on houses.**
6. **After each phase of parsing optimization, the work should return to canonical address quality, reference fusion, and stable address assetization.**
7. **Operations-system issues may be recorded, but their priority remains below the core data-processing and address-quality pipeline.**

## How To Use
- When development direction needs recalibration, this document can be referenced directly.
- When work starts drifting, use these prompts as a checklist to verify that the current effort still serves the system design goal.
- When entering a new phase, this document should act as a direction constraint rather than letting the work be driven only by local metrics.

## Conclusion
This document is neither a product-requirements document nor an execution-plan document. It is a directional constraint for ongoing AddressForge development. Any phase-specific optimization, planning, or implementation should remain aligned with these prompts.
