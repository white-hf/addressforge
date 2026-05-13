# AddressForge Operations Subsystem Product Requirements Document (PRD)

## 1. Product Vision & Positioning
The AddressForge Operations Subsystem is a "Human-in-the-loop" workbench designed to transform messy address strings into canonical, machine-readable business assets. 

**Core Problem Solved:** The previous UI was organized by technical modules (e.g., Dashboard, Review, Batch, Reports), forcing operations users to memorize complex dependencies (Ingest -> Clean -> Batch -> Review -> Freeze -> Train -> Eval -> Shadow -> Promote). This resulted in high cognitive load and workflow fragmentation.

**New Positioning (Workflow-Driven):** The subsystem will transition from a "Feature Console" to a "Guided Workflow Workbench". It will prioritize the business objective ("What should I do next?") over system capabilities, enabling seamless execution of both high-volume data labeling and advanced ML model evolution.

## 2. Core User Personas & Workflows

### 2.1 The Data Reviewer (Primary Loop)
**Goal:** Rapidly adjudicate ambiguous or low-confidence addresses.
**Workflow:**
1.  **Generate Review Batch:** System automatically pulls the most valuable (low confidence / high frequency error) samples.
2.  **Expert Adjudication:** Use the 3-column Review Lab (with AI Insights) to confirm or correct addresses.
3.  **Continuous Loop:** Upon finishing a batch, the system immediately prompts to generate the next batch without returning to a central dashboard.

### 2.2 The Model Administrator (Milestone Branch)
**Goal:** Evolve the core parsing engine safely and deploy new models.
**Workflow:**
1.  **Monitor Growth:** Observe the accumulation of new Gold Labels.
2.  **Trigger Evolution:** When a threshold is met (e.g., 500 new labels), freeze a Gold Snapshot and trigger the `ParserRerankerTrainer`.
3.  **Release Gate Check:** Review the automatically generated Shadow and Evaluation reports.
4.  **Promote:** If metrics (F1, Regression Risk) pass the hard gate, promote the model to Active status.

## 3. Key Features & Information Architecture (IA) Redesign

### 3.1 Unified "Governance Pipeline" (Replacing Dashboard)
The landing page will be transformed into a linear, state-driven wizard.
- **Visual Progress:** Displays the flow from Data Ingestion -> Cleaning -> Review -> Model Evolution -> Assetization.
- **Contextual Actions:** Buttons dynamically enable/highlight based on system state. (e.g., "Freeze & Train" only highlights when un-frozen gold labels exist).
- **Smart Nudges:** Toast notifications or badges indicating when a milestone is reached (e.g., "New Gold Labels available for training").

### 3.2 Seamless Review Loop (Review Lab Enhancements)
- **End-of-Batch Prompt:** When the review queue reaches 0, a modal/toast will appear: *"Batch Complete! You generated X gold labels. [Generate Next Batch]"*. This eliminates the need to navigate back to the "Batch Management" module.

### 3.3 Abstracted Background Complexity
- **Consolidated ML Actions:** The "Freeze Gold", "Train Model", and "Run Evaluation" steps will be visually grouped or sequenced, reducing the need for users to manually trigger each step independently if they choose an "Auto-Evolve" path.
- **In-place Report Viewing:** Shadow and Evaluation reports will be previewable directly from the Pipeline view or Report Center without 404 dead-ends.

## 4. Non-Functional Requirements
- **Internationalization (i18n):** 100% bilingual (EN/ZH) support across all text nodes, placeholders, and dynamic status messages. No hardcoded Chinese strings in templates.
- **Feedback Immediacy:** All actions (job dispatch, batch generation) must provide immediate, non-blocking visual feedback (Toast notifications).
- **Graceful Degradation:** If the LLM Refiner fails or is unavailable, the Review Lab must fall back smoothly to heuristic parsing results without breaking the UI.

## 5. Success Metrics
1.  **Workflow Continuity:** 0 page reloads required to complete the "Generate -> Review -> Generate" loop.
2.  **Cognitive Load Reduction:** Operations users can execute a full model training and release cycle without consulting technical documentation.
3.  **UI Consistency:** Zero occurrences of mixed language content or unmapped `data-i18n` keys.
