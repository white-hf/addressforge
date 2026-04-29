# AddressForge Core Engine

AddressForge is a next-generation address intelligence engine. It provides a modular framework for parsing, validating, and assetizing addresses, powered by a Human-in-the-loop ML ecosystem.

## 🏗️ Modern Architecture

AddressForge is built on four architectural pillars:

### 1. Profile-Driven Extensibility
The engine is decoupled from regional logic via the **Profile System** (`core/profiles/`).
- **CanadaProfile**: Specialized for North American patterns (Basement, Units, Penthouse, etc.).
- **Global Ready**: New countries can be added by implementing a `BaseCountryProfile` adapter.

### 2. Error-Driven Active Learning
We don't just collect labels; we collect *the right labels*.
- **Error Buckets**: Detailed attribution (Pattern Miss, Reference Gap, etc.).
- **Smart Sampling**: The system automatically pulls samples from the most frequent "Error Buckets" into the expert review queue.

### 3. Address Assetization (Canonicalization)
Moving beyond string parsing to stable data assets.
- **Deduplication**: Maps multiple address variants to unique `Building ID` and `Unit ID`.
- **Promotion**: High-confidence cleaning results are automatically promoted to the Canonical Asset Library.

### 4. Release Gate & Guardrails
Ensuring safety in model evolution.
- **Historical Replay**: Reruns new models over historical batches to detect regressions.
- **Release Gate**: Quantitative check (Delta analysis) required before promoting any candidate model to Active status.

---

## 🛠️ Project Structure

```text
src/addressforge/
├── api/            # Public Address Intelligence APIs
├── console/        # Control Center & Review Lab Web Server
├── control/        # Background Job Management (Queue/Worker)
├── core/           
│   └── profiles/   # Country-specific adapters (Canada, etc.)
├── learning/       # ML Logic: Evaluator, Trainer, Shadow Mode
├── pipelines/      # Orchestrated workflows (Training, Export)
└── services/       # Business Logic Layer (Assets, Replay, Review)
```

---

## 🚀 Operations SOP (Standard Operating Procedure)

1.  **Ingestion**: Sync raw data via the Control Center.
2.  **Cleaning**: Run the parsing pipeline to identify risks.
3.  **Review**: Adjudicate "Uncertainty" samples in the 3-column Review Lab.
4.  **Training**: Trigger the automated Training Pipeline using curated Gold labels.
5.  **Evaluation**: Run Shadow metrics and check the "Release Gate" in the Report Center.
6.  **Promotion**: Activate the new model version.
7.  **Assetization**: Promote high-confidence results to the Canonical Asset Library.

---

## 📖 Deep Dives

- [Operation Subsystem Product Manual (ZH)](docs/zh/operation-subsystem-guide.md)
- [Operation Subsystem Product Manual (EN)](docs/en/operation-subsystem-guide.md)
- [Iteration Roadmap](docs/en/addressforge-version-plan.md)

---
*AddressForge: Turning messy strings into intelligent business assets.*
