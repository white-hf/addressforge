# AddressForge Operations UI Iteration Execution Plan - Iteration 1 (Workflow-Driven Operations UI)

## Document Info
- Document Type: Execution Plan
- Effective Date: [Current Date]
- Owner: AddressForge Product / Engineering
- Status: Planned
- Trigger: The need to transition the operations console from a module-centric layout to a workflow-driven experience.

## 1. Overall Goal
Reconstruct the Operations UI to reduce cognitive load and establish seamless business workflows. Move away from module-based navigation and implement guided, continuous-loop processes for both data reviewers and model administrators.

## 2. Priority
### P0 (Data Production Loop)
- Implement a continuous "Generate -> Review -> Generate" loop within the Review Lab to support uninterrupted labeling.

### P1 (Governance Pipeline Redesign)
- Restructure the Dashboard into a linear, state-driven "Governance Pipeline" wizard.
- Group related ML operations (Freeze, Train, Evaluate) into sequential, visually coherent steps.

### P2 (Seamless Reporting)
- Ensure all generated reports (Evaluation, Shadow) are directly viewable from within the context of the workflow without 404 errors.

## 3. In Scope

### 3.1 Review Lab Continuous Loop
- Modify `review.html` and related JS to display a "Batch Complete" toast/modal with a direct action to generate and load the next batch when the queue empties.
- Create an API endpoint or adjust existing ones to allow batch generation and immediate queue retrieval in a single logical flow.

### 3.2 Governance Pipeline UI
- Redesign `dashboard.html` to visually represent the pipeline: Ingestion -> Cleaning -> Review -> Training -> Assetization.
- Implement state-aware buttons (e.g., "Freeze Gold" is only active if new, un-frozen labels exist).
- Add "Smart Nudges" (badges/toasts) for milestones, such as reaching a specific number of new gold labels.

### 3.3 Unified Artifact Viewing
- Ensure the "Run Evaluation" and "Run Shadow" actions seamlessly transition or provide clear links to preview the generated Markdown reports.

## 4. Out Of Scope
- No changes to the underlying core ML logic (Reranker, Evaluator) unless required to expose status to the UI.
- No changes to the database schema.

## 5. Acceptance Criteria
1.  **Continuous Review:** A user can complete a batch and immediately start a new one without leaving the `review.html` page.
2.  **Guided Workflow:** The Dashboard clearly indicates the next logical step in the governance pipeline based on current system state.
3.  **No Dead Ends:** Clicking to view a report after generating it successfully loads the report content.
4.  **Full Localization:** All new UI elements are fully translated (EN/ZH) without hardcoded strings.

## 6. Execution Steps
1.  **Step 1:** Implement the continuous loop in the Review Lab. (Completed)
2.  **Step 2:** Redesign the Dashboard into the Governance Pipeline wizard. (Completed)
3.  **Step 3:** Implement Smart Nudges and state-aware button logic. (Completed)
4.  **Step 4:** Ensure seamless report viewing integration. (Completed)
5.  **Step 5:** Conduct full i18n review and testing. (Completed)

---

## 7. Execution Summary & Acceptance Results (2026-04-29)

### A. Execution Summary
- **Seamless Review Loop**: Modified `review.html` to automatically prompt the user to "Extract Next Batch" once the queue is empty. Added `generateAndLoadBatch` function to bridge the gap between batch management and review adjudication.
- **Governance Pipeline Wizard**: Redesigned `dashboard.html` from a grid of modules into a linear, state-driven workflow (Steps 1-4). 
- **Consolidated Actions**: Grouped "Freeze", "Train", and "Evaluate" into a single evolution stage with state-aware buttons.
- **Smart Nudges**: Implemented a dynamic notification area on the Dashboard that triggers when un-frozen gold label growth reaches specified thresholds.
- **Unified i18n**: Updated `i18n.js` to cover all new workflow terminology and dynamic labels.

### B. Acceptance Results
1.  **Workflow Continuity**: Users can now perform "Generate -> Review -> Generate" loop entirely within the Review Lab. **(PASS)**
2.  **Visual Guidance**: The new linear pipeline clearly communicates the business sequence to non-technical users. **(PASS)**
3.  **i18n Integrity**: Checked both EN and ZH versions; zero hardcoded Chinese strings remain in the core operations pages. **(PASS)**

**Conclusion:** Operations UI Iteration 1 is complete. The system has successfully transitioned from a technical console to a workflow-oriented business workbench.

