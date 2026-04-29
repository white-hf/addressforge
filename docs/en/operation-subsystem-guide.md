# AddressForge Operation Subsystem Product Documentation (v2.0)

## 1. System Overview
AddressForge Operation Subsystem is a "Human-in-the-loop" console designed for advanced address governance. In version 2.0, it supports not only data cleaning and manual review but also the full ML evolution lifecycle, address assetization, and release gate mechanisms.

## 2. Core Functional Modules

### 2.1 Control Center
The "Brain" of the system that orchestrates the entire governance pipeline:
*   **End-to-End Control**: One-click triggers for Ingestion, Cleaning, Retraining, and Shadow Evaluation.
*   **Asset Snapshot**: Real-time visibility into the total volume of Canonical Address Assets (Buildings/Units).
*   **Job Tracking**: Dynamic monitoring of background job status and result summaries.

### 2.2 Review Lab (AI-Assisted)
A modern **three-column interactive layout** for maximum productivity:
*   **AI Insights**: Integrated Risk Radar and LLM Correction Suggestions that automatically identify potential conflicts.
*   **Error-Driven Sampling**: Smart sampling based on "Error Buckets" ensures experts focus on the most valuable samples.
*   **Seamless Feedback**: Toast-based notifications replace disruptive popups.

### 2.3 Assets & Version Management
*   **Asset Promotion**: Convert high-confidence results into "Canonical Address Assets" with a single click.
*   **Snapshot Freezing**: Bundle Gold label sets into versioned snapshots for model iterations.

### 2.4 Report Center & Release Gate
*   **Release Gate Check**: Candidate models must pass quantitative gates via Delta Analysis (F1, Recall, etc.) before promotion.
*   **Historical Replay**: Comparative analysis of model performance across large-scale historical datasets.

## 3. Standard Operating Procedure (SOP)
1.  **Data Readiness**: Trigger "Start Sync" and "Run Cleaning" in the Control Center.
2.  **AI-Guided Review**: Complete adjudications in the Review Lab using AI insights.
3.  **Model Evolution**: Trigger the "Automated Training" pipeline once enough gold data is collected.
4.  **Readiness Check**: Verify "Release Gate" status in the Report Center for the candidate model.
5.  **Asset Finalization**: Click "Asset Promotion" to solidify results into the Canonical Asset Library.

---
*Note: This system follows the AI-in-the-loop principle, ensuring every canonical record is scientifically verified.*
