# AddressForge Business Expert Platform Documentation (v1.0)

## 1. Vision
Transform AddressForge from an "ML Experiment Management Tool" to an "Address Business Expert Workstation," achieving **visualized governance and closed-loop control** of the entire data processing workflow. Hide ML details via business perspectives, enabling non-technical staff to efficiently handle address quality monitoring, error correction, and asset publishing.

## 2. Core Functional Layout (Business Workflow Navigation)
*   **Overview Center**: Real-time monitoring of the data processing lifecycle.
*   **Address Governance**: Analytics for cleaning performance and error bucketing.
*   **Expert Review Lab**: Side-by-side comparison interface for manual calibration and Gold Label generation.
*   **Assets Library**: Management of standard address snapshots and version releases.

## 3. Localization Strategy (I18N)
*   **Terminology Standardization**: Centralized dictionary for UI terms.
*   **Real-time Switching**: One-click toggling between UI languages.

# Iteration Development Roadmap

## Phase 1: Business Process Dashboard
- [ ] Task 1.1: Develop `GET /api/v1/business/process-overview` API.
- [ ] Task 1.2: Integrate end-to-end process flow charts into the Dashboard.
- [ ] Task 1.3: Implement basic I18N JS infrastructure.

## Phase 2: Address Review Lab
- [ ] Task 2.1: Develop `GET /api/v1/business/review/queue` API.
- [ ] Task 2.2: Implement side-by-side comparison and correction interface.
- [ ] Task 2.3: Implement automated correction result persistence.

## Phase 3: Closed-loop Release
- [ ] Task 3.1: Develop release preview interface.
- [ ] Task 3.2: Tailwind CSS modernization for the whole interface.
